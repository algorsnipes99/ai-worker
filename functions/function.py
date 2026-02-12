from typing import Dict, Any

class Function:
    """Base class for all executable functions"""
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], 
                 needs_verification: bool = False, verification_description: str = None):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.needs_verification = needs_verification
        self.verification_description = verification_description or description

    def get_schema(self) -> Dict[str, Any]:
        """Generate JSON schema for this function"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": [k for k, v in self.parameters.items() if not v.get("optional", False)]
                }
            }
        }

    def execute(self, args: Dict[str, Any]) -> Any:
        """Execute the function with given arguments"""
        raise NotImplementedError("Subclasses must implement execute()")
