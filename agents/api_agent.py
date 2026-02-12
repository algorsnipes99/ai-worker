from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.api_function import ApiFunction
from .base_agent import BaseAgent

class ApiAgent(BaseAgent):
    """API agent that executes plans with API calling capabilities only"""
    
    @property
    def messages_dir(self) -> str:
        return "messages/api_agents"

    @property
    def system_prompt_path(self) -> str:
        return "prompts/api_agent_prompt.txt"

    def _initialize_tools(self) -> FunctionRegistry:
        """Initialize and register API calling tools only"""
        registry = FunctionRegistry()
        registry.register(ApiFunction())
        return registry
