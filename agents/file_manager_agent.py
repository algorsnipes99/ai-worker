from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.file_read_function import FileReadFunction
from functions.file_edit_function import FileEditFunction
from functions.command_function import CommandFunction
from functions.folder_info_function import FolderInfoFunction
from functions.website_lookup_function import WebsiteLookupFunction
from functions.website_lookup_rendered_function import WebsiteLookupRenderedFunction
from .base_agent import BaseAgent

class FileManagerAgent(BaseAgent):
    """File management agent that executes plans with file operation capabilities only"""
    
    @property
    def messages_dir(self) -> str:
        return "messages/file_manager_agents"

    @property
    def system_prompt_path(self) -> str:
        return "prompts/file_manager_prompt.txt"

    def _initialize_tools(self) -> FunctionRegistry:
        """Initialize and register file management tools only"""
        registry = FunctionRegistry()
        registry.register(FileReadFunction())
        registry.register(FileEditFunction())
        registry.register(CommandFunction())
        registry.register(FolderInfoFunction())
        registry.register(WebsiteLookupFunction())
        registry.register(WebsiteLookupRenderedFunction())
        return registry
