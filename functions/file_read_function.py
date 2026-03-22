import os
from typing import Dict, Any
from functions.function import Function

class FileReadFunction(Function):
    """Reads content from a file"""

    # Register the readFile tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="readFile",
            description="Reads content from a file at the specified path",
            parameters={
                "path": {
                    "type": "string",
                    "description": "Path to the file to read"
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8"
                },
                "lines": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional line numbers to read (1-based)"
                }
            }
        )

    # Read and return file content, optionally filtering to specific line numbers.
    # @param args: Dict with 'path' (required), 'encoding' (default utf-8), 'lines' (optional 1-based list).
    # @returns: Dict with 'content' string, or 'error' if file not found or read fails.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args["path"]
        encoding = args.get("encoding", "utf-8")
        lines = args.get("lines")
        print('reading file '+ path)

        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

        try:
            with open(path, 'r', encoding=encoding) as f:
                if lines:
                    content = []
                    for i, line in enumerate(f, 1):
                        if i in lines:
                            content.append(line)
                    return {"content": "".join(content)}
                else:
                    return {"content": f.read()}
        except Exception as e:
            return {"error": str(e)}
