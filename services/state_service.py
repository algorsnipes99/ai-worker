from typing import Dict, Any, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
import os

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

class StateService:
    """Service for managing agent execution states in MongoDB"""

    # Connect to MongoDB using env vars. Raises ConnectionError on failure.
    # @param messages_dir: Unused legacy parameter kept for interface compatibility.
    def __init__(self, messages_dir: str):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.collection_name = os.getenv('MONGODB_STATE_COLLECTION', 'states')

        try:
            self.client = MongoClient(self.uri)
            # Verify connection
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
        except ConnectionFailure as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    # Upsert the execution state snapshot for a given GUID.
    # @param state: State dict (e.g. {status, current_step, pending_tool_calls, ...}).
    # @param guid: Unique execution identifier.
    # @param agent_class_name: Lowercased agent class name stored for reference.
    # @param parent_message_guid: Optional parent agent GUID for child agents.
    def save_execution_state(self, state: Dict[str, Any], guid: str,
                           agent_class_name: str, parent_message_guid: Optional[str] = None) -> None:
        document = {
            'guid': guid,
            'agent_class_name': agent_class_name.lower(),
            'state': state,
            'parent_message_guid': parent_message_guid,
            'last_updated': self.get_timestamp()
        }

        # Upsert to update if exists or insert if new
        self.collection.update_one(
            {'guid': guid},
            {'$set': document},
            upsert=True
        )

    # Load the execution state for a given GUID using a three-tier fallback strategy:
    # 1. Exact GUID match
    # 2. GUID + parent_message_guid match
    # 3. Regex match on the GUID string
    # @param guid: Execution GUID to load.
    # @param agent_class_name: Agent class name (unused in queries, kept for interface parity).
    # @param parent_message_guid: Optional parent GUID for secondary lookup.
    # @returns: State dict, or empty dict if no document found.
    def load_execution_state(self, guid: str, agent_class_name: str,
                           parent_message_guid: Optional[str] = None) -> Dict[str, Any]:
        if not guid:
            return {}

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

        return doc.get('state', {}) if doc else {}

    # Return the current time as an ISO 8601 string.
    # @returns: Timestamp string.
    def get_timestamp(self) -> str:
        return datetime.now().isoformat()
