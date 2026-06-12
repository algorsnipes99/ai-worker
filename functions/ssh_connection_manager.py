import paramiko
from typing import Optional, Dict

# Module-level connection pool shared across all SSH tool instances.
# Keyed by session_id (f"{host}:{port}"), holds live paramiko.SSHClient objects.
_connections: Dict[str, paramiko.SSHClient] = {}


class SSHConnectionManager:
    """Manages SSH connections as a singleton pool keyed by session_id."""

    @staticmethod
    def connect(host: str, port: int, username: str,
                password: Optional[str] = None,
                key_file_path: Optional[str] = None) -> str:
        """
        Open a new SSH connection and store it in the pool.
        Returns a session_id string (f"{host}:{port}").
        If a connection to this host:port already exists, it is closed first.
        """
        session_id = f"{host}:{port}"

        # Close existing connection if reconnecting
        existing = _connections.pop(session_id, None)
        if existing:
            try:
                existing.close()
            except Exception:
                pass

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            key_filename=key_file_path,
            timeout=15
        )
        _connections[session_id] = client
        return session_id

    @staticmethod
    def execute(session_id: str, command: str,
                working_directory: Optional[str] = None) -> dict:
        """
        Execute a command on an active SSH session.
        Returns dict with stdout, stderr, exit_code.
        Raises ValueError if session_id is not in the pool.
        """
        client = SSHConnectionManager._get_connection(session_id)

        if working_directory:
            command = f"cd {working_directory} && {command}"

        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        exit_code = stdout.channel.recv_exit_status()

        return {
            "stdout": stdout.read().decode("utf-8", errors="replace"),
            "stderr": stderr.read().decode("utf-8", errors="replace"),
            "exit_code": exit_code
        }

    @staticmethod
    def disconnect(session_id: str) -> bool:
        """
        Close and remove an SSH connection from the pool.
        Returns True if a connection was closed, False if session_id didn't exist.
        """
        client = _connections.pop(session_id, None)
        if client:
            try:
                client.close()
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def get_active_sessions() -> Dict[str, paramiko.SSHClient]:
        """Return a copy of all active session IDs and their clients."""
        return dict(_connections)

    @staticmethod
    def _get_connection(session_id: str) -> paramiko.SSHClient:
        client = _connections.get(session_id)
        if not client:
            raise ValueError(
                f"No active SSH session found for '{session_id}'. "
                f"Use sshConnect(action='connect', ...) to open a connection first. "
                f"Active sessions: {list(_connections.keys())}"
            )
        return client
