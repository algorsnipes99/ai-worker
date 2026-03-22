import os
from functions.function_registry import FunctionRegistry
from functions.codebase_query_function import CodebaseQueryFunction
from .base_agent import BaseAgent


class CodebaseExpertAgent(BaseAgent):
    """Agent specialised in answering questions about indexed codebases using RAG"""

    # Storage directory for this agent's conversation messages.
    @property
    def messages_dir(self) -> str:
        return "messages/codebase_expert_agents"

    # Path to the system prompt file for this agent.
    @property
    def system_prompt_path(self) -> str:
        return "prompts/codebase_expert_prompt.txt"

    DEFAULT_REPO_PATHS = [
        r'C:\dev\mqx\mqx_library',
        r'C:\dev\mqx\mqx_sim',
        r'C:\dev\mqx\mqx_admin',
        r'C:\dev\mqx\mqx_api',
        r'C:\dev\mqx\mqx_app',
    ]

    # Build and return a FunctionRegistry with the codebaseQuery RAG tool.
    # Repo paths are read from CODEBASE_REPO_PATHS / CODEBASE_REPO_PATH env vars,
    # falling back to DEFAULT_REPO_PATHS if neither is set.
    def _initialize_tools(self) -> FunctionRegistry:
        registry = FunctionRegistry()
        raw = os.getenv('CODEBASE_REPO_PATHS', os.getenv('CODEBASE_REPO_PATH', ''))
        repo_paths = [p.strip() for p in raw.split(',') if p.strip()] or self.DEFAULT_REPO_PATHS
        registry.register(CodebaseQueryFunction(repo_paths=repo_paths))
        return registry
