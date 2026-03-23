import platform
import socket
import os


def get_machine_id() -> str | None:
    system = platform.system()

    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            )
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return value
        except Exception:
            return None

    elif system == "Linux":
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
            except Exception:
                pass

    return None


def get_machine_name() -> str | None:
    try:
        return socket.gethostname()
    except Exception:
        return None
