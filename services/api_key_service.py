from typing import Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os
import logging

from utils.crypto import decrypt

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class ApiKeyService:
    """Looks up per-user LLM API keys (encrypted at rest) from MongoDB."""

    def __init__(self):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.collection_name = os.getenv('MONGODB_API_KEYS_COLLECTION', 'apikeys')

        try:
            self.client = MongoClient(self.uri)
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
        except ConnectionFailure as e:
            raise ConnectionError(f"ApiKeyService failed to connect to MongoDB: {e}")

    def get_api_key(self, user_guid: Optional[str], provider: str = 'deepseek') -> Optional[str]:
        """Return the decrypted API key for this user/provider, or None if not set."""
        if not user_guid:
            return None

        doc = self.collection.find_one({'user_guid': user_guid, 'provider': provider})
        if not doc or not doc.get('encrypted_key'):
            return None

        try:
            return decrypt(doc['encrypted_key'])
        except Exception as e:
            logger.warning(f"Failed to decrypt API key for user {user_guid}: {e}")
            return None
