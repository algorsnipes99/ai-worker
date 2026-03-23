from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os
import json
from utils.machine_info import get_machine_id, get_machine_name

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

class MessageService:
    """Service for saving and loading agent messages to MongoDB"""

    # Connect to MongoDB using env vars. Raises ConnectionError on failure.
    # @param messages_dir: Unused legacy parameter kept for interface compatibility.
    def __init__(self, messages_dir: str):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.collection_name = os.getenv('MONGODB_COLLECTION_NAME', 'messages')

        try:
            self.client = MongoClient(self.uri)
            # Verify connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
        except ConnectionFailure as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    # Upsert the message array for a given GUID. Creates the document if it doesn't exist.
    # @param messages: List of message dicts to persist.
    # @param guid: Unique execution identifier.
    # @param agent_class_name: Lowercased agent class name stored for filtering.
    # @param parent_message_guid: Optional parent agent GUID for child agents.
    # @returns: pymongo UpdateResult.
    def save_messages(self, messages: List[Dict[str, Any]], guid: str,
                     agent_class_name: str, parent_message_guid: Optional[str] = None):
        document = {
            'guid': guid,
            'agent_class_name': agent_class_name.lower(),
            'messages': messages,
            'parent_message_guid': parent_message_guid,
            'machine_id': get_machine_id(),
            'machine_name': get_machine_name(),
            'created_at': self._get_timestamp()
        }
        print("befoire save")
        # Upsert to update if exists or insert if new
        result = self.collection.update_one(
            {'guid': guid},
            {'$set': document},
            upsert=True
        )
        print(result)
        return result

    # Load messages for the given GUID using a three-tier fallback strategy:
    # 1. Exact GUID match
    # 2. GUID + parent_message_guid match
    # 3. Regex match on the GUID string
    # @param guid: Execution GUID to load.
    # @param agent_class_name: Agent class name (unused in queries, kept for interface parity).
    # @param parent_message_guid: Optional parent GUID for secondary lookup.
    # @returns: List of message dicts, or None if no document found.
    def load_messages(self, guid: str, agent_class_name: str,
                     parent_message_guid: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        if not guid:
            return None

        # First try exact match
        query = {'guid': guid}
        doc = self.collection.find_one(query)

        if not doc and parent_message_guid:
            # Try with parent guid
            query = {
                'guid': guid,
                'parent_message_guid': parent_message_guid
            }
            doc = self.collection.find_one(query)

        if not doc:
            # Try any document containing this guid
            query = {'guid': {'$regex': guid}}
            doc = self.collection.find_one(query)

        return doc.get('messages', []) if doc else None

    # Set the 'status' field on the agent's document (e.g. 'active', 'complete', 'paused').
    # Creates the document if it does not exist.
    # @param guid: Execution GUID to update.
    # @param status: Status string to set.
    def update_status(self, guid: str, status: str) -> None:
        self.collection.update_one(
            {'guid': guid},
            {'$set': {'status': status}},
            upsert=True
        )

    # Atomically check for a pause_signal on the document and clear it in one operation.
    # @param guid: Execution GUID to check.
    # @returns: True if a pause_signal was present (and has now been cleared), False otherwise.
    def check_and_clear_pause_signal(self, guid: str) -> bool:
        result = self.collection.find_one_and_update(
            {'guid': guid, 'pause_signal': True},
            {'$unset': {'pause_signal': ""}},
        )
        return result is not None

    # Return the current time as an ISO 8601 string.
    # @returns: Timestamp string.
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
