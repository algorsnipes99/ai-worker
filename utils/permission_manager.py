"""Permission manager for handling tool permissions"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

class PermissionManager:
    """Manages tool permissions in active_permissions.json file"""

    # Initialize the PermissionManager.
    # @param permissions_file: Path to the JSON file used to persist permissions.
    #                          Defaults to 'active_permissions.json' in the working directory.
    def __init__(self, permissions_file: str = "active_permissions.json"):
        self.permissions_file = permissions_file
        self._ensure_permissions_file_exists()

    # Create the permissions file with a default empty structure if it does not exist.
    # Writes initial JSON with empty 'tool_permissions' and 'message_guids' dicts
    # plus creation/update timestamps.
    def _ensure_permissions_file_exists(self) -> None:
        if not os.path.exists(self.permissions_file):
            initial_data = {
                "tool_permissions": {},
                "message_guids": {},
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            self._save_permissions(initial_data)

    # Load the full permissions document from disk.
    # @returns: The parsed JSON dict. If the file cannot be read or parsed, returns
    #           a default empty-structure dict and logs a warning.
    def _load_permissions(self) -> Dict[str, Any]:
        try:
            with open(self.permissions_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load permissions file: {e}")
            # Return default structure
            return {
                "tool_permissions": {},
                "message_guids": {},
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }

    # Persist the permissions document to disk, updating 'last_updated' first.
    # @param data: The full permissions dict to serialize as JSON.
    # @raises Exception: Re-raises any I/O error after logging it.
    def _save_permissions(self, data: Dict[str, Any]) -> None:
        try:
            data["last_updated"] = datetime.now().isoformat()
            with open(self.permissions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: Could not save permissions file: {e}")
            raise

    # Check the current permission state for a tool.
    # @param tool_name: The name of the tool to check.
    # @returns: None  — No entry exists; permission has never been set. Caller should
    #                   raise ToolPermissionRequiredException to prompt the user.
    #           True  — Permission has been explicitly granted.
    #           False — Permission has been explicitly denied.
    def check_permission(self, tool_name: str) -> Optional[bool]:
        data = self._load_permissions()
        return data.get("tool_permissions", {}).get(tool_name)

    # Explicitly grant permission for a tool.
    # Sets the tool's entry to True. The permission is one-shot: it will be
    # removed by consume_permission() after first use.
    # @param tool_name: The name of the tool to grant permission for.
    def grant_permission(self, tool_name: str) -> None:
        data = self._load_permissions()
        data["tool_permissions"][tool_name] = True
        self._save_permissions(data)
        print(f"Permission granted for tool: {tool_name}")

    # Explicitly deny permission for a tool.
    # Sets the tool's entry to False. Subsequent check_permission() calls will
    # return False and the tool will not be executed.
    # @param tool_name: The name of the tool to deny permission for.
    def deny_permission(self, tool_name: str) -> None:
        data = self._load_permissions()
        data["tool_permissions"][tool_name] = False
        self._save_permissions(data)
        print(f"Permission denied for tool: {tool_name}")

    # Consume (remove) a granted permission after the tool has been executed.
    # Permissions are one-shot: once a tool runs, its entry is deleted so the
    # user must re-approve on the next invocation.
    # @param tool_name: The name of the tool whose permission should be consumed.
    # @returns: True if the permission was granted and has now been removed,
    #           False if no granted permission existed.
    def consume_permission(self, tool_name: str) -> bool:
        data = self._load_permissions()
        current_permission = data.get("tool_permissions", {}).get(tool_name)

        if current_permission is True:
            # Consume the permission
            del data["tool_permissions"][tool_name]  # Removes the key entirely
            self._save_permissions(data)
            print(f"Permission consumed for tool: {tool_name}")
            return True

        return False

    # Remove a tool's permission entry entirely, regardless of its current state.
    # After revocation, check_permission() returns None (unknown), which will
    # trigger a new permission request on next tool invocation.
    # @param tool_name: The name of the tool whose permission entry should be removed.
    def revoke_permission(self, tool_name: str) -> None:
        data = self._load_permissions()
        if tool_name in data.get("tool_permissions", {}):
            del data["tool_permissions"][tool_name]
            self._save_permissions(data)
            print(f"Permission revoked for tool: {tool_name}")

    # Return all current tool permission entries.
    # @returns: Dict mapping tool name to its permission value (True or False).
    #           Returns an empty dict if no permissions have been set.
    def list_permissions(self) -> Dict[str, bool]:
        data = self._load_permissions()
        return data.get("tool_permissions", {})

    # Clear all tool permission entries from the permissions file.
    # After reset, every tool will appear as unknown (None) on the next
    # check_permission() call, requiring fresh user approval.
    def reset_permissions(self) -> None:
        data = self._load_permissions()
        data["tool_permissions"] = {}
        self._save_permissions(data)
        print("All permissions reset")

    # Store the parent agent's message GUID in the permissions file.
    # Used to track agent lineage when a child agent is spawned via delegation.
    # @param guid: The message GUID of the parent agent execution.
    def set_parent_message_guid(self, guid: str) -> None:
        data = self._load_permissions()
        if "message_guids" not in data:
            data["message_guids"] = {}
        data["message_guids"]["parent_message_guid"] = guid
        self._save_permissions(data)
        print(f"Parent message GUID set: {guid[:8]}...")

    # Store the child agent's message GUID in the permissions file.
    # Used when a parent delegates to a child agent. The stored GUID allows the
    # external interface to resume the child after a permission exception is resolved.
    # @param guid: The message GUID of the child agent execution.
    def set_child_message_guid(self, guid: str) -> None:
        data = self._load_permissions()
        if "message_guids" not in data:
            data["message_guids"] = {}
        data["message_guids"]["child_message_guid"] = guid
        self._save_permissions(data)
        print(f"Child message GUID set: {guid[:8]}...")

    # Retrieve the stored parent agent message GUID.
    # @returns: The parent agent's message GUID string, or None if not set.
    def get_parent_message_guid(self) -> Optional[str]:
        data = self._load_permissions()
        return data.get("message_guids", {}).get("parent_message_guid")

    # Retrieve the stored child agent message GUID.
    # @returns: The child agent's message GUID string, or None if not set.
    def get_child_message_guid(self) -> Optional[str]:
        data = self._load_permissions()
        return data.get("message_guids", {}).get("child_message_guid")

    # Remove all stored parent and child message GUIDs from the permissions file.
    # Call this after an agent session completes to avoid stale GUIDs
    # interfering with a subsequent unrelated session.
    def clear_message_guids(self) -> None:
        data = self._load_permissions()
        if "message_guids" in data:
            data["message_guids"] = {}
            self._save_permissions(data)
            print("All message GUIDs cleared")

    # Return all currently stored message GUIDs.
    # @returns: Dict with keys 'parent_message_guid' and/or 'child_message_guid',
    #           depending on what has been set. Returns an empty dict if none are stored.
    def list_message_guids(self) -> Dict[str, str]:
        data = self._load_permissions()
        return data.get("message_guids", {})
