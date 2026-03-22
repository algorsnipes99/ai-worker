import json
import requests
import uuid
import os
from typing import Dict, Any, List, Optional

class SummarizationAgent:
    """A specialized agent for summarizing conversations"""

    # Initialize with a DeepSeek API key.
    # @param api_key: DeepSeek API key used for summarization calls.
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    # Condense a long conversation by LLM-summarizing the oldest messages while
    # preserving the system prompt and the most recent messages verbatim.
    # Falls back to simple truncation if the LLM call fails.
    # @param messages: Full conversation message list.
    # @param summarize_first: How many early messages (after system) to summarize.
    # @param keep_last: How many recent messages to preserve unchanged.
    # @returns: Condensed message list: [system, summary_system, ...recent_messages].
    def summarize_conversation(self, messages: List[Dict[str, Any]],
                             summarize_first: int = 50,
                             keep_last: int = 10) -> List[Dict[str, Any]]:
        if len(messages) <= summarize_first + keep_last:
            return messages  # No need to summarize

        # Separate system prompt if exists
        system_message = None
        if messages and messages[0]["role"] == "system":
            system_message = messages[0]
            content_messages = messages[1:]
        else:
            content_messages = messages

        # Split messages for processing
        messages_to_summarize = content_messages[:summarize_first]
        recent_messages = content_messages[-keep_last:]

        # Prepare summarization prompt
        summary_prompt = {
            "role": "user",
            "content": f"""Summarize the first {summarize_first} messages of this conversation concisely while preserving:
            - Key decisions and actions taken
            - Important information discovered
            - Current progress and state
            - Any constraints or requirements

            Be comprehensive but concise. Original conversation had {len(content_messages)} messages."""
        }

        # Build context for summarization
        summarization_context = []
        if system_message:
            summarization_context.append(system_message)
        summarization_context.extend(messages_to_summarize)
        summarization_context.append(summary_prompt)

        # Call LLM for summarization
        response = self._call_deepseek(summarization_context)

        if "choices" in response and response["choices"]:
            summary = response["choices"][0]["message"]["content"]

            # Build condensed conversation
            condensed_messages = []
            if system_message:
                condensed_messages.append(system_message)

            # Add summary message
            condensed_messages.append({
                "role": "system",
                "content": f"CONVERSATION SUMMARY (First {summarize_first} of {len(content_messages)} messages):\n{summary}"
            })

            # Add recent messages for continuity
            condensed_messages.extend(recent_messages)

            return condensed_messages

        # Fallback: truncate without summarization
        return self._truncate_conversation(messages, summarize_first, keep_last)

    # Fallback truncation when the LLM summarization call fails.
    # Removes early messages and inserts a truncation notice in their place.
    # @param messages: Full conversation message list.
    # @param summarize_first: Number of early messages removed.
    # @param keep_last: Number of recent messages retained.
    # @returns: Truncated message list with a truncation notice injected.
    def _truncate_conversation(self, messages: List[Dict[str, Any]],
                              summarize_first: int, keep_last: int) -> List[Dict[str, Any]]:
        system_message = messages[0] if messages and messages[0]["role"] == "system" else None
        content_messages = messages[1:] if system_message else messages

        truncated_messages = []
        if system_message:
            truncated_messages.append(system_message)

        truncated_messages.append({
            "role": "system",
            "content": f"Conversation truncated: first {summarize_first} messages removed, last {keep_last} kept"
        })
        truncated_messages.extend(content_messages[-keep_last:])

        return truncated_messages

    # Make an authenticated POST request to the DeepSeek chat completions endpoint.
    # Uses a low temperature for factual summarization output.
    # @param messages: Message list to send.
    # @returns: Parsed JSON response dict, or an error dict on failure.
    def _call_deepseek(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.3  # Lower temperature for more factual summarization
        }

        try:
            response = requests.post(self.api_url, json=data, headers=headers)
            return response.json() if response.status_code == 200 else {"error": f"API Error {response.status_code}"}
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"}
