from typing import Dict, Any
from functions.function import Function
from functions.ssh_connection_manager import SSHConnectionManager


class SshConnectFunction(Function):
    """Connect to or disconnect from an SSH server."""

    def __init__(self):
        super().__init__(
            name="sshConnect",
            description=(
                "Connect to or disconnect from an SSH server. "
                "Use action='connect' to authenticate and get a session_id, "
                "or action='disconnect' to close an existing session. "
                "The returned session_id (format 'host:port') must be passed to sshExecute "
                "for remote command execution on that server."
            ),
            parameters={
                "action": {
                    "type": "string",
                    "enum": ["connect", "disconnect"],
                    "description": "'connect' to open a new SSH session, 'disconnect' to close an existing one"
                },
                "host": {
                    "type": "string",
                    "description": "SSH server hostname or IP address (required for connect, not needed for disconnect)"
                },
                "port": {
                    "type": "integer",
                    "description": "SSH server port",
                    "default": 22
                },
                "username": {
                    "type": "string",
                    "description": "SSH login username (required for connect)"
                },
                "password": {
                    "type": "string",
                    "description": "SSH login password (optional if using key_file_path)"
                },
                "key_file_path": {
                    "type": "string",
                    "description": "Path to an SSH private key file for key-based authentication (optional if using password)"
                },
                "session_id": {
                    "type": "string",
                    "description": "The session_id returned from a previous connect call (required for disconnect)"
                }
            }
        )

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = args.get("action", "connect")

        if action == "disconnect":
            session_id = args.get("session_id", "")
            if not session_id:
                return {"status": "error", "message": "session_id is required for disconnect"}
            closed = SSHConnectionManager.disconnect(session_id)
            if closed:
                return {"status": "disconnected", "session_id": session_id}
            else:
                return {"status": "error", "message": f"No active session found for '{session_id}'"}

        # action == "connect"
        host = args.get("host", "")
        if not host:
            return {"status": "error", "message": "host is required for connect"}
        port = args.get("port", 22)
        username = args.get("username", "")
        if not username:
            return {"status": "error", "message": "username is required for connect"}
        password = args.get("password")
        key_file_path = args.get("key_file_path")

        if not password and not key_file_path:
            return {"status": "error", "message": "Either password or key_file_path is required for authentication"}

        try:
            session_id = SSHConnectionManager.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                key_file_path=key_file_path
            )
            return {
                "status": "connected",
                "session_id": session_id,
                "host": host,
                "port": port,
                "username": username
            }
        except Exception as e:
            return {"status": "error", "message": f"SSH connection failed: {str(e)}"}


class SshExecuteFunction(Function):
    """Execute a command on an active SSH session."""

    def __init__(self):
        super().__init__(
            name="sshExecute",
            description=(
                "Execute a shell command on a remote SSH server using an active session. "
                "Use sshConnect first to obtain a session_id. "
                "Supports any remote command: ls, cat, cd, tail, grep, find, pwd, etc. "
                "For reading remote files, use 'cat <path>'. For navigating, use 'cd <dir> && <command>' "
                "or pass the working_directory parameter."
            ),
            parameters={
                "session_id": {
                    "type": "string",
                    "description": "The session_id returned from a previous sshConnect call"
                },
                "command": {
                    "type": "string",
                    "description": "The shell command to execute on the remote server"
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional working directory to cd into before running the command"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds for the command execution",
                    "default": 30
                }
            }
        )

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = args.get("session_id", "")
        if not session_id:
            return {"status": "error", "message": "session_id is required. Use sshConnect to get one first."}

        command = args.get("command", "")
        if not command:
            return {"status": "error", "message": "command is required"}

        working_directory = args.get("working_directory")

        try:
            result = SSHConnectionManager.execute(
                session_id=session_id,
                command=command,
                working_directory=working_directory
            )
            return {
                "status": "success",
                "session_id": session_id,
                "command": command,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"]
            }
        except ValueError as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": f"Command execution failed: {str(e)}"}
