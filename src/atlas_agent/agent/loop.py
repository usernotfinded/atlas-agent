from __future__ import annotations

import logging
from typing import Any, Union

from atlas_agent.agent.result import AgentResult, IterationResult
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.core.types import Session, UserApprovalPending
from atlas_agent.providers.base import AIProvider
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot
from atlas_agent.safety.kill_switch import AdvancedKillSwitch
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.spec import LLMResponse, ToolCall, ToolResult, ToolError, GuardrailChain


class DefaultGuardrailChain:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def evaluate(self, tool_call: ToolCall, session: Session) -> Union[ToolResult, ToolError, UserApprovalPending, None]:
        try:
            tool = self.registry.get_tool(tool_call.name)
        except KeyError:
            return None
            
        if tool.approval_gated:
             return UserApprovalPending(
                approval_id=f"approve_{tool_call.id}",
                notification=f"Approval required for tool {tool.name}",
                timeout_seconds=3600
            )
        return None


class AgentLoop:
    def __init__(
        self,
        provider: AIProvider,
        tool_registry: ToolRegistry,
        guardrails: GuardrailChain,
        max_iterations: int = 10,
        max_tool_calls: int = 50,
        audit_writer: AuditWriter | None = None,
        risk_manager: RiskManager | None = None,
        kill_switch: AdvancedKillSwitch | None = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.guardrails = guardrails
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.audit_writer = audit_writer
        self.risk_manager = risk_manager
        self.kill_switch = kill_switch

    def run(
        self,
        user_objective: str,
        session: Session,
        system_prompt: str,
        mode: str = "paper",
        run_id: str | None = None,
        portfolio_snapshot: PortfolioSnapshot | None = None,
    ) -> AgentResult:
        run_id = run_id or f"run_{int(session.turn_count)}_{session.id}"
        if self.audit_writer:
            self.audit_writer.write_event(
                "run_started",
                run_id=run_id,
                payload={"user_objective": user_objective, "mode": mode}
            )

        iterations = []
        messages = [{"role": "user", "content": user_objective}]
        total_tool_calls = 0
        errors = []

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
            except Exception as e:
                logging.error(f"Provider error: {e}")
                if self.audit_writer:
                    self.audit_writer.write_event(
                        "run_failed",
                        run_id=run_id,
                        iteration=i,
                        status="error",
                        payload={"error": str(e)}
                    )
                return AgentResult(
                    status="error",
                    errors=[str(e)],
                    iterations=iterations,
                    total_tool_calls=total_tool_calls,
                )

            if self.audit_writer:
                self.audit_writer.write_event(
                    "provider_response",
                    run_id=run_id,
                    iteration=i,
                    payload={
                        "text": llm_response.text,
                        "tool_call_count": len(llm_response.tool_calls),
                        "is_final": llm_response.is_final
                    }
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
                # Store tool calls in the format expected by most providers
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": str(tc.arguments) # Simplified for storage
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

            # 2. Execute tool calls
            tool_results = []
            for tool_call in llm_response.tool_calls:
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

                total_tool_calls += 1
                
                # 1. Kill Switch Check
                if self.kill_switch:
                    kill_decision = self.kill_switch.evaluate()
                    if not kill_decision.allowed:
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
                            diagnostics={"kill_switch": kill_decision.model_dump()}
                        )

                # 2. Risk Gating
                tool_spec = None
                try:
                    tool_spec = self.tool_registry.get_tool(tool_call.name)
                except KeyError:
                    pass

                if tool_spec and tool_spec.risk_gated and self.risk_manager:
                    current_portfolio = portfolio_snapshot or PortfolioSnapshot(
                        cash=10000.0, equity=10000.0, total_exposure=0.0
                    )
                    
                    args = tool_call.arguments or {}
                    try:
                        risk_input = OrderRiskInput(
                            symbol=args.get("symbol", "UNKNOWN"),
                            side=args.get("side", "buy"),
                            quantity=float(args.get("quantity", 0)),
                            price=float(args.get("limit_price") or args.get("price") or 0.0),
                            notional=float(args.get("quantity", 0)) * float(args.get("limit_price") or args.get("price") or 1.0),
                            confidence=getattr(session, "last_confidence", None),
                            stop_loss=args.get("stop_loss")
                        )
                        
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
                        logging.warning(f"Failed to create RiskInput from tool call {tool_call.name}: {e}")

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
