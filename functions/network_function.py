from functions.function import Function
from typing import Dict, Any, List
import socket
import subprocess
from ipaddress import ip_network

class NetworkScanFunction(Function):
    """Scan local network for devices"""

    # Register the scanNetwork tool. Requires user verification (needs_verification=True).
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

    # Iterate over all host IPs in the subnet, ping each one, and resolve hostnames for
    # those that respond.
    # @param args: Dict with 'subnet' (CIDR string) and 'timeout' (seconds per ping).
    # @returns: Dict with 'status', 'devices' (list of {ip, hostname}), and 'subnet'.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
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

    # Send a single ICMP ping to the given IP and return whether it responded.
    # Uses the Windows 'ping -n 1 -w <ms>' command.
    # @param ip: IP address string to ping.
    # @param timeout: Timeout in seconds (converted to milliseconds for the ping command).
    # @returns: True if the host responded, False otherwise.
    def _ping_host(self, ip: str, timeout: float) -> bool:
        try:
            subprocess.check_output(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
                stderr=subprocess.STDOUT
            )
            return True
        except subprocess.CalledProcessError:
            return False
