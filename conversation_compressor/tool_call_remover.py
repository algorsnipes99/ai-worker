from typing import List, Dict, Any
from .base_compressor import BaseCompressor


class ToolCallRemover(BaseCompressor):
    """
    Strategy 1: Remove all tool call messages and their responses.
    Removes:
      - messages with role='tool' (tool responses)
      - messages that have a 'tool_calls' field (assistant invoking tools)
    """

    # Strip all tool-related messages, keeping only user, system, and plain assistant messages.
    # @param messages: Full conversation message list.
    # @returns: Filtered list with role='tool' and tool_calls messages removed.
    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            msg for msg in messages
            if msg.get('role') != 'tool' and not msg.get('tool_calls')
        ]
