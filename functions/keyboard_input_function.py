import time
import win32api
import win32con
import win32gui
from typing import Dict, Any
from functions.function import Function

class KeyboardInputFunction(Function):
    """Simulates keyboard input"""
    
    def __init__(self):
        super().__init__(
            name="keyboardInput",
            description="Simulates keyboard input",
            parameters={
                "text": {
                    "type": "string",
                    "description": "Text to type"
                },
                "window_title": {
                    "type": "string",
                    "description": "Optional window title to target",
                    "default": None
                },
                "delay": {
                    "type": "number",
                    "description": "Delay between keystrokes in seconds",
                    "default": 0.05
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Require confirmation before sending",
                    "default": True
                }
            }
        )

    def _set_foreground_window(self, window_title: str) -> bool:
        """Bring specified window to foreground"""
        window = win32gui.FindWindow(None, window_title)
        if window:
            win32gui.SetForegroundWindow(window)
            return True
        return False

    def _send_key(self, key: str):
        """Send a single key press"""
        if len(key) == 1:
            # Regular character
            win32api.keybd_event(ord(key.upper()), 0, 0, 0)
            win32api.keybd_event(ord(key.upper()), 0, win32con.KEYEVENTF_KEYUP, 0)
        else:
            # Special keys would be handled here
            pass

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        text = args["text"]
        window_title = args.get("window_title")
        delay = args.get("delay", 0.05)
        confirm = args.get("confirm", True)

        if confirm:
            return {
                "status": "confirmation_required",
                "message": f"About to type: '{text}'",
                "confirm_action": True
            }

        try:
            if window_title:
                if not self._set_foreground_window(window_title):
                    return {"error": f"Window not found: {window_title}"}

            for char in text:
                self._send_key(char)
                time.sleep(delay)

            return {"status": "success", "characters_sent": len(text)}
        except Exception as e:
            return {"error": str(e)}
