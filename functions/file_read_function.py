import os
from typing import Dict, Any
from functions.function import Function

class FileReadFunction(Function):
    """Reads content from a file"""
    
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
