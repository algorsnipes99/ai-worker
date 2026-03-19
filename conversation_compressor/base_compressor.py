from abc import ABC, abstractmethod
from pymongo import MongoClient
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()


class BaseCompressor(ABC):
    """Base class for all conversation compression strategies"""

    def __init__(self):
        uri = os.getenv('MONGODB_URI')
        db_name = os.getenv('MONGODB_DB_NAME', 'test')
        collection_name = os.getenv('MONGODB_COLLECTION_NAME', 'messages')
        self.client = MongoClient(uri)
        self.collection = self.client[db_name][collection_name]

    def run(self, guid: str):
        """Load, compress, and save the conversation, then clear flags"""
        doc = self.collection.find_one({'guid': guid})
        if not doc:
            raise ValueError(f"Conversation {guid} not found")

        compressed_messages = self.compress(doc['messages'])

        self.collection.update_one(
            {'guid': guid},
            {
                '$set': {'messages': compressed_messages},
                '$unset': {'compress_conversation': '', 'compression_strategy': ''}
            }
        )

    @abstractmethod
    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return a compressed version of the messages list"""
        pass
