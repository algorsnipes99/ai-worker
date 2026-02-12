from functions.function import Function
from typing import Dict, Any, List
import socket
import subprocess
from ipaddress import ip_network

class NetworkScanFunction(Function):
    """Scan local network for devices"""
    def __init__(self):
        super().__init__(
            name="scanNetwork",
            description="Scan local network for active devices and their hostnames",
            needs_verification=True,
            verification_description="Scan your local network for connected devices",
            parameters={
                "subnet": {
                    "type": "string", 
                    "description": "Network subnet to scan (e.g. '192.168.1.0/24')",
                    "default": "192.168.1.0/24"
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for each ping",
                    "default": 0.5
                }
            }
        )

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute network scan"""
        try:
            network = ip_network(args.get("subnet", "192.168.1.0/24"))
            timeout = float(args.get("timeout", 0.5))
            
            devices = []
            for ip in network.hosts():
                ip_str = str(ip)
                if self._ping_host(ip_str, timeout):
                    try:
                        hostname = socket.gethostbyaddr(ip_str)[0]
                    except socket.herror:
                        hostname = "Unknown"
                    devices.append({"ip": ip_str, "hostname": hostname})
            
            return {
                "status": "success",
                "devices": devices,
                "subnet": str(network)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _ping_host(self, ip: str, timeout: float) -> bool:
        """Check if host is reachable"""
        try:
            subprocess.check_output(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
                stderr=subprocess.STDOUT
            )
            return True
        except subprocess.CalledProcessError:
            return False
