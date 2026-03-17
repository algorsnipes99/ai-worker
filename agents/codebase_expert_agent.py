import os
from functions.function_registry import FunctionRegistry
from functions.codebase_query_function import CodebaseQueryFunction
from .base_agent import BaseAgent


class CodebaseExpertAgent(BaseAgent):
    """Agent specialised in answering questions about indexed codebases using RAG"""

    @property
    def messages_dir(self) -> str:
        return "messages/codebase_expert_agents"

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

    def _initialize_tools(self) -> FunctionRegistry:
        registry = FunctionRegistry()
        raw = os.getenv('CODEBASE_REPO_PATHS', os.getenv('CODEBASE_REPO_PATH', ''))
        repo_paths = [p.strip() for p in raw.split(',') if p.strip()] or self.DEFAULT_REPO_PATHS
        registry.register(CodebaseQueryFunction(repo_paths=repo_paths))
        return registry
