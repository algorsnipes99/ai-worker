from abc import ABC, abstractmethod
from pymongo import MongoClient
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()


class BaseCompressor(ABC):
    """Base class for all conversation compression strategies"""

    # Connect to MongoDB using env vars so subclasses can load and save conversations.
    def __init__(self):
        uri = os.getenv('MONGODB_URI')
        db_name = os.getenv('MONGODB_DB_NAME', 'test')
        collection_name = os.getenv('MONGODB_COLLECTION_NAME', 'messages')
        self.client = MongoClient(uri)
        self.collection = self.client[db_name][collection_name]

    # Load the conversation for the given GUID, compress it, save it back, and clear flags.
    # @param guid: The conversation GUID to compress.
    # @raises ValueError: If no document with the given GUID exists.
    def run(self, guid: str):
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

    # Apply the compression strategy to a message list and return the result.
    # Must be implemented by each concrete compressor subclass.
    # @param messages: Full list of conversation message dicts.
    # @returns: Compressed list of message dicts.
    @abstractmethod
    def compress(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass
