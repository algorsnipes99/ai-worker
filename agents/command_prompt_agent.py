import os
from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.command_function import CommandFunction
from functions.codebase_query_function import CodebaseQueryFunction
from .base_agent import BaseAgent
from functions.website_lookup_function import WebsiteLookupFunction

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
        registry.register(WebsiteLookupFunction())
        repo_paths = self._get_repo_paths()
        # if repo_paths:
        #     registry.register(CodebaseQueryFunction(repo_paths=repo_paths)) // will add agai in future, too slow and inaccurate
        return registry

    def _get_repo_paths(self):
        raw = os.getenv('CODEBASE_REPO_PATHS', os.getenv('CODEBASE_REPO_PATH', ''))
        return [p.strip() for p in raw.split(',') if p.strip()]
