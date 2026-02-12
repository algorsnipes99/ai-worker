"""Permission manager for handling tool permissions"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

class PermissionManager:
    """Manages tool permissions in active_permissions.json file"""
    
    def __init__(self, permissions_file: str = "active_permissions.json"):
        self.permissions_file = permissions_file
        self._ensure_permissions_file_exists()
    
    def _ensure_permissions_file_exists(self) -> None:
        """Create permissions file if it doesn't exist"""
        if not os.path.exists(self.permissions_file):
            initial_data = {
                "tool_permissions": {},
                "message_guids": {},
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            self._save_permissions(initial_data)
    
    def _load_permissions(self) -> Dict[str, Any]:
        """Load permissions from file"""
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
    
    def _save_permissions(self, data: Dict[str, Any]) -> None:
        """Save permissions to file"""
        try:
            data["last_updated"] = datetime.now().isoformat()
            with open(self.permissions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: Could not save permissions file: {e}")
            raise
    
    def check_permission(self, tool_name: str) -> Optional[bool]:
        """
        Check permission status for a tool.
        
        Returns:
            None: Permission not set (first time)
            True: Permission granted
            False: Permission denied
        """
        data = self._load_permissions()
        return data.get("tool_permissions", {}).get(tool_name)
    
    def grant_permission(self, tool_name: str) -> None:
        """Grant permission for a tool"""
        data = self._load_permissions()
        data["tool_permissions"][tool_name] = True
        self._save_permissions(data)
        print(f"Permission granted for tool: {tool_name}")
    
    def deny_permission(self, tool_name: str) -> None:
        """Deny permission for a tool"""
        data = self._load_permissions()
        data["tool_permissions"][tool_name] = False
        self._save_permissions(data)
        print(f"Permission denied for tool: {tool_name}")
    
    def consume_permission(self, tool_name: str) -> bool:
        """
        Consume permission for a tool (remove it entirely after use).
        
        Returns:
            True: Permission was granted and consumed (removed)
            False: Permission was not granted
        """
        data = self._load_permissions()
        current_permission = data.get("tool_permissions", {}).get(tool_name)
        
        if current_permission is True:
            # Consume the permission
            del data["tool_permissions"][tool_name]  # Removes the key entirely
            self._save_permissions(data)
            print(f"Permission consumed for tool: {tool_name}")
            return True
        
        return False
    
    def revoke_permission(self, tool_name: str) -> None:
        """Remove permission entry for a tool"""
        data = self._load_permissions()
        if tool_name in data.get("tool_permissions", {}):
            del data["tool_permissions"][tool_name]
            self._save_permissions(data)
            print(f"Permission revoked for tool: {tool_name}")
    
    def list_permissions(self) -> Dict[str, bool]:
        """List all current permissions"""
        data = self._load_permissions()
        return data.get("tool_permissions", {})
    
    def reset_permissions(self) -> None:
        """Clear all permissions"""
        data = self._load_permissions()
        data["tool_permissions"] = {}
        self._save_permissions(data)
        print("All permissions reset")
    
    def set_parent_message_guid(self, guid: str) -> None:
        """Store the parent agent's message GUID"""
        data = self._load_permissions()
        if "message_guids" not in data:
            data["message_guids"] = {}
        data["message_guids"]["parent_message_guid"] = guid
        self._save_permissions(data)
        print(f"Parent message GUID set: {guid[:8]}...")
    
    def set_child_message_guid(self, guid: str) -> None:
        """Store the child agent's message GUID"""
        data = self._load_permissions()
        if "message_guids" not in data:
            data["message_guids"] = {}
        data["message_guids"]["child_message_guid"] = guid
        self._save_permissions(data)
        print(f"Child message GUID set: {guid[:8]}...")
    
    def get_parent_message_guid(self) -> Optional[str]:
        """Retrieve the parent agent's message GUID"""
        data = self._load_permissions()
        return data.get("message_guids", {}).get("parent_message_guid")
    
    def get_child_message_guid(self) -> Optional[str]:
        """Retrieve the child agent's message GUID"""
        data = self._load_permissions()
        return data.get("message_guids", {}).get("child_message_guid")
    
    def clear_message_guids(self) -> None:
        """Clear all stored message GUIDs"""
        data = self._load_permissions()
        if "message_guids" in data:
            data["message_guids"] = {}
            self._save_permissions(data)
            print("All message GUIDs cleared")
    
    def list_message_guids(self) -> Dict[str, str]:
        """List all current message GUIDs"""
        data = self._load_permissions()
        return data.get("message_guids", {})
