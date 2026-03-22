from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.api_function import ApiFunction
from .base_agent import BaseAgent

class ApiAgent(BaseAgent):
    """API agent that executes plans with API calling capabilities only"""

    # Storage directory for this agent's conversation messages.
    @property
    def messages_dir(self) -> str:
        return "messages/api_agents"

    # Path to the system prompt file for this agent.
    @property
    def system_prompt_path(self) -> str:
        return "prompts/api_agent_prompt.txt"

    # Build and return a FunctionRegistry containing only the makeApiCall tool.
    def _initialize_tools(self) -> FunctionRegistry:
        registry = FunctionRegistry()
        registry.register(ApiFunction())
        return registry
