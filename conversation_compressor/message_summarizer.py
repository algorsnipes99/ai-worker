import json
from typing import List, Dict, Any
from openai import OpenAI
import os
from .base_compressor import BaseCompressor


class MessageSummarizer(BaseCompressor):
    """
    Strategy 2: Summarize each message as much as possible using the LLM.
    Iterates over every message and replaces its content with a shortened version.
    Tool call/response messages are left structurally intact but their content is shortened.
    """

    def __init__(self):
        super().__init__()
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.client = OpenAI(
            api_key=self.api_key,
            base_url='https://api.deepseek.com'
        )

    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        compressed = []
        for msg in messages:
            compressed.append(self._summarize_message(msg))
        return compressed

    def _summarize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of the message with shortened content"""
        msg = dict(message)

        # Summarize plain text content
        if isinstance(msg.get('content'), str) and msg['content'].strip():
            msg['content'] = self._shorten(msg['content'])

        # Shorten tool call arguments
        if msg.get('tool_calls'):
            shortened_calls = []
            for tc in msg['tool_calls']:
                tc_copy = dict(tc)
                if tc_copy.get('function', {}).get('arguments'):
                    try:
                        args = json.loads(tc_copy['function']['arguments'])
                        summary = self._shorten(json.dumps(args))
                        tc_copy = {**tc_copy, 'function': {**tc_copy['function'], 'arguments': summary}}
                    except (json.JSONDecodeError, TypeError):
                        pass
                shortened_calls.append(tc_copy)
            msg['tool_calls'] = shortened_calls

        return msg

    def _shorten(self, text: str) -> str:
        """Ask the LLM to shorten a piece of text as much as possible"""
        try:
            response = self.client.chat.completions.create(
                model='deepseek-chat',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'You are a conversation compressor. Shorten the following message '
                            'as much as possible while preserving all key facts, decisions, and '
                            'outcomes. Remove filler words, redundancy, and verbose explanations. '
                            'Return only the shortened text, nothing else.'
                        )
                    },
                    {'role': 'user', 'content': text}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # Fall back to original text if LLM call fails
            return text
