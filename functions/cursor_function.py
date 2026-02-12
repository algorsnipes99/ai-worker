from functions.function import Function
from typing import Dict, Any
import pyautogui
import json

class CursorFunction(Function):
    """Move mouse cursor to specified screen position"""
    def __init__(self):
        super().__init__(
            name="moveCursorTo",
            description="Move mouse cursor to specified screen position (coordinates start from top-left)",
            parameters={
                "cursorPosX": {
                    "type": "integer", 
                    "description": "X coordinate (0 is left edge)",
                    "minimum": 0,
                    "maximum": pyautogui.size().width
                },
                "cursorPosY": {
                    "type": "integer",
                    "description": "Y coordinate (0 is top edge)", 
                    "minimum": 0,
                    "maximum": pyautogui.size().height
                }
            }
        )

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Safely move cursor to position"""
        try:
            # Enable fail-safe (move to corner to abort)
            pyautogui.FAILSAFE = True
            pyautogui.moveTo(args["cursorPosX"], args["cursorPosY"], duration=0.25)
            return {
                "status": "success",
                "message": f"Moved cursor to ({args['cursorPosX']}, {args['cursorPosY']})",
                "screen_size": pyautogui.size()
            }
        except Exception as e:
            print(f"\n[DEBUG] Sending request to Ollama: {json.dumps(e, indent=2)}")
            return {
                "status": "error",
                "message": str(e),
                "screen_size": pyautogui.size()
            }
