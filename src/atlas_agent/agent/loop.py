# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/loop.py
# PURPOSE: The agentic reasoning loop: prompt the model, execute the tools it asks
#          for, feed the results back, repeat until it stops or a bound is hit.
#          This is where an LLM's output becomes actions, so every tool call passes
#          the kill switch and the risk manager on its way through.
# DEPS:    providers.base (the model), tools.registry (what it may call),
#          risk.manager + safety.kill_switch (the gates), audit (the record)
#
# DESIGN:  The loop is BOUNDED on every axis — iterations, tool calls, tokens. An
#          unbounded agent with broker access is not a feature, it is an incident.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations
import hashlib
import math

import logging
from typing import Any, Union, List, Optional

from atlas_agent.agent.result import AgentResult, IterationResult
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session, UserApprovalPending
from atlas_agent.providers.base import AIProvider
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot
from atlas_agent.safety.kill_switch import AdvancedKillSwitch
from atlas_agent.safety.action_plan import SafetyActionPlanner
from atlas_agent.safety.executor import SafetyActionExecutor
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ToolCall, ToolResult, ToolError, GuardrailChain


# ==============================================================================
# GUARDRAIL CHAIN
# ==============================================================================

class DefaultGuardrailChain:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def evaluate(self, tool_call: ToolCall, session: Session) -> Union[ToolResult, ToolError, UserApprovalPending, None]:
        """Decide whether a tool call may proceed.

        Returns:
            None to allow, or a UserApprovalPending / ToolError to intercept it.
        """
        # An unknown tool returns None (allow) rather than an error, because the
        # REGISTRY is what refuses to execute it. This chain only adds the approval
        # gate on top; it is not the thing that bounds the tool set.
        try:
            tool = self.registry.get_tool(tool_call.name)
        except KeyError:
            return None

        # The gate is read off the tool's own spec, not from a list kept here. A tool
        # that can move money declares approval_gated=True in tools/builtin.py, and the
        # protection travels with the definition instead of relying on this file being
        # updated in step.
        if tool.approval_gated:
             return UserApprovalPending(
                approval_id=f"approve_{tool_call.id}",
                notification=f"Approval required for tool {tool.name}",
                timeout_seconds=3600
            )
        return None


# ==============================================================================
# AGENT LOOP
# ==============================================================================

