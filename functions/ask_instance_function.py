from typing import Dict, Any, List, Optional, TYPE_CHECKING
from functions.function import Function

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent

MAX_TRANSCRIPT_CHARS = 20000
TOOL_RESULT_PREVIEW_CHARS = 500

ASK_INSTANCE_SYSTEM_PROMPT = """You are a one-shot research assistant. Another AI assistant, in a different conversation, is asking you a question about the conversation transcript below. Answer concisely and accurately using ONLY information from that transcript. If the answer isn't present, say so explicitly — do not guess.

=== TRANSCRIPT (conversation {instance_id}) ===
{transcript}
=== END TRANSCRIPT ==="""


# Render a single message as one transcript line, or None if it should be skipped.
# System messages are skipped (they belong to the other conversation, not this question).
# Tool results are truncated to TOOL_RESULT_PREVIEW_CHARS.
def _format_message(msg: Dict[str, Any]) -> Optional[str]:
    role = msg.get("role")
    if role == "system":
        return None
    if role == "tool":
        content = str(msg.get("content", ""))
        if len(content) > TOOL_RESULT_PREVIEW_CHARS:
            content = content[:TOOL_RESULT_PREVIEW_CHARS] + "... [truncated]"
        return f"[tool result]: {content}"
    if role == "assistant":
        content = msg.get("content")
        if content:
            return f"assistant: {content}"
        tool_calls = msg.get("tool_calls") or []
        names = ", ".join(tc.get("function", {}).get("name", "?") for tc in tool_calls)
        return f"assistant: [called tool: {names}]" if names else None
    if role == "user":
        return f"user: {msg.get('content', '')}"
    return None


# Build a bounded text transcript from a conversation's messages, dropping the
# oldest lines first if the transcript exceeds MAX_TRANSCRIPT_CHARS.
# @param messages: Full message array from the target conversation.
# @returns: Transcript string (possibly prefixed with an omission notice).
def _build_transcript(messages: List[Dict[str, Any]]) -> str:
    lines = [line for line in (_format_message(m) for m in messages) if line]
    transcript = "\n".join(lines)
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript

    kept: List[str] = []
    total = 0
    for line in reversed(lines):
        total += len(line) + 1
        if total > MAX_TRANSCRIPT_CHARS:
            break
        kept.append(line)
    kept.reverse()
    return "[... earlier messages omitted ...]\n" + "\n".join(kept)


class AskInstanceFunction(Function):
    """Answers a question using the message history of a different one of the user's conversations."""

    # @param agent: The owning BaseAgent. Provides message_guid/user_guid (read
    #   lazily at execute() time, since message_guid isn't assigned until run()),
    #   message_service for cross-conversation lookups, and system (the agent's
    #   FunctionCallingSystem) for the one-shot DeepSeek call.
    def __init__(self, agent: "BaseAgent"):
        super().__init__(
            name="askInstance",
            description=(
                "Ask a question answered using the message history of a different one of your "
                "conversations. Provide the target conversation's GUID (instance_id) and your "
                "question; a temporary, tool-less assistant reads that conversation's transcript "
                "and answers based only on it. Nothing from this is saved to the other conversation."
            ),
            parameters={
                "question": {"type": "string", "description": "The question to answer using the other conversation's history"},
                "instance_id": {"type": "string", "description": "GUID of the other conversation to read"}
            }
        )
        self.agent = agent

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        question = args.get("question")
        instance_id = args.get("instance_id")
        if not question or not isinstance(question, str):
            return {"error": "Invalid 'question' parameter"}
        if not instance_id or not isinstance(instance_id, str):
            return {"error": "Invalid 'instance_id' parameter"}

        if instance_id == self.agent.message_guid:
            return {"error": "Cannot ask about the current conversation"}

        conv = self.agent.message_service.get_conversation_for_user(instance_id, self.agent.user_guid)
        if conv is None:
            return {"error": "Conversation not found or not accessible"}

        transcript = _build_transcript(conv["messages"]) or "(empty conversation)"
        system_prompt = ASK_INSTANCE_SYSTEM_PROMPT.format(instance_id=instance_id, transcript=transcript)

        temp_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ]

        try:
            response = self.agent.system._call_deepseek(temp_messages)
            answer = response["choices"][0]["message"]["content"]
        except Exception as e:
            return {"error": f"askInstance failed: {str(e)}"}

        return {
            "answer": answer,
            "source_guid": instance_id,
            "source_message_count": len(conv["messages"])
        }
