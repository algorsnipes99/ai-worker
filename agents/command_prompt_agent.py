from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.command_function import CommandFunction
from .base_agent import BaseAgent

class CommandPromptAgent(BaseAgent):
    """Command prompt agent that executes plans with command execution capabilities only"""
    
    @property
    def messages_dir(self) -> str:
        return "messages/command_prompt_agents"

    @property
    def system_prompt_path(self) -> str:
        return "prompts/command_prompt_prompt.txt"

    def _initialize_tools(self) -> FunctionRegistry:
        """Initialize and register command execution tools only"""
        registry = FunctionRegistry()
        registry.register(CommandFunction())
        return registry