class AgentLoop:

    # --- Construction ---

    def __init__(
        self,
        provider: AIProvider,
        tool_registry: ToolRegistry,
        guardrails: GuardrailChain,
        # Two independent ceilings. `max_iterations` bounds reasoning turns;
        # `max_tool_calls` bounds actions across ALL turns. A model that loops calling
        # one tool would exhaust the second long before the first, and vice versa.
        max_iterations: int = 10,
        max_tool_calls: int = 50,
        audit_writer: AuditWriter | None = None,
        risk_manager: RiskManager | None = None,
        kill_switch: AdvancedKillSwitch | None = None,
        safety_planner: SafetyActionPlanner | None = None,
        safety_executor: SafetyActionExecutor | None = None,
        log_raw_prompts: bool = False,
        log_provider_text: bool = False,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.guardrails = guardrails
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.audit_writer = audit_writer
        self.risk_manager = risk_manager
        self.kill_switch = kill_switch
        self.safety_planner = safety_planner or SafetyActionPlanner(risk_manager=risk_manager)
        self.safety_executor = safety_executor or (
            SafetyActionExecutor(
                tool_registry=tool_registry,
                kill_switch=kill_switch, # type: ignore
                risk_manager=risk_manager, # type: ignore
                audit_writer=audit_writer
            ) if kill_switch and risk_manager else None
        )
        self.log_raw_prompts = log_raw_prompts
        self.log_provider_text = log_provider_text

    # ==========================================================================
    # LLM ARGUMENT VALIDATION (the trust boundary)
    # ==========================================================================
    #
    # Everything below parses arguments the MODEL produced. It is untrusted input in
    # the strictest sense: it is generated text, it can be steered by a poisoned
    # prompt, and it feeds straight into the risk manager. Nothing here coerces or
    # guesses — every failure raises.

    def _parse_positive_float(self, raw: Any, field_name: str) -> float:
        if raw is None:
            raise ValueError(f"missing required field: {field_name}")
        # bool before float: isinstance(True, int) holds, so True would parse as 1.0
        # and become a real quantity.
        if isinstance(raw, bool):
            raise ValueError(f"invalid numeric field: {field_name}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid numeric field: {field_name}") from exc
        # NaN/inf must die here. NaN loses every comparison silently, so a NaN notional
        # would satisfy each risk ceiling downstream without any of them noticing.
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be a positive finite number")
        if value <= 0:
            raise ValueError(f"{field_name} must be positive")
        return value

    def _market_reference_price(self, args: dict[str, Any]) -> float:
        # A market order has no price of its own, but risk cannot size it without one.
        # Four aliases are accepted because models are inconsistent about which key they
        # use — and the alternative (defaulting to zero, or skipping the check) would
        # let a market order past every notional limit as though it were free.
        for field_name in ("price", "reference_price", "current_price", "estimated_price"):
            raw_value = args.get(field_name)
            if raw_value is None:
                continue
            return self._parse_positive_float(raw_value, field_name)
        # No price, no order. Raising is the whole point: an unpriceable order is an
        # unbounded one.
        raise ValueError("market orders require an explicit positive reference/current/estimated execution price")

    def _build_propose_order_risk_input(
        self,
        tool_call: ToolCall,
        session: Session,
    ) -> OrderRiskInput:
        args = tool_call.arguments or {}
        symbol = str(args.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("missing required field: symbol")

        # Allowlist, not a cast. A model emitting "long" or "SELL_SHORT" is rejected
        # rather than coerced into something that happens to parse.
        side = str(args.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError("invalid field: side")

        quantity = self._parse_positive_float(args.get("quantity"), "quantity")
        order_type = str(args.get("order_type") or "market").strip().lower()

        if order_type == "limit":
            price = self._parse_positive_float(args.get("limit_price"), "limit_price")
        elif order_type == "market":
            price = self._market_reference_price(args)
        else:
            raise ValueError(f"unsupported order_type: {order_type}")

        return OrderRiskInput(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            notional=quantity * price,
            confidence=getattr(session, "last_confidence", None),
            stop_loss=args.get("stop_loss"),
        )

    # ==========================================================================
    # RUN
    # ==========================================================================

    def run(
        self,
        user_objective: str,
        session: Session,
        system_prompt: str,
        mode: str = "paper",
        run_id: str | None = None,
        portfolio_snapshot: PortfolioSnapshot | None = None,
        open_order_ids: List[str] | None = None,
        # Defaults to False. Safety actions (cancel, flatten) place real orders, so the
        # loop may not authorise its own cleanup unless the caller says it can.
        allow_auto_safety_actions: bool = False,
    ) -> AgentResult:
        run_id = run_id or f"run_{int(session.turn_count)}_{session.id}"
        
        if self.audit_writer:
            self.audit_writer.start_run(run_id)
            run_started_payload = {"mode": mode}
            if self.log_raw_prompts:
                run_started_payload["user_objective"] = user_objective
            else:
                run_started_payload["prompt_hash"] = hashlib.sha256(user_objective.encode("utf-8")).hexdigest()

            self.audit_writer.write_event(
                "run_started",
                run_id=run_id,
                payload=run_started_payload
            )

        result = self._run_loop(
            user_objective, session, system_prompt, mode, run_id, portfolio_snapshot, open_order_ids, allow_auto_safety_actions
        )

        if self.audit_writer:
            status_map = {
                "complete": "completed",
                "error": "failed",
                "blocked": "interrupted",
                "max_iterations": "interrupted",
                "max_tool_calls": "interrupted",
                "approval_required": "interrupted"
            }
            final_status = status_map.get(result.status, "failed")
            self.audit_writer.finish_run(status=final_status, final_status_text=result.status) # type: ignore
            
        return result

    # --- The loop itself ---

    def _run_loop(
        self,
        user_objective: str,
        session: Session,
        system_prompt: str,
        mode: str,
        run_id: str,
        portfolio_snapshot: PortfolioSnapshot | None,
        open_order_ids: List[str] | None,
        allow_auto_safety_actions: bool,
    ) -> AgentResult:
        iterations = []
        messages = [{"role": "user", "content": user_objective}]
        total_tool_calls = 0
        errors = []

        # `range(max_iterations)` rather than `while True`: the loop cannot fail to
        # terminate. Falling out of it is a legitimate outcome (status="max_iterations"),
        # not an error — a model that will not stop is exactly what the bound is for.
        for i in range(self.max_iterations):
            # 1. Get model response
            if self.audit_writer:
                self.audit_writer.write_event(
                    "provider_called",
                    run_id=run_id,
                    iteration=i,
                    payload={"message_count": len(messages)}
                )

            try:
                llm_response = self.provider.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=self.tool_registry.describe_for_model(self.provider.capabilities()),
                )
            except Exception as exc:
                # Sanitised before it is logged. Provider exceptions routinely carry the
                # full request body — which includes the API key and the prompt.
                from atlas_agent.runtime_errors import make_safe_runtime_error
                safe_error = make_safe_runtime_error(operation="provider_complete", exc=exc)
                logging.error(f"Provider error: {safe_error.message}")
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "run_failed",
                        run_id=run_id,
                        iteration=i,
                        status="error",
                        payload=safe_error.to_dict(),
                    )
                return AgentResult(
                    status="error",
                    errors=[safe_error.message],
                    iterations=iterations,
                    total_tool_calls=total_tool_calls,
                )

            if self.audit_writer:
                response_text = llm_response.text or ""
                payload = {
                    "tool_call_count": len(llm_response.tool_calls),
                    "is_final": llm_response.is_final
                }
                
                # Off by default, the model's raw text is NOT written to the audit log —
                # only a hash of it. The trail still proves which response was received
                # (the hash is reproducible from the text), while the reasoning itself,
                # which can quote memory, positions and prompts, stays out of the record.
                # `log_provider_text` is the explicit opt-in for debugging.
                if self.log_provider_text:
                    payload["text"] = response_text
                else:
                    payload["response_hash"] = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
                    payload["length"] = len(response_text)
                    payload["provider"] = self.provider.__class__.__name__

                self.audit_writer.write_event(
                    "provider_response",
                    run_id=run_id,
                    iteration=i,
                    payload=payload
                )

            # Record iteration
            iteration = IterationResult(
                index=i,
                message=llm_response.text,
                tool_calls=llm_response.tool_calls,
            )
            iterations.append(iteration)

            # Update conversation history with assistant message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": llm_response.text}
            if llm_response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": str(tc.arguments)
                        }
                    }
                    for tc in llm_response.tool_calls
                ]
            messages.append(assistant_msg)

            # Check for final response
            if not llm_response.tool_calls and llm_response.is_final:
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "run_completed",
                        run_id=run_id,
                        iteration=i,
                        status="complete",
                        payload={"final_message": llm_response.text}
                    )
                return AgentResult(
                    status="complete",
                    final_message=llm_response.text,
                    iterations=iterations,
                    total_tool_calls=total_tool_calls,
                )

            # ------------------------------------------------------------------
            # TOOL EXECUTION — the gauntlet, in this exact order:
            #   1. call budget      → have we already acted too many times?
            #   2. kill switch      → is the system braking right now?
            #   3. risk manager     → would this specific order breach a limit?
            #   4. guardrails       → does this tool need a human?
            #   5. execute
            # The order is not arbitrary: each step is cheaper and more categorical
            # than the next, and the kill switch is checked BEFORE risk so that a
            # braking system never even evaluates an order it would refuse anyway.
            # ------------------------------------------------------------------
            tool_results = []
            for tool_call in llm_response.tool_calls:
                # Checked per CALL, not per iteration: a single model turn can request
                # twenty tool calls, and the budget has to bind inside that turn too.
                if total_tool_calls >= self.max_tool_calls:
                    if self.audit_writer:
                        self.audit_writer.write_event(
                            "run_completed",
                            run_id=run_id,
                            iteration=i,
                            status="max_tool_calls"
                        )
                    return AgentResult(
                        status="max_tool_calls",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                    )

                # Incremented BEFORE the call, not after. A tool that raises still counts
                # against the budget — otherwise a model could burn the loop forever on
                # calls that fail.
                total_tool_calls += 1

                # 1. Kill Switch Check
                # Re-evaluated on EVERY tool call, not once per run. An operator hitting
                # /kill mid-reasoning must stop the very next action, not wait for the
                # loop to come round again.
                if self.kill_switch:
                    kill_decision = self.kill_switch.evaluate()
                    if not kill_decision.allowed:
                        diagnostics = {"kill_switch": kill_decision.model_dump()}

                        # A braking switch does not merely block: cancel_all/flatten_all
                        # demand corrective action, so the loop builds and runs a safety
                        # plan rather than simply refusing and walking away from an open book.
                        if kill_decision.status in ["cancel_required", "flatten_required"]:
                            portfolio = portfolio_snapshot or PortfolioSnapshot(
                                cash=10000.0, equity=10000.0, total_exposure=0.0
                            )
                            plan = self.safety_planner.create_plan(
                                kill_decision, 
                                portfolio, 
                                open_order_ids or [],
                                mode=mode # type: ignore
                            )
                            diagnostics["safety_action_plan"] = plan.model_dump()
                            
                            if self.audit_writer:
                                event_type = "safety_action_plan_created"
                                if plan.status == "blocked": event_type = "safety_action_plan_blocked"
                                elif plan.status == "requires_approval": event_type = "safety_action_requires_approval"
                                elif any(a.type == "no_op" for a in plan.actions): event_type = "safety_action_no_op"
                                
                                self.audit_writer.write_event(
                                    event_type,
                                    run_id=run_id,
                                    iteration=i,
                                    payload={
                                        "plan_id": plan.plan_id,
                                        "mode": plan.mode,
                                        "status": plan.status,
                                        "action_count": len(plan.actions),
                                        "action_types": [a.type for a in plan.actions]
                                    }
                                )

                            # THREE conditions, all required, before the loop is allowed
                            # to auto-execute a plan that places real orders: an executor
                            # exists, the caller opted in, and the plan itself did not ask
                            # for a human. Any one of them missing leaves the plan recorded
                            # but unexecuted — visible, and waiting for a person.
                            if self.safety_executor and allow_auto_safety_actions and not plan.requires_approval:
                                exec_res = self.safety_executor.execute_plan(
                                    plan, session, portfolio, mode=mode # type: ignore
                                )
                                diagnostics["safety_execution"] = exec_res.model_dump()

                        if self.audit_writer:
                            self.audit_writer.write_event(
                                "kill_switch_blocked",
                                run_id=run_id,
                                iteration=i,
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                                payload=kill_decision.model_dump()
                            )
                        return AgentResult(
                            status="blocked",
                            iterations=iterations,
                            total_tool_calls=total_tool_calls,
                            errors=[kill_decision.reason or "Kill switch blocked execution"],
                            diagnostics=diagnostics
                        )

                # 2. Risk Gating
                tool_spec = None
                try:
                    tool_spec = self.tool_registry.get_tool(tool_call.name)
                except KeyError:
                    pass

                # Gated on the tool's OWN `risk_gated` flag (from tools/builtin.py), so a
                # new order-placing tool inherits the check by declaring it, rather than
                # by someone remembering to extend a condition here.
                if tool_spec and tool_spec.risk_gated and self.risk_manager and tool_call.name == "propose_order":
                    current_portfolio = portfolio_snapshot or PortfolioSnapshot(
                        cash=10000.0, equity=10000.0, total_exposure=0.0
                    )

                    try:
                        # This can raise on malformed model output — see the validation
                        # section above. A raise here means the order never reaches risk,
                        # which is correct: an unparseable order is not a rejected order,
                        # it is not an order at all.
                        risk_input = self._build_propose_order_risk_input(tool_call, session)
                        
                        risk_decision = self.risk_manager.evaluate_order(
                            risk_input, current_portfolio, mode=mode # type: ignore
                        )
                        
                        if not risk_decision.allowed:
                            error = ToolError(
                                error_type="risk_rejected",
                                message=f"Risk Manager blocked {tool_call.name}: {risk_decision.reason}",
                                is_retryable=False,
                                suggested_action="Review your order parameters or portfolio risk limits.",
                                details={"violations": [v.model_dump() for v in risk_decision.violations]}
                            )
                            tool_results.append(error)
                            
                            if self.audit_writer:
                                self.audit_writer.write_event(
                                    "tool_call_blocked",
                                    run_id=run_id,
                                    iteration=i,
                                    tool_name=tool_call.name,
                                    tool_call_id=tool_call.id,
                                    status="risk_rejected",
                                    payload=risk_decision.model_dump()
                                )
                            
                            return AgentResult(
                                status="blocked",
                                iterations=iterations,
                                total_tool_calls=total_tool_calls,
                                errors=[error.message],
                                diagnostics={"risk_decision": risk_decision.model_dump()}
                            )
                    except (ValueError, TypeError) as e:
                        error = ToolError(
                            error_type="risk_rejected",
                            message=f"Risk Manager blocked {tool_call.name}: {e}",
                            is_retryable=False,
                            suggested_action="Provide complete, valid order parameters before retrying.",
                        )
                        tool_results.append(error)

                        if self.audit_writer:
                            self.audit_writer.write_event(
                                "tool_call_blocked",
                                run_id=run_id,
                                iteration=i,
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                                status="risk_rejected",
                                payload={"reason": str(e)},
                            )

                        return AgentResult(
                            status="blocked",
                            iterations=iterations,
                            total_tool_calls=total_tool_calls,
                            errors=[error.message],
                            diagnostics={"risk_decision": {"reason": str(e), "status": "blocked"}},
                        )

                    # Batch 3.2: Live analysis-only gate
                    if mode == "live":
                        analysis_result = {
                            "status": "live_analysis_only",
                            "risk_decision": risk_decision.model_dump(),
                            "message": "Risk check passed. Live order submission is deferred.",
                        }
                        tool_results.append(ToolResult(data=analysis_result, error=False))

                        if self.audit_writer:
                            self.audit_writer.write_event(
                                "tool_call_live_analysis_only",
                                run_id=run_id,
                                iteration=i,
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                                payload=analysis_result,
                            )
                        continue

                if self.audit_writer:
                    self.audit_writer.write_event(
                        "tool_call_requested",
                        run_id=run_id,
                        iteration=i,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        payload=tool_call.arguments
                    )

                result = self.tool_registry.execute(tool_call, self.guardrails, session)
                tool_results.append(result)

                if isinstance(result, UserApprovalPending):
                    if self.audit_writer:
                        self.audit_writer.write_event(
                            "approval_required",
                            run_id=run_id,
                            iteration=i,
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            payload=result.model_dump()
                        )
                    return AgentResult(
                        status="approval_required",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                        diagnostics={"approval": result.model_dump()},
                    )
                
                if isinstance(result, ToolError) and result.error_type == "risk_rejected":
                     if self.audit_writer:
                        self.audit_writer.write_event(
                            "tool_call_blocked",
                            run_id=run_id,
                            iteration=i,
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            status="risk_rejected",
                            payload={"message": result.message}
                        )
                     return AgentResult(
                        status="blocked",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                        errors=[result.message],
                    )

                if isinstance(result, ToolError) and result.error_type == "validation":
                     if self.audit_writer:
                        self.audit_writer.write_event(
                            "validation_error",
                            run_id=run_id,
                            iteration=i,
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            payload={"message": result.message}
                        )

                if self.audit_writer and isinstance(result, ToolResult):
                    self.audit_writer.write_event(
                        "tool_call_executed",
                        run_id=run_id,
                        iteration=i,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        status="success",
                        payload={"result": str(result.data)}
                    )

            # Re-create iteration with results
            iteration = IterationResult(
                index=i,
                message=llm_response.text,
                tool_calls=llm_response.tool_calls,
                tool_results=tool_results,
            )
            iterations[-1] = iteration

            # Append tool results to messages
            for tc, tr in zip(llm_response.tool_calls, tool_results):
                content = str(tr.data) if isinstance(tr, ToolResult) else tr.message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

        if self.audit_writer:
            self.audit_writer.write_event(
                "run_completed",
                run_id=run_id,
                status="max_iterations"
            )
        return AgentResult(
            status="max_iterations",
            iterations=iterations,
            total_tool_calls=total_tool_calls,
        )
