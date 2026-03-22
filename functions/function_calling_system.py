import json
import requests
from typing import Dict, Any, List
from functions.function_registry import FunctionRegistry
from utils.permission_manager import PermissionManager
from exceptions.tool_permission_exception import ToolPermissionRequiredException

class FunctionCallingSystem:
    """Handles LLM function calling workflow"""

    # Initialize with a tool registry and DeepSeek API key.
    # @param registry: FunctionRegistry containing all available tools for this agent.
    # @param api_key: DeepSeek API key used for LLM calls.
    def __init__(self, registry: FunctionRegistry, api_key: str):
        self.registry = registry
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.permission_manager = PermissionManager()

    # Make an authenticated POST to the DeepSeek chat completions endpoint.
    # If tools are provided they are passed with tool_choice='auto'.
    # @param messages: Message list to send.
    # @param tools: Optional list of tool schema dicts.
    # @returns: Parsed JSON response dict.
    # @raises HTTPError: If the API returns a non-200 status.
    def _call_deepseek(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": messages
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        response = requests.post(self.api_url, json=data, headers=headers)

        if response.status_code != 200:
            print(f"\nAPI Error {response.status_code}:")
            print(response.text)
            response.raise_for_status()

        return response.json()

    # Route an LLM request: if the last message contains tool_calls, dispatch to
    # _handle_tool_calls; otherwise return the tool schemas for the next API call.
    # @param request: Dict with at minimum a 'messages' key.
    # @returns: Either a tool execution result dict or a schema/tool_choice dict.
    # @raises ValueError: If 'messages' is missing from the request.
    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if "messages" not in request:
            raise ValueError("Invalid request: missing messages")

        last_message = request["messages"][-1]

        if last_message.get("role") == "assistant" and "tool_calls" in last_message:
            return self._handle_tool_calls(request)

        return {
            "tools": self.registry.get_schemas(),
            "tool_choice": "auto"
        }

    # Find the most recent assistant message with tool_calls and execute each tool.
    # Permission checks are applied per tool. ToolPermissionRequiredException is re-raised.
    # Other tool errors are caught and returned as error strings to the LLM.
    # @param request: Full request dict containing the message history.
    # @returns: Dict with 'messages' (history + tool responses) and 'function_results'.
    # @raises ValueError: If no assistant tool_calls message is found, or response count mismatches.
    # @raises ToolPermissionRequiredException: Propagated from _execute_with_permission_check.
    def _handle_tool_calls(self, request: Dict[str, Any]) -> Dict[str, Any]:
        # Find the most recent assistant message with tool_calls
        tool_call_msg = None
        for msg in reversed(request["messages"]):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                tool_call_msg = msg
                break

        if not tool_call_msg:
            raise ValueError("No assistant message with tool_calls found in history")

        tool_messages = []
        function_results = []

        # Process all tool calls in parallel
        for tool_call in tool_call_msg["tool_calls"]:
            try:
                # Validate tool call structure
                if not all(k in tool_call for k in ["id", "function"]):
                    raise ValueError("Invalid tool call structure")
                if not all(k in tool_call["function"] for k in ["name", "arguments"]):
                    raise ValueError("Invalid function call structure")

                args = json.loads(tool_call["function"]["arguments"])

                # Check for permission verification before execution
                result = self._execute_with_permission_check(
                    tool_call["function"]["name"],
                    args
                )

                # Validate and format response
                if not isinstance(result, dict):
                    result = {"result": result}

                tool_response = {
                    "role": "tool",
                    "content": json.dumps(result),
                    "tool_call_id": tool_call["id"],
                    "name": tool_call["function"]["name"]
                }
                tool_messages.append(tool_response)
                function_results.append({
                    "name": tool_call["function"]["name"],
                    "result": result,
                    "tool_call_id": tool_call["id"]
                })

            except Exception as e:
                # Re-raise permission exceptions to allow user prompting
                if isinstance(e, ToolPermissionRequiredException):
                    print(f"🔐 Permission required for {e.tool_name}, re-raising from function calling system...")
                    raise e

                error_msg = f"ERROR: {str(e)}"
                tool_messages.append({
                    "role": "tool",
                    "content": error_msg,
                    "tool_call_id": tool_call.get("id", "unknown"),
                    "name": tool_call.get("function", {}).get("name", "unknown")
                })
                function_results.append({
                    "name": tool_call.get("function", {}).get("name", "unknown"),
                    "result": {"error": error_msg},
                    "tool_call_id": tool_call.get("id", "unknown")
                })

        # Verify we have matching tool responses
        if len(tool_messages) != len(tool_call_msg["tool_calls"]):
            raise ValueError("Tool response count mismatch")

        return {
            "messages": request["messages"] + tool_messages,
            "function_results": function_results
        }

    # Execute a tool after checking its permission state via PermissionManager.
    # - None  → raise ToolPermissionRequiredException (halts execution for human approval)
    # - False → return a structured denial dict (LLM sees the denial and can adapt)
    # - True  → consume the one-shot permission and execute the tool
    # Tools with needs_verification=False bypass the permission check entirely.
    # @param tool_name: Name of the tool to execute.
    # @param args: Arguments dict for the tool.
    # @returns: Tool execution result dict.
    # @raises ValueError: If the tool is not registered.
    # @raises ToolPermissionRequiredException: If permission is unknown (None).
    def _execute_with_permission_check(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        # Get the function object to check if it needs verification
        if tool_name not in self.registry.functions:
            raise ValueError(f"Function {tool_name} not found")

        function = self.registry.functions[tool_name]

        # Check if this function requires user verification
        if function.needs_verification:
            permission_status = self.permission_manager.check_permission(tool_name)
            print("-"*50)
            print("permission_status")
            print(permission_status)
            print("-"*50)

            if permission_status is None:
                # First time - no permission set, throw exception to bubble up
                raise ToolPermissionRequiredException(
                    tool_name=tool_name,
                    tool_description=function.description,
                    verification_description=function.verification_description,
                    tool_args=args,
                    execution_context={"timestamp": "2025-01-29T12:10:54Z"}
                )

            elif permission_status is False:
                # Permission denied - return structured denial response
                return {
                    "status": "permission_denied",
                    "message": f"User permission required but not granted for tool: {tool_name}",
                    "tool_name": tool_name,
                    "verification_description": function.verification_description,
                    "requested_action": f"Execute {tool_name} with arguments: {args}",
                    "suggestion": "User can grant permission when prompted on next execution"
                }

            elif permission_status is True:
                # Permission granted - consume it and execute
                if self.permission_manager.consume_permission(tool_name):
                    print(f"🔐 Permission consumed for {tool_name}, executing tool...")
                    return self.registry.execute(tool_name, args)
                else:
                    # This shouldn't happen, but handle gracefully
                    return {
                        "status": "permission_error",
                        "message": f"Permission consumption failed for tool: {tool_name}",
                        "tool_name": tool_name
                    }

        # No verification needed - execute normally
        print("Executing " + tool_name + " #### args:")
        return self.registry.execute(tool_name, args)
