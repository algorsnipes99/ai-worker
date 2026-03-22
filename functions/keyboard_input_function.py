import time
import win32api
import win32con
import win32gui
from typing import Dict, Any
from functions.function import Function

class KeyboardInputFunction(Function):
    """Simulates keyboard input"""

    # Register the keyboardInput tool with its parameter schema.
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

    # Find a window by title and bring it to the foreground using the Win32 API.
    # @param window_title: The exact window title to search for.
    # @returns: True if the window was found and focused, False otherwise.
    def _set_foreground_window(self, window_title: str) -> bool:
        window = win32gui.FindWindow(None, window_title)
        if window:
            win32gui.SetForegroundWindow(window)
            return True
        return False

    # Simulate a single key press and release via win32api keybd_event.
    # Only handles single printable characters; special keys are a no-op placeholder.
    # @param key: Single character string to send.
    def _send_key(self, key: str):
        if len(key) == 1:
            # Regular character
            win32api.keybd_event(ord(key.upper()), 0, 0, 0)
            win32api.keybd_event(ord(key.upper()), 0, win32con.KEYEVENTF_KEYUP, 0)
        else:
            # Special keys would be handled here
            pass

    # Type the given text character by character with a configurable delay.
    # If confirm=True (default), returns a confirmation_required response instead of typing.
    # Optionally focuses a target window before sending keystrokes.
    # @param args: Dict with 'text', optional 'window_title', 'delay', and 'confirm'.
    # @returns: Dict with 'status' and result details, or 'error' if window not found.
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
