import subprocess
from typing import Dict, Any
from functions.function import Function

class CommandFunction(Function):
    """Executes system commands"""

    # Register the executeCommand tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="executeCommand",
            description="Executes a system command and returns the output. Do NOT use to search or find files/code in project repositories — use codebaseQuery for that.",
            parameters={
                "command": {
                    "type": "string",
                    "description": "The command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory to execute in",
                    "default": ""
                }
            }
        )

    # Run the shell command via subprocess and return its exit code, stdout, and stderr.
    # @param args: Dict with 'command' (required), 'timeout' (default 30s), 'working_dir' (optional).
    # @returns: Dict with 'exit_code', 'stdout', 'stderr', or 'error' on timeout/exception.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        command = args["command"]
        timeout = args.get("timeout", 30)
        working_dir = args.get("working_dir", "")
        print('running command '+ command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir if working_dir else None,
                timeout=timeout,
                capture_output=True,
                text=True
            )

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout} seconds"}
        except Exception as e:
            return {"error": str(e)}
