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

    def save_execution_state(self, state: Dict[str, Any], guid: str, 
                           agent_class_name: str, parent_message_guid: Optional[str] = None) -> None:
        """Save execution state to MongoDB"""
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

    def load_execution_state(self, guid: str, agent_class_name: str,
                           parent_message_guid: Optional[str] = None) -> Dict[str, Any]:
        """Load execution state from MongoDB"""
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

    def get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        return datetime.now().isoformat()
