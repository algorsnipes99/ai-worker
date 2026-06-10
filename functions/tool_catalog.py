import logging
from typing import Callable, Dict, List, TYPE_CHECKING

from functions.function import Function
from functions.function_registry import FunctionRegistry
from functions.file_read_function import FileReadFunction
from functions.file_edit_function import FileEditFunction
from functions.command_function import CommandFunction
from functions.api_function import ApiFunction
from functions.website_lookup_function import WebsiteLookupFunction
from functions.website_lookup_rendered_function import WebsiteLookupRenderedFunction
from functions.database_function import DatabaseFunction
from functions.sql_query import SQLQuery
from functions.update_sql import UpdateSQL
from functions.get_sql_table_data import GetSQLTableData
from functions.codebase_query_function import CodebaseQueryFunction
from functions.calculator_function import CalculatorFunction
from functions.folder_info_function import FolderInfoFunction
from functions.app_function import AppFunction
from functions.cursor_function import CursorFunction
from functions.keyboard_input_function import KeyboardInputFunction
from functions.network_function import NetworkScanFunction
from functions.weather_function import WeatherFunction

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent

# Maps tool name (as seen by the LLM in tool schemas) to a factory that
# builds the corresponding Function instance for a given agent.
# delegateToAgent is intentionally excluded - it requires resume GUIDs that
# aren't available at _initialize_tools() time.
TOOL_CATALOG: Dict[str, Callable[["BaseAgent"], Function]] = {
    "readFile": lambda agent: FileReadFunction(),
    "editFile": lambda agent: FileEditFunction(),
    "executeCommand": lambda agent: CommandFunction(),
    "makeApiCall": lambda agent: ApiFunction(),
    "lookupWebsite": lambda agent: WebsiteLookupFunction(),
    "lookupWebsiteRendered": lambda agent: WebsiteLookupRenderedFunction(),
    "getDatabaseSchema": lambda agent: DatabaseFunction(),
    "sql_query": lambda agent: SQLQuery(),
    "update_sql": lambda agent: UpdateSQL(),
    "get_sql_table_data": lambda agent: GetSQLTableData(),
    "codebaseQuery": lambda agent: CodebaseQueryFunction(repo_paths=agent._get_repo_paths()),
    "calculate": lambda agent: CalculatorFunction(),
    "getFolderInfo": lambda agent: FolderInfoFunction(),
    "openApplication": lambda agent: AppFunction(),
    "moveCursorTo": lambda agent: CursorFunction(),
    "keyboardInput": lambda agent: KeyboardInputFunction(),
    "scanNetwork": lambda agent: NetworkScanFunction(),
    "get_current_weather": lambda agent: WeatherFunction(),
}


# Build a FunctionRegistry from a list of tool name strings, looking each up
# in TOOL_CATALOG. Unknown tool names are logged and skipped.
# @param tool_names: List of tool name strings (e.g. ["readFile", "executeCommand"]).
# @param agent: The owning agent instance, passed to factories that need context.
# @returns: A populated FunctionRegistry.
def build_registry(tool_names: List[str], agent: "BaseAgent") -> FunctionRegistry:
    registry = FunctionRegistry()
    for name in tool_names:
        factory = TOOL_CATALOG.get(name)
        if not factory:
            logging.warning(f"Unknown tool '{name}' in available_tools, skipping")
            continue
        registry.register(factory(agent))
    return registry
