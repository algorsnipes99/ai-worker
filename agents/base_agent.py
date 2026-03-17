from abc import ABC, abstractmethod
import json
import uuid
import os
from typing import Dict, Any, List, Optional
from functions.function_registry import FunctionRegistry
from functions.function_calling_system import FunctionCallingSystem
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
    
    def __init__(self, user_request: str, plan_text: str, api_key: str, 
                 parent_message_guid: Optional[str] = None,
                 parent_resume_guid: Optional[str] = None,
                 child_resume_guid: Optional[str] = None):
        self.user_request = user_request
        self.plan_text = plan_text
        self.api_key = api_key
        self.message_guid: Optional[str] = None
        self.parent_message_guid = parent_message_guid
        self.parent_resume_guid = parent_resume_guid
        self.child_resume_guid = child_resume_guid
        self.execution_state = {}
        self.message_service = MessageService(self.messages_dir)
        self.state_service = StateService(self.messages_dir)
        self.registry = self._initialize_tools()
        self.system = FunctionCallingSystem(self.registry, api_key=self.api_key)

    @property
    @abstractmethod
    def messages_dir(self) -> str:
        """Directory to store agent messages (must be implemented by subclasses)"""
        pass

    @property
    @abstractmethod 
    def system_prompt_path(self) -> str:
        """Path to agent's system prompt (must be implemented by subclasses)"""
        pass

    @abstractmethod
    def _initialize_tools(self) -> FunctionRegistry:
        """Initialize agent-specific tools (must be implemented by subclasses)"""
        pass

    def _get_system_prompt_from_file(self) -> str:
        """Read system prompt from file with fallback default"""
        try:
            with open(self.system_prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            return "You are an AI assistant that follows plans."

    def _enhance_system_prompt(self, system_prompt: str) -> str:
        """Add plan context to system prompt (can be overridden by subclasses)"""
        return f"{system_prompt}\n\nPLAN TO FOLLOW:\n{self.plan_text}"

    def _create_initial_messages(self) -> List[Dict[str, Any]]:
        """Create initial message array with enhanced system prompt"""
        system_prompt = self._get_system_prompt_from_file()
        enhanced_prompt = self._enhance_system_prompt(system_prompt)
        return [
            {"role": "system", "content": enhanced_prompt},
            {"role": "user", "content": self.user_request}
        ]

    def _save_messages(self, messages: List[Dict[str, Any]], guid: str):
        """Save messages using MessageService"""
        result = self.message_service.save_messages(
            messages=messages,
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )
        
        # Also save execution state
        return self._save_execution_state(guid)

    def _load_messages(self, guid: str) -> Optional[List[Dict[str, Any]]]:
        """Load messages using MessageService"""
        return self.message_service.load_messages(
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )
    
    def _save_execution_state(self, guid: str) -> None:
        """Save execution state using StateService"""
        # Add current timestamp to track last save
        self.execution_state["last_saved"] = self.state_service.get_timestamp()
        self.execution_state["message_count"] = len(self._load_messages(guid) or [])
        
        self.state_service.save_execution_state(
            state=self.execution_state,
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )
    
    def _load_execution_state(self, guid: str) -> None:
        """Load execution state using StateService"""
        self.execution_state = self.state_service.load_execution_state(
            guid=guid,
            agent_class_name=self.__class__.__name__,
            parent_message_guid=self.parent_message_guid
        )

    def _get_timestamp(self) -> str:
        """Get current timestamp from StateService"""
        return self.state_service.get_timestamp()
    
    def setAgentStatesInPermissions(self) -> None:
        """Track agent GUID in PermissionManager for parent-child relationship tracking"""
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
    
    def _check_pause_signal(self) -> bool:
        """Check MongoDB for a pause_signal on this agent's document"""
        if not self.message_guid:
            return False
        return self.message_service.check_and_clear_pause_signal(self.message_guid)

    def removeChildAgentState(self) -> None:
        """Remove child agent GUID from PermissionManager when child agent completes"""
        try:
            if self.parent_message_guid:
                permission_manager = PermissionManager()
                permission_manager.set_child_message_guid("")  # Clear child GUID
        except Exception as e:
            print(f"Warning: Could not clear child GUID in PermissionManager: {e}")

    def update_plan(self, new_user_request: str, new_plan_text: str) -> None:
        """Update the current plan while maintaining conversation history"""
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

    def _start_new_execution(self, user_request_override: Optional[str] = None) -> Dict[str, Any]:
        """Start a new execution (not resuming)"""
        if self.message_guid is None:
            self.message_guid = str(uuid.uuid4())
            messages = self._create_initial_messages()
            self.execution_state = {"status": self.STATE_INIT, "current_step": 0}
        else:
            messages = self._load_messages(self.message_guid) or []
            if user_request_override:
                messages.append({"role": "user", "content": user_request_override})
                
        return self._process_with_tools(messages)

    def _resume_before_tool_call(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resume execution when tool calls were pending but not executed"""
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

    def _resume_after_tool_call(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resume execution when tool results need to be processed by the assistant"""
        # Add system message indicating resumption
        messages.append({
            "role": "system",
            "content": "Resuming after tool call completion. Continue processing the tool results."
        })
        
        return self._process_with_tools(messages, resuming=True)

    def _resume_completed(self, messages: List[Dict[str, Any]], user_request_override: Optional[str] = None) -> Dict[str, Any]:
        """Resume execution when previous run was already completed"""
        print('####'*30)
        print('_resume_completed')
        print(user_request_override)

        print('####'*30)

        # Reset state for new interaction
        self.execution_state["status"] = self.STATE_INIT
        # if user_request_override:
        #         messages.append({"role": "user", "content": user_request_override})
        # else:        
        #     messages.append({
        #         "role": "system",
        #         "content": "Previous task was completed. Starting new interaction."
        #     })
        
        return self._process_with_tools(messages, resuming=True)

    def _resume_error(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resume execution when previous run encountered an error"""
        # Reset state
        self.execution_state["status"] = self.STATE_INIT
        messages.append({
            "role": "system",
            "content": "Previous execution encountered an error. Resuming from last valid state."
        })
        
        return self._process_with_tools(messages, resuming=True)

    def _resume_init(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Resume execution from initial state"""
        messages.append({
            "role": "system",
            "content": "Resuming execution from initial state."
        })
        
        return self._process_with_tools(messages, resuming=True)

    def run(self, user_request_override: Optional[str] = None) -> Dict[str, Any]:
        """Main execution entry point with enhanced resumption support"""
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

    def _process_with_tools(self, messages: List[Dict[str, Any]], resuming: bool = False) -> Dict[str, Any]:
        """Process messages with enhanced state tracking"""
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
                messages.append(choice["message"])
                
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
