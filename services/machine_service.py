from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from utils.machine_info import get_machine_id, get_machine_name
from datetime import datetime, timezone, timedelta
import os
import time
import logging

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

PAIRING_TOKEN_TTL_SECONDS = 600  # 10 minutes


class MachineService:
    """Registers and tracks this machine's online/offline status in MongoDB."""

    def __init__(self):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.machines_collection_name = os.getenv('MONGODB_MACHINES_COLLECTION', 'machines')
        self.pairing_tokens_collection_name = os.getenv('MONGODB_PAIRING_TOKENS_COLLECTION', 'pairingtokens')
        self.machine_id = get_machine_id()
        self.machine_name = get_machine_name()

        try:
            self.client = MongoClient(self.uri)
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.machines_collection_name]
            self.pairing_tokens = self.db[self.pairing_tokens_collection_name]
        except ConnectionFailure as e:
            raise ConnectionError(f"MachineService failed to connect to MongoDB: {e}")

    def is_paired(self) -> bool:
        """Return True if this machine already has a verified user_guid in MongoDB."""
        doc = self.collection.find_one({'machine_id': self.machine_id})
        if not doc:
            return False
        user_guid = doc.get('user_guid')
        return bool(user_guid)

    def create_pairing_token(self, token: str) -> None:
        """Insert a pending pairing token into the pairing_tokens collection."""
        now = datetime.now(timezone.utc)
        self.pairing_tokens.update_one(
            {'machine_id': self.machine_id, 'status': 'pending'},
            {'$set': {
                'token': token,
                'machine_id': self.machine_id,
                'machine_name': self.machine_name,
                'status': 'pending',
                'created_at': now.isoformat(),
                'expires_at': (now + timedelta(seconds=PAIRING_TOKEN_TTL_SECONDS)).isoformat(),
            }},
            upsert=True
        )

    def wait_for_pairing(self, timeout_seconds: int = PAIRING_TOKEN_TTL_SECONDS, poll_interval: int = 5) -> bool:
        """
        Poll MongoDB until this machine's record has a user_guid (pairing complete)
        or until timeout. Returns True if paired, False if timed out.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_paired():
                logger.info("Machine pairing confirmed.")
                return True
            logger.info("Waiting for pairing to complete…")
            time.sleep(poll_interval)
        return False

    def register(self) -> None:
        """Upsert this machine as online. Does NOT overwrite user_guid."""
        self.collection.update_one(
            {'machine_id': self.machine_id},
            {'$set': {
                'machine_id': self.machine_id,
                'machine_name': self.machine_name,
                'status': 'online',
                'last_seen': datetime.now().isoformat(),
                'has_local_api_key': bool(os.getenv('DEEPSEEK_API_KEY'))
            }},
            upsert=True
        )

    def report_api_key_check(self, status: str, error: str = None) -> None:
        """Record the result of an on-demand DEEPSEEK_API_KEY presence/validity check."""
        self.collection.update_one(
            {'machine_id': self.machine_id},
            {'$set': {
                'has_local_api_key': bool(os.getenv('DEEPSEEK_API_KEY')),
                'api_key_check': {
                    'status': status,
                    'checked_at': datetime.now().isoformat(),
                    'error': error
                }
            }}
        )

    def deregister(self) -> None:
        """Mark this machine as offline."""
        self.collection.update_one(
            {'machine_id': self.machine_id},
            {'$set': {
                'status': 'offline',
                'last_seen': datetime.now().isoformat()
            }}
        )
