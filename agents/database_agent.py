from typing import Dict
from functions.function_registry import FunctionRegistry
from functions.database_function import DatabaseFunction
from functions.get_sql_table_data import GetSQLTableData
from functions.sql_query import SQLQuery
from functions.update_sql import UpdateSQL
from .base_agent import BaseAgent

class DatabaseAgent(BaseAgent):
    """Database agent that executes plans with database operations capabilities"""
    
    @property
    def messages_dir(self) -> str:
        return "messages/database_agents"

    @property
    def system_prompt_path(self) -> str:
        return "prompts/database_agent_prompt.txt"

    def _initialize_tools(self) -> FunctionRegistry:
        """Initialize and register database tools only"""
        registry = FunctionRegistry()
        registry.register(DatabaseFunction())
        registry.register(GetSQLTableData())
        registry.register(SQLQuery())
        registry.register(UpdateSQL())
        return registry
