from typing import Dict, Any
from functions.function import Function

class FunctionRegistry:
    """Manages available functions"""

    # Initialize an empty registry.
    def __init__(self):
        self.functions: Dict[str, Function] = {}

    # Add a Function instance to the registry, keyed by its name.
    # @param func: The Function instance to register.
    def register(self, func: Function):
        self.functions[func.name] = func

    # Return a list of JSON schema dicts for all registered functions.
    # Used to populate the 'tools' field in DeepSeek API requests.
    # @returns: List of tool schema dicts.
    def get_schemas(self) -> list[Dict[str, Any]]:
        return [f.get_schema() for f in self.functions.values()]

    # Look up and execute a registered function by name.
    # @param name: The tool name to execute.
    # @param args: Arguments dict to pass to the function's execute() method.
    # @returns: The function's return value.
    # @raises ValueError: If no function with the given name is registered.
    def execute(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self.functions:
            raise ValueError(f"Function {name} not found")
        return self.functions[name].execute(args)
