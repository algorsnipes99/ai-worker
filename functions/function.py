from typing import Dict, Any

class Function:
    """Base class for all executable functions"""

    # Initialize a function with its LLM-facing metadata and verification flag.
    # @param name: Tool name used in the JSON schema and FunctionRegistry key.
    # @param description: Shown to the LLM to explain when to call this tool.
    # @param parameters: Dict of parameter name → JSON Schema property dict.
    # @param needs_verification: If True, PermissionManager must approve before execution.
    # @param verification_description: Human-readable description for the permission prompt.
    def __init__(self, name: str, description: str, parameters: Dict[str, Any],
                 needs_verification: bool = False, verification_description: str = None):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.needs_verification = needs_verification
        self.verification_description = verification_description or description

    # Generate the JSON schema dict that the DeepSeek API expects for this tool.
    # Required parameters are inferred from those without optional=True.
    # @returns: A 'type: function' schema dict compatible with the OpenAI tool-calling format.
    def get_schema(self) -> Dict[str, Any]:
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

    # Execute the function with the given arguments. Must be overridden by subclasses.
    # @param args: Dict of argument name → value as parsed from the LLM's tool call.
    # @returns: Any result value; will be JSON-serialized and returned to the LLM.
    def execute(self, args: Dict[str, Any]) -> Any:
        raise NotImplementedError("Subclasses must implement execute()")
