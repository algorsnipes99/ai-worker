from pymongo import MongoClient
from conversation_compressor.tool_call_remover import ToolCallRemover
from conversation_compressor.message_summarizer import MessageSummarizer
from conversation_compressor.combined_compressor import CombinedCompressor
from agents.api_agent import ApiAgent
from agents.database_agent import DatabaseAgent
from agents.command_prompt_agent import CommandPromptAgent
from agents.file_manager_agent import FileManagerAgent
from agents.summarization_agent import SummarizationAgent
from agents.codebase_expert_agent import CodebaseExpertAgent
from agents.custom_agent import CustomAgent
from concurrent.futures import ThreadPoolExecutor
from utils.machine_info import get_machine_id
from services.machine_service import MachineService
from services.redis_service import RedisService

import os
import logging
import secrets
import webbrowser
from typing import Dict, Any, Type
import signal
import sys
import threading

from dotenv import load_dotenv
load_dotenv()


class AgentWorker:
    """Worker that listens on Redis pub/sub for task signals and runs agents."""

    def __init__(self):
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.collection_name = os.getenv('MONGODB_COLLECTION_NAME', 'messages')
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.machine_id = get_machine_id()
        self.machine_service = MachineService()

        if not self.machine_service.is_paired():
            ui_url = os.getenv('UI_URL', 'http://localhost:3000').rstrip('/')
            token = secrets.token_urlsafe(32)
            self.machine_service.create_pairing_token(token)
            pair_url = f"{ui_url}/pair/{token}"
            logging.info(f"Machine not paired. Opening browser for pairing: {pair_url}")
            webbrowser.open(pair_url)
            paired = self.machine_service.wait_for_pairing()
            if not paired:
                logging.error("Pairing timed out (10 minutes). Exiting.")
                sys.exit(1)

        self.machine_service.register()

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        self.max_workers = 5
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.thread_local = threading.local()

        self.shutdown_flag = False
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

    def handle_shutdown(self, _signum, _frame):
        self.logger.info("Shutdown signal received")
        self.shutdown_flag = True
        self.logger.info("Shutting down thread pool (waiting for running tasks to complete)")
        self.executor.shutdown(wait=True)
        self.logger.info("Thread pool shutdown completed")
        self.machine_service.deregister()
        self.logger.info("Machine marked offline")

    def run(self):
        try:
            client = MongoClient(self.uri)
            db = client[self.db_name]
            collection = db[self.collection_name]

            redis_service = RedisService()

            self.logger.info(f"Listening for Redis events on channel: {redis_service.channel}")
            for event in redis_service.listen():
                if self.shutdown_flag:
                    break
                self._handle_redis_event(event, collection)

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)
        finally:
            try:
                redis_service.close()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Redis event handling
    # -------------------------------------------------------------------------

    def _handle_redis_event(self, event: dict, collection):
        event_type = event.get('type')
        guid = event.get('guid')
        target_machine_id = event.get('target_machine_id')

        if not guid:
            self.logger.warning(f"Redis event missing guid: {event}")
            return

        if target_machine_id and target_machine_id != self.machine_id:
            return  # not for this machine

        if event_type == 'run_signal':
            self._process_run_signal(guid, collection)
        elif event_type == 'compress_conversation':
            self._process_compress_signal(guid, collection)
        else:
            self.logger.warning(f"Unknown Redis event type: {event_type}")

    def _process_run_signal(self, guid: str, collection):
        doc = collection.find_one({
            'guid': guid,
            'run_signal': True,
            'messages': {'$elemMatch': {'role': 'user', 'content': {'$exists': True}}},
            '$or': [
                {'target_machine_id': {'$exists': False}},
                {'target_machine_id': None},
                {'target_machine_id': self.machine_id}
            ]
        })
        if not doc:
            return  # already processed or machine mismatch

        user_messages = [m for m in doc['messages'] if m['role'] == 'user']
        if not user_messages:
            return

        message = {
            'user_request': user_messages[-1]['content'],
            'plan_text': doc.get('plan_text', ''),
            'parent_message_guid': doc.get('parent_message_guid'),
            'parent_resume_guid': doc.get('guid'),
            'child_resume_guid': doc.get('child_resume_guid'),
            'agent_class_name': doc.get('agent_class_name'),
            'model_name': doc.get('model_name', 'deepseek-v4-flash'),
            'available_tools': doc.get('available_tools', []),
            '_id': doc.get('_id', 'unknown')
        }

        collection.update_one({'_id': doc['_id']}, {'$unset': {'run_signal': ""}})
        self.executor.submit(self._process_document_thread, message)
        self.logger.info(f"Submitted message {message.get('_id')} to thread pool")

    def _process_compress_signal(self, guid: str, collection):
        doc = collection.find_one({'guid': guid, 'compress_conversation': True})
        if not doc:
            return  # already processed

        strategy = doc.get('compression_strategy', 'remove_tool_calls')
        collection.update_one(
            {'_id': doc['_id']},
            {'$unset': {'compress_conversation': '', 'compression_strategy': ''}}
        )
        self.executor.submit(self._process_compression_thread, guid, strategy)
        self.logger.info(f"Submitted compression for {guid} with strategy: {strategy}")

    # -------------------------------------------------------------------------
    # Thread workers
    # -------------------------------------------------------------------------

    def _get_agent_class(self, agent_class_name: str) -> Type:
        mapping = {
            'databaseagent': DatabaseAgent,
            'apiagent': ApiAgent,
            'commandpromptagent': CommandPromptAgent,
            'filemanageragent': FileManagerAgent,
            'summarizationagent': SummarizationAgent,
            'codebaseexpertagent': CodebaseExpertAgent,
            'customagent': CustomAgent,
        }
        agent_class = mapping.get(agent_class_name.lower())
        if not agent_class:
            self.logger.warning(f"Unknown agent class: {agent_class_name}, defaulting to DatabaseAgent")
            agent_class = DatabaseAgent
        return agent_class

    def _get_thread_mongo_client(self):
        if not hasattr(self.thread_local, 'mongo_client'):
            self.thread_local.mongo_client = MongoClient(self.uri)
            self.logger.debug(f"Created new MongoDB client for thread {threading.current_thread().name}")
        return self.thread_local.mongo_client

    def _process_document_thread(self, message: Dict[str, Any]):
        thread_name = threading.current_thread().name
        message_id = message.get('_id', 'unknown')
        try:
            self.logger.info(f"Thread {thread_name} started processing message {message_id}")
            agent_class_name = message.get('agent_class_name')
            if not agent_class_name:
                self.logger.warning(f"No agent_class_name for message {message_id}, defaulting to DatabaseAgent")
                agent_class_name = 'databaseagent'

            agent_class = self._get_agent_class(agent_class_name)
            self.logger.info(f"Thread {thread_name} processing {message_id} with {agent_class.__name__}")

            agent = agent_class(
                user_request=message['user_request'],
                plan_text=message.get('plan_text', ""),
                api_key=self.api_key,
                parent_message_guid=message.get('parent_message_guid'),
                parent_resume_guid=message.get('parent_resume_guid'),
                child_resume_guid=message.get('child_resume_guid'),
                model_name=message.get('model_name', 'deepseek-v4-flash'),
                available_tools=message.get('available_tools', [])
            )
            result = agent.run(message['user_request'])
            self.logger.info(f"Thread {thread_name} - {agent_class.__name__} completed {message_id}: {result}")
        except Exception as e:
            self.logger.error(f"Thread {thread_name} - Error processing {message_id}: {str(e)}", exc_info=True)
        finally:
            self.logger.info(f"Thread {thread_name} finished processing {message_id}")

    def _process_compression_thread(self, guid: str, strategy: str):
        thread_name = threading.current_thread().name
        self.logger.info(f"Thread {thread_name} compressing {guid} with strategy: {strategy}")
        try:
            compressor_map = {
                'remove_tool_calls': ToolCallRemover,
                'summarize_messages': MessageSummarizer,
                'both': CombinedCompressor,
            }
            compressor_class = compressor_map.get(strategy, ToolCallRemover)
            compressor_class().run(guid)
            self.logger.info(f"Thread {thread_name} finished compressing {guid}")
        except Exception as e:
            self.logger.error(f"Thread {thread_name} - Error compressing {guid}: {e}", exc_info=True)

    def process_message(self, message: Dict[str, Any]):
        self._process_document_thread(message)

    def get_last_processed_id(self):
        return None


if __name__ == '__main__':
    worker = AgentWorker()
    worker.run()
