import json
import requests
import uuid
import os
from typing import Dict, Any, List, Optional

class SummarizationAgent:
    """A specialized agent for summarizing conversations"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        
    def summarize_conversation(self, messages: List[Dict[str, Any]], 
                             summarize_first: int = 50,
                             keep_last: int = 10) -> List[Dict[str, Any]]:
        """
        Summarize a conversation by condensing early messages while preserving recent context
        
        Args:
            messages: Full conversation messages to summarize
            summarize_first: Number of early messages to summarize
            keep_last: Number of recent messages to preserve
            
        Returns:
            Condensed conversation with summary
        """
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
    
    def _truncate_conversation(self, messages: List[Dict[str, Any]], 
                              summarize_first: int, keep_last: int) -> List[Dict[str, Any]]:
        """Fallback truncation without LLM summarization"""
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
    
    def _call_deepseek(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Make authenticated API call to DeepSeek"""
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
