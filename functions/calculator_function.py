from functions.function import Function
from typing import Dict, Any

class CalculatorFunction(Function):
    """Evaluate math expressions"""

    # Register the calculate tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="calculate",
            description="Evaluate a math expression",
            parameters={
                "expression": {"type": "string", "description": "Math expression to evaluate"}
            }
        )

    # Safely evaluate a math expression using AST validation.
    # Only allows numeric literals and basic binary/unary operators (+, -, *, /, ()).
    # @param args: Dict with 'expression' (required).
    # @returns: Dict with 'result', 'status', 'expression', or 'error' on invalid input.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Validate expression contains only allowed characters
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in args["expression"]):
                raise ValueError("Expression contains invalid characters")

            # Use ast.literal_eval for safer evaluation
            import ast
            parsed = ast.parse(args["expression"], mode='eval')

            # Only allow basic math operations
            for node in ast.walk(parsed):
                if not isinstance(node, (ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp)):
                    raise ValueError("Only basic math operations are allowed")

            result = eval(compile(parsed, '<string>', 'eval'), {"__builtins__": None}, {})
            return {
                "result": result,
                "status": "success",
                "expression": args["expression"]
            }
        except Exception as e:
            return {
                "error": str(e),
                "status": "error",
                "expression": args["expression"]
            }
