from typing import List, Dict, Any
from .base_compressor import BaseCompressor
from .tool_call_remover import ToolCallRemover
from .message_summarizer import MessageSummarizer


class CombinedCompressor(BaseCompressor):
    """
    Strategy 3: Remove all tool calls/responses, then summarize remaining messages.
    """

    # Initialize both sub-compressors (ToolCallRemover and MessageSummarizer).
    def __init__(self):
        super().__init__()
        self._remover = ToolCallRemover()
        self._summarizer = MessageSummarizer()

    # First strip all tool-related messages, then LLM-summarize what remains.
    # @param messages: Full conversation message list.
    # @returns: Compressed message list with tools removed and content shortened.
    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        after_removal = self._remover.compress(messages)
        return self._summarizer.compress(after_removal)
