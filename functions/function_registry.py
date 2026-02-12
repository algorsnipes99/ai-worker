from typing import Dict, Any
from functions.function import Function

class FunctionRegistry:
    """Manages available functions"""
    def __init__(self):
        self.functions: Dict[str, Function] = {}

    def register(self, func: Function):
        """Register a new function"""
        self.functions[func.name] = func

    def get_schemas(self) -> list[Dict[str, Any]]:
        """Get all function schemas"""
        return [f.get_schema() for f in self.functions.values()]

    def execute(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a registered function"""
        if name not in self.functions:
            raise ValueError(f"Function {name} not found")
        return self.functions[name].execute(args)
