from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from utils.machine_info import get_machine_id, get_machine_name
from datetime import datetime
import os

from dotenv import load_dotenv
load_dotenv()

HARDCODED_USER_GUID = 'm8JLGcC0mxMWHWQ1QbO2NJ3xlgz2'


class MachineService:
    """Registers and tracks this machine's online/offline status in MongoDB."""

    def __init__(self):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.machines_collection_name = os.getenv('MONGODB_MACHINES_COLLECTION', 'machines')
        self.machine_id = get_machine_id()
        self.machine_name = get_machine_name()

        try:
            self.client = MongoClient(self.uri)
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.machines_collection_name]
        except ConnectionFailure as e:
            raise ConnectionError(f"MachineService failed to connect to MongoDB: {e}")

    # Upsert this machine as online. Creates the record if it doesn't exist.
    def register(self) -> None:
        self.collection.update_one(
            {'machine_id': self.machine_id},
            {'$set': {
                'machine_id': self.machine_id,
                'machine_name': self.machine_name,
                'user_guid': HARDCODED_USER_GUID,
                'status': 'online',
                'last_seen': datetime.now().isoformat()
            }},
            upsert=True
        )

    # Mark this machine as offline.
    def deregister(self) -> None:
        self.collection.update_one(
            {'machine_id': self.machine_id},
            {'$set': {
                'status': 'offline',
                'last_seen': datetime.now().isoformat()
            }}
        )
