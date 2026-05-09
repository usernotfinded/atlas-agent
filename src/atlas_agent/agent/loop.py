from __future__ import annotations

import logging
from typing import Any, Union

from atlas_agent.agent.result import AgentResult, IterationResult
from atlas_agent.core.types import Session, UserApprovalPending
from atlas_agent.providers.base import AIProvider
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
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.guardrails = guardrails
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls

    def run(
        self,
        user_objective: str,
        session: Session,
        system_prompt: str,
        mode: str = "paper",
    ) -> AgentResult:
        iterations = []
        messages = [{"role": "user", "content": user_objective}]
        total_tool_calls = 0
        errors = []

        for i in range(self.max_iterations):
            # 1. Get model response
            try:
                llm_response = self.provider.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=self.tool_registry.describe_for_model(self.provider.capabilities()),
                )
            except Exception as e:
                logging.error(f"Provider error: {e}")
                return AgentResult(
                    status="error",
                    errors=[str(e)],
                    iterations=iterations,
                    total_tool_calls=total_tool_calls,
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
                    return AgentResult(
                        status="max_tool_calls",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                    )

                total_tool_calls += 1
                result = self.tool_registry.execute(tool_call, self.guardrails, session)
                tool_results.append(result)

                if isinstance(result, UserApprovalPending):
                    return AgentResult(
                        status="approval_required",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                        diagnostics={"approval": result.model_dump()},
                    )
                
                if isinstance(result, ToolError) and result.error_type == "risk_rejected":
                     return AgentResult(
                        status="blocked",
                        iterations=iterations,
                        total_tool_calls=total_tool_calls,
                        errors=[result.message],
                    )

            # Update iteration with results
            # Note: iteration was already appended, but dataclass is frozen.
            # We'll need to create a new IterationResult or use a list of results and then 
            # rebuild at the end if we want it fully frozen.
            # For now let's use a non-frozen IterationResult or just mutate it if possible.
            # Wait, IterationResult was defined with frozen=True.
            
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

        return AgentResult(
            status="max_iterations",
            iterations=iterations,
            total_tool_calls=total_tool_calls,
        )
