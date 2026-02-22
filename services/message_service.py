from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os
import json

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

class MessageService:
    """Service for saving and loading agent messages to MongoDB"""
    
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

    def save_messages(self, messages: List[Dict[str, Any]], guid: str, 
                     agent_class_name: str, parent_message_guid: Optional[str] = None):
        """Save messages to MongoDB"""
        document = {
            'guid': guid,
            'agent_class_name': agent_class_name.lower(),
            'messages': messages,
            'parent_message_guid': parent_message_guid,
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

    def load_messages(self, guid: str, agent_class_name: str,
                     parent_message_guid: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Load messages from MongoDB"""
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

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()
