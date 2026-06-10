from abc import ABC, abstractmethod
import json
import uuid
import os
from typing import Dict, Any, List, Optional
from functions.function_registry import FunctionRegistry
from functions.function_calling_system import FunctionCallingSystem, DEFAULT_MODEL
from utils.permission_manager import PermissionManager
from services.message_service import MessageService
from services.state_service import StateService
from agents.summarization_agent import SummarizationAgent

class BaseAgent(ABC):
    """Abstract base class for all agents providing common functionality"""

    # Define execution states as constants
    STATE_INIT = "INIT"
    STATE_BEFORE_TOOL_CALL = "BEFORE_TOOL_CALL"
    STATE_AFTER_TOOL_CALL = "AFTER_TOOL_CALL"
    STATE_COMPLETED = "COMPLETED"
    STATE_ERROR = "ERROR"

    # Initialize the agent with request context and resume GUIDs.
    # Sets up MessageService, StateService, tool registry, and FunctionCallingSystem.
    # @param user_request: The user's task description.
    # @param plan_text: Optional plan to append to the system prompt.
    # @param api_key: DeepSeek API key.
    # @param parent_message_guid: GUID of the parent agent (if this is a child agent).
    # @param parent_resume_guid: GUID to resume for the top-level (parent) agent.
    # @param child_resume_guid: GUID to resume for a child agent spawned via delegation.
    def __init__(self, user_request: str, plan_text: str, api_key: str,
                 parent_message_guid: Optional[str] = None,
                 parent_resume_guid: Optional[str] = None,
                 child_resume_guid: Optional[str] = None,
                 model_name: str = DEFAULT_MODEL):
        self.user_request = user_request
        self.plan_text = plan_text
        self.api_key = api_key
        self.model_name = model_name
        self.message_guid: Optional[str] = None
        self.parent_message_guid = parent_message_guid
        self.parent_resume_guid = parent_resume_guid
        self.child_resume_guid = child_resume_guid
        self.execution_state = {}
        self.message_service = MessageService(self.messages_dir)
        self.state_service = StateService(self.messages_dir)
        self.registry = self._initialize_tools()
        self.system = FunctionCallingSystem(self.registry, api_key=self.api_key, model_name=self.model_name)

    # Directory path where agent messages are stored (subclass must implement).
    @property
    @abstractmethod
    def messages_dir(self) -> str:
        pass

    # Path to the agent's system prompt text file (subclass must implement).
    @property
    @abstractmethod
    def system_prompt_path(self) -> str:
        pass

    # Build and return the FunctionRegistry for this agent's tool set (subclass must implement).
    @abstractmethod
    def _initialize_tools(self) -> FunctionRegistry:
        pass

    # Read the system prompt from disk; return a default string if the file is missing or unreadable.
    # @returns: The raw system prompt text.
    def _get_system_prompt_from_file(self) -> str:
        try:
            with open(self.system_prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            return "You are an AI assistant that follows plans."

    # Append plan_text to the system prompt. Subclasses may override to customize injection.
    # @param system_prompt: The base system prompt string.
    # @returns: Enhanced prompt with plan context appended.
    def _enhance_system_prompt(self, system_prompt: str) -> str:
        return f"{system_prompt}\n\nPLAN TO FOLLOW:\n{self.plan_text}"

    # Build the initial message array: [system (enhanced), user (request)].
    # @returns: List of message dicts ready for the LLM.
    def _create_initial_messages(self) -> List[Dict[str, Any]]:
        system_prompt = self._get_system_prompt_from_file()
        enhanced_prompt = self._enhance_system_prompt(system_prompt)
        return [
            {"role": "system", "content": enhanced_prompt},
            {"role": "user", "content": self.user_request}
        ]

    # Persist messages to MongoDB via MessageService, then also save execution state.
    # @param messages: The current message list.
    # @param guid: The execution GUID to save under.
    def _save_messages(self, messages: List[Dict[str, Any]], guid: str):
        result = self.message_service.save_messages(
            messages=messages,
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )

        # Also save execution state
        return self._save_execution_state(guid)

    # Load messages from MongoDB for the given GUID.
    # @param guid: The execution GUID to load.
    # @returns: List of message dicts, or None if not found.
    def _load_messages(self, guid: str) -> Optional[List[Dict[str, Any]]]:
        return self.message_service.load_messages(
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )

    # Snapshot current execution_state to MongoDB via StateService.
    # Adds a timestamp and message count before saving.
    # @param guid: The execution GUID to save state under.
    def _save_execution_state(self, guid: str) -> None:
        # Add current timestamp to track last save
        self.execution_state["last_saved"] = self.state_service.get_timestamp()
        self.execution_state["message_count"] = len(self._load_messages(guid) or [])

        self.state_service.save_execution_state(
            state=self.execution_state,
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )

    # Load a previously saved execution state from MongoDB into self.execution_state.
    # @param guid: The execution GUID to load state for.
    def _load_execution_state(self, guid: str) -> None:
        self.execution_state = self.state_service.load_execution_state(
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )

    # Return the current ISO timestamp from StateService.
    # @returns: Timestamp string.
    def _get_timestamp(self) -> str:
        return self.state_service.get_timestamp()

    # Register this agent's GUID in PermissionManager for parent-child lineage tracking.
    # Sets parent_message_guid if this is a top-level agent, child_message_guid if a child.
    def setAgentStatesInPermissions(self) -> None:
        try:
            permission_manager = PermissionManager()
            if self.parent_message_guid:
                # This is a child agent - set child GUID
                permission_manager.set_child_message_guid(self.message_guid)
            else:
                # This is a parent/main agent - set parent GUID
                permission_manager.set_parent_message_guid(self.message_guid)
        except Exception as e:
            print(f"Warning: Could not update GUID tracking in PermissionManager: {e}")

    # Poll MongoDB for a pause_signal on this agent's document and clear it atomically.
    # @returns: True if a pause was signalled (and cleared), False otherwise.
    def _check_pause_signal(self) -> bool:
        if not self.message_guid:
            return False
        return self.message_service.check_and_clear_pause_signal(self.message_guid)

    # Clear the child agent's GUID in PermissionManager once the child agent completes.
    def removeChildAgentState(self) -> None:
        try:
            if self.parent_message_guid:
                permission_manager = PermissionManager()
                permission_manager.set_child_message_guid("")  # Clear child GUID
        except Exception as e:
            print(f"Warning: Could not clear child GUID in PermissionManager: {e}")

    # Replace the current plan mid-execution and append a system message to the conversation.
    # @param new_user_request: Updated task description.
    # @param new_plan_text: Updated plan text.
    def update_plan(self, new_user_request: str, new_plan_text: str) -> None:
        self.user_request = new_user_request
        self.plan_text = new_plan_text

        if self.message_guid is not None:
            messages = self._load_messages(self.message_guid)
            if messages:
                plan_update = {
                    "role": "system",
                    "content": f"PLAN UPDATE: New request: {new_user_request}\n\nNEW PLAN:\n{new_plan_text}"
                }
                messages.append(plan_update)
                self._save_messages(messages, self.message_guid)

    # Begin a fresh execution (no resume GUID). Generates a new message_guid and
    # builds initial messages, then enters the tool-calling loop.
    # @param user_request_override: Optional message to append as a follow-up user turn.
    # @returns: Final LLM response dict.
    def _start_new_execution(self, user_request_override: Optional[str] = None) -> Dict[str, Any]:
        if self.message_guid is None:
            self.message_guid = str(uuid.uuid4())
            messages = self._create_initial_messages()
            self.execution_state = {"status": self.STATE_INIT, "current_step": 0}
        else:
            messages = self._load_messages(self.message_guid) or []
            if user_request_override:
                messages.append({"role": "user", "content": user_request_override})

        return self._process_with_tools(messages)

    # Resume from STATE_BEFORE_TOOL_CALL: re-execute any tool calls that had not yet
    # received responses, then continue the tool-calling loop.
    # @param messages: Full message history loaded from MongoDB.
    # @returns: Final LLM response dict, or an error dict on failure.
    def _resume_before_tool_call(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            print("in _resume_before_tool_call")
            # Find the assistant message with tool_calls and identify which ones need responses
            assistant_tool_calls = []
            existing_tool_responses = set()

            # Scan messages to find tool calls and existing responses
            for msg in messages:
                if msg["role"] == "assistant" and "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        assistant_tool_calls.append(tc)
                elif msg["role"] == "tool" and "tool_call_id" in msg:
                    existing_tool_responses.add(msg["tool_call_id"])
            print('assistant_tool_calls'+ ('-'*10))
            print(assistant_tool_calls)
            print('assistant_tool_calls'+ ('-'*10))

            # Find tool calls that don't have responses yet
            pending_tool_calls = [
                tc for tc in assistant_tool_calls
                if tc["id"] not in existing_tool_responses
            ]
            print('pending_tool_calls'+ ('-'*10))
            print(pending_tool_calls)
            print('pending_tool_calls'+ ('-'*10))

            print(f"🔄 Resuming with {len(pending_tool_calls)} pending tool calls out of {len(assistant_tool_calls)} total")

            if not pending_tool_calls:
                # All tool calls already have responses, just continue processing
                self.execution_state["status"] = self.STATE_AFTER_TOOL_CALL
                self._save_messages(messages, self.message_guid)
                return self._process_with_tools(messages, resuming=True)

            # Create a temporary message structure with only pending tool calls
            temp_assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": pending_tool_calls
            }
            temp_messages = messages[:-1] + [temp_assistant_msg]  # Replace last assistant message
            print('temp_messages'+ ('-'*10))
            print(temp_messages)
            print('temp_messages'+ ('-'*10))
            # Process only the pending tool calls
            tool_result = self.system.process_request({"messages": temp_messages})

            if tool_result.get("function_results"):
                # Add tool responses to the original messages
                for func_result in tool_result["function_results"]:
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(func_result["result"]),
                        "tool_call_id": func_result["tool_call_id"]
                    })

                # Update state to after tool call
                self.execution_state["status"] = self.STATE_AFTER_TOOL_CALL
                self._save_messages(messages, self.message_guid)

                # Continue with normal processing
                return self._process_with_tools(messages, resuming=True)
            else:
                self.execution_state["status"] = self.STATE_ERROR
                self._save_messages(messages, self.message_guid)
                return {"error": "No tool results returned during resumption"}
        except Exception as e:
            self.execution_state["status"] = self.STATE_ERROR
            self._save_messages(messages, self.message_guid)
            return {"error": f"Tool execution error during resumption: {str(e)}"}

    # Resume from STATE_AFTER_TOOL_CALL: tool results are already appended; inject a
    # continuation system message and re-enter the tool-calling loop.
    # @param messages: Full message history loaded from MongoDB.
    # @returns: Final LLM response dict.
    def _resume_after_tool_call(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Add system message indicating resumption
        messages.append({
            "role": "system",
            "content": "Resuming after tool call completion. Continue processing the tool results."
        })

        return self._process_with_tools(messages, resuming=True)

    # Resume from STATE_COMPLETED: reset state to INIT and continue the loop,
    # treating any new user_request_override as a follow-up turn.
    # @param messages: Full message history loaded from MongoDB.
    # @param user_request_override: Optional follow-up message.
    # @returns: Final LLM response dict.
    def _resume_completed(self, messages: List[Dict[str, Any]], user_request_override: Optional[str] = None) -> Dict[str, Any]:
        print('####'*30)
        print('_resume_completed')
        print(user_request_override)

        print('####'*30)

        # Reset state for new interaction
        self.execution_state["status"] = self.STATE_INIT

        return self._process_with_tools(messages, resuming=True)

    # Resume from STATE_ERROR: reset state to INIT, append an error-context system message,
    # and re-enter the tool-calling loop.
    # @param messages: Full message history loaded from MongoDB.
    # @returns: Final LLM response dict.
    def _resume_error(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Reset state
        self.execution_state["status"] = self.STATE_INIT
        messages.append({
            "role": "system",
            "content": "Previous execution encountered an error. Resuming from last valid state."
        })

        return self._process_with_tools(messages, resuming=True)

    # Resume from STATE_INIT (previously interrupted before any LLM call).
    # @param messages: Full message history loaded from MongoDB.
    # @returns: Final LLM response dict.
    def _resume_init(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        messages.append({
            "role": "system",
            "content": "Resuming execution from initial state."
        })

        return self._process_with_tools(messages, resuming=True)

    # Main entry point. Determines whether to resume a previous execution or start fresh,
    # then dispatches to the appropriate handler based on saved execution state.
    # @param user_request_override: Optional message to use instead of self.user_request.
    # @returns: Final LLM response dict (may include 'paused', 'error', or 'message_guid').
    def run(self, user_request_override: Optional[str] = None) -> Dict[str, Any]:
        print('in base agnet run-------------------------')
        print(f"🔍 parent_message_guid: {self.parent_message_guid}")
        print(f"🔍 parent_resume_guid: {self.parent_resume_guid}")
        print(f"🔍 child_resume_guid: {self.child_resume_guid}")
        print(f"🔍 Agent type: {type(self).__name__}")
        print(f"🔍 Has parent_message_guid: {bool(self.parent_message_guid)}")

        print('in base agnet run----------------------------')

        # Determine which resume GUID to use based on agent type
        resume_guid = None
        if self.parent_message_guid:
            # We are in a child agent, use child_resume_guid
            resume_guid = self.child_resume_guid
        else:
            # We are in a parent/main agent, use parent_resume_guid
            resume_guid = self.parent_resume_guid

        if resume_guid:
            print(f"Resuming execution from {resume_guid[:8]}...")
            self.message_guid = resume_guid
            messages = self._load_messages(resume_guid) or []
            self._load_execution_state(resume_guid)
            print('after load execution state')
            print('user_request_override' + ('-'*10))
            print(user_request_override)
            print('user_request_override'+ ('-'*10))

            # Determine state and delegate to appropriate handler
            current_state = self.execution_state.get("status", self.STATE_INIT)
            print('current_state' + ('-'*10))
            print(current_state)
            print('current_state'+ ('-'*10))
            if current_state == self.STATE_BEFORE_TOOL_CALL:
                print('_resume_before_tool_call'+ ('-'*10))
                return self._resume_before_tool_call(messages)
            elif current_state == self.STATE_AFTER_TOOL_CALL:
                return self._resume_after_tool_call(messages)
            elif current_state == self.STATE_COMPLETED:
                return self._resume_completed(messages, user_request_override)
            elif current_state == self.STATE_ERROR:
                return self._resume_error(messages)
            else:  # INIT or unknown
                return self._resume_init(messages)
        else:
            # Normal execution path for new runs
            return self._start_new_execution(user_request_override)

    # Core LLM loop: repeatedly call DeepSeek, execute any tool calls, and loop until
    # the model returns a final answer (no tool calls). Saves state at each transition.
    # Triggers auto-summarization if message count hits 100.
    # @param messages: Current message list to send to the LLM.
    # @param resuming: If True, skips step-counter increment and initial state reset.
    # @returns: Final LLM response dict with 'message_guid' injected, or error/paused dict.
    def _process_with_tools(self, messages: List[Dict[str, Any]], resuming: bool = False) -> Dict[str, Any]:
        print("_process_with_tools_"+("_"*30))

        # Summarization check - only for non-resuming executions to avoid breaking state
        if not resuming and len(messages) >= 100:
            print(f"📝 Summarizing conversation at {len(messages)} messages threshold")
            summarizer = SummarizationAgent(self.api_key)
            messages = summarizer.summarize_conversation(messages, summarize_first=50, keep_last=10)
            self._save_messages(messages, self.message_guid)
            print(f"📝 Conversation summarized to {len(messages)} messages")

        # Update step counter
        if not resuming:
            if "current_step" not in self.execution_state:
                self.execution_state["current_step"] = 0
            else:
                self.execution_state["current_step"] += 1

        # Initial state save (unless we're resuming after a tool call)
        if not resuming or self.execution_state.get("status") != self.STATE_AFTER_TOOL_CALL:
            self.execution_state["status"] = self.STATE_INIT
            self.execution_state["total_messages"] = len(messages)
            self._save_messages(messages, self.message_guid)
            self.message_service.update_status(self.message_guid, "active")

            # Track agent GUID in PermissionManager for parent-child relationship tracking
            self.setAgentStatesInPermissions()

        while True:
            # Check for pause signal before each LLM call
            if self._check_pause_signal():
                print(f"⏸️  Pause signal received for agent {self.message_guid}. Halting execution.")
                self.message_service.update_status(self.message_guid, "paused")
                return {"paused": True, "message_guid": self.message_guid}

            # Call LLM API
            response = self.system._call_deepseek(
                messages=messages,
                tools=self.registry.get_schemas()
            )

            if "error" in response:
                self.execution_state["status"] = self.STATE_ERROR
                self._save_messages(messages, self.message_guid)
                return response

            if "choices" in response and response["choices"]:
                choice = response["choices"][0]
                assistant_msg = dict(choice["message"])
                reasoning = assistant_msg.pop("reasoning_content", None)
                if reasoning:
                    assistant_msg["thinking"] = reasoning
                messages.append(assistant_msg)

                if "tool_calls" in choice["message"]:
                    # Update state to before tool call
                    self.execution_state["status"] = self.STATE_BEFORE_TOOL_CALL
                    self.execution_state["pending_tool_calls"] = [
                        {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                        for tc in choice["message"]["tool_calls"]
                    ]
                    self._save_messages(messages, self.message_guid)

                    try:
                        tool_result = self.system.process_request({"messages": messages})
                        if tool_result.get("function_results"):
                            for func_result in tool_result["function_results"]:
                                messages.append({
                                    "role": "tool",
                                    "content": json.dumps(func_result["result"]),
                                    "tool_call_id": func_result["tool_call_id"]
                                })

                            # Update state to after tool call
                            self.execution_state["status"] = self.STATE_AFTER_TOOL_CALL
                            self.execution_state["last_tool_results"] = [
                                {
                                    "tool_call_id": fr["tool_call_id"],
                                    "success": "error" not in fr["result"],
                                    "timestamp": self._get_timestamp()
                                }
                                for fr in tool_result["function_results"]
                            ]
                            self._save_messages(messages, self.message_guid)
                            continue
                    except Exception as e:
                        # Import the exception class for proper handling
                        from exceptions.tool_permission_exception import ToolPermissionRequiredException

                        # Handle permission exceptions specially to maintain message structure integrity
                        if isinstance(e, ToolPermissionRequiredException):
                            raise e

                        self._save_messages(messages, self.message_guid)
                        continue

                # Final response with no tool calls
                self.execution_state["status"] = self.STATE_COMPLETED
                self._save_messages(messages, self.message_guid)
                self.message_service.update_status(self.message_guid, "complete")
                self.removeChildAgentState()
                response["message_guid"] = self.message_guid
                return response

            self.execution_state["status"] = self.STATE_ERROR
            self.execution_state["error"] = "Invalid response format from LLM"
            self._save_messages(messages, self.message_guid)
            return {"error": "Invalid response format from LLM"}
