import os
from typing import Dict, Any
from functions.function import Function
from datetime import datetime

class FolderInfoFunction(Function):
    """Gets detailed information about folder contents"""
    
    def __init__(self):
        super().__init__(
            name="getFolderInfo",
            description="Gets information about files in a directory including names, types, and sizes",
            parameters={
                "path": {
                    "type": "string",
                    "description": "Path to the directory to scan"
                },
                "recursive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to scan subdirectories recursively"
                },
                "include_hidden": {
                    "type": "boolean", 
                    "default": False,
                    "description": "Whether to include hidden files"
                }
            }
        )
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args["path"]
        recursive = args.get("recursive", False)
        include_hidden = args.get("include_hidden", False)

        if not os.path.isdir(path):
            return {"error": f"Path is not a directory: {path}"}
        
        try:
            return {
                "path": path,
                "files": self._scan_directory(path, recursive, include_hidden)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _scan_directory(self, path: str, recursive: bool, include_hidden: bool) -> list:
        files = []
        with os.scandir(path) as entries:
            for entry in entries:
                if not include_hidden and entry.name.startswith('.'):
                    continue
                    
                file_info = {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else 0,
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
                }
                
                files.append(file_info)
                
                if recursive and entry.is_dir():
                    files.extend(self._scan_directory(
                        entry.path, recursive, include_hidden
                    ))
        
        return files
