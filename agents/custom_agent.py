from functions.function_registry import FunctionRegistry
from .base_agent import BaseAgent

class CustomAgent(BaseAgent):
    """Agent whose tool set is configured dynamically via available_tools"""

    # Default tool set used when no available_tools are provided.
    DEFAULT_TOOLS = ["executeCommand"]

    # Storage directory for this agent's conversation messages.
    @property
    def messages_dir(self) -> str:
        return "messages/custom_agents"

    # Path to the system prompt file for this agent.
    @property
    def system_prompt_path(self) -> str:
        return "prompts/custom_agent_prompt.txt"

    # Build and return a FunctionRegistry from self.available_tools, falling back
    # to DEFAULT_TOOLS if none were provided.
    def _initialize_tools(self) -> FunctionRegistry:
        return self._build_registry_from_available_tools(default=self.DEFAULT_TOOLS)
