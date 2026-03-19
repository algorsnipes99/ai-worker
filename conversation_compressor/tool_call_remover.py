from typing import List, Dict, Any
from .base_compressor import BaseCompressor


class ToolCallRemover(BaseCompressor):
    """
    Strategy 1: Remove all tool call messages and their responses.
    Removes:
      - messages with role='tool' (tool responses)
      - messages that have a 'tool_calls' field (assistant invoking tools)
    """

    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            msg for msg in messages
            if msg.get('role') != 'tool' and not msg.get('tool_calls')
        ]
