from functions.function import Function
from typing import Dict, Any
import subprocess
import os

class AppFunction(Function):
    """Open specified Windows application"""

    # Register the openApplication tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="openApplication",
            description="Open a Windows application by its name",
            parameters={
                "appName": {
                    "type": "string",
                    "description": "Name of the application to open (e.g. 'notepad', 'chrome')"
                }
            }
        )

    # Launch a Windows application by name, falling back to the 'start' command if direct
    # Popen fails.
    # @param args: Dict with 'appName' (required).
    # @returns: Dict with 'status' and 'message'.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Try direct execution first
            try:
                subprocess.Popen(args["appName"], shell=True)
                return {"status": "success", "message": f"Opened {args['appName']}"}
            except Exception:
                # Try using start command for Windows
                os.system(f'start "" "{args["appName"]}"')
                return {"status": "success", "message": f"Attempted to open {args['appName']}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
