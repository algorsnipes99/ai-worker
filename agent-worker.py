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
from concurrent.futures import ThreadPoolExecutor

import os
import time
import logging
from typing import Dict, Any, Type
import signal
import sys
import threading

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

class AgentWorker:
    """Worker that monitors MongoDB for new messages and runs agents"""

    # Initialize the worker: read env config, set up logging, thread pool, and signal handlers.
    def __init__(self):
        # Use environment variables for configuration
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DB_NAME', 'test')
        self.collection_name = os.getenv('MONGODB_COLLECTION_NAME', 'messages')
        self.api_key = os.getenv('DEEPSEEK_API_KEY')

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Thread pool for parallel processing
        self.max_workers = 5  # Configurable number of parallel executions
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.thread_local = threading.local()  # For thread-local storage

        # For graceful shutdown
        self.shutdown_flag = False
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

    # Handle SIGINT/SIGTERM gracefully: set shutdown flag and wait for the thread pool to drain.
    # @param signum: Signal number received.
    # @param frame: Current stack frame.
    def handle_shutdown(self, signum, frame):
        self.logger.info("Shutdown signal received")
        self.shutdown_flag = True

        # Shutdown thread pool gracefully
        self.logger.info("Shutting down thread pool (waiting for running tasks to complete)")
        self.executor.shutdown(wait=True)
        self.logger.info("Thread pool shutdown completed")

    # Main polling loop: connect to MongoDB, watch for run_signal and compress_conversation docs,
    # and dispatch each to a thread pool worker. Runs until shutdown_flag is set.
    def run(self):
        try:
            client = MongoClient(self.uri)
            db = client[self.db_name]
            collection = db[self.collection_name]

            self.logger.info("Starting MongoDB polling")
            poll_interval = 5  # seconds

            # Track last processed timestamp
            last_processed = None

            while not self.shutdown_flag:
                try:
                    # Query for messages with run_signal and user messages
                    query = {
                        'run_signal': True,
                        'messages': {
                            '$elemMatch': {
                                'role': 'user',
                                'content': {'$exists': True}
                            }
                        }
                    }


                    documents = collection.find(query).sort('created_at', 1)

                    for doc in documents:
                        if self.shutdown_flag:
                            break

                        # Get the latest user message
                        user_messages = [m for m in doc['messages'] if m['role'] == 'user']
                        if user_messages:
                            message = {
                                'user_request': user_messages[-1]['content'],
                                'plan_text': doc.get('plan_text', ''),
                                'parent_message_guid': doc.get('parent_message_guid'),
                                'parent_resume_guid': doc.get('guid'),
                                'child_resume_guid': doc.get('child_resume_guid'),
                                'agent_class_name': doc.get('agent_class_name'),
                                '_id': doc.get('_id', 'unknown')  # Include _id for logging
                            }

                            # Remove run_signal immediately (before processing)
                            collection.update_one(
                                {'_id': doc['_id']},
                                {'$unset': {'run_signal': ""}}
                            )

                            # Submit to thread pool for async processing
                            self.executor.submit(self._process_document_thread, message)
                            self.logger.info(f"Submitted message {message.get('_id')} to thread pool")

                    # Check for conversations pending compression
                    compress_docs = collection.find({'compress_conversation': True})
                    for doc in compress_docs:
                        if self.shutdown_flag:
                            break
                        strategy = doc.get('compression_strategy', 'remove_tool_calls')
                        guid = doc.get('guid')
                        # Clear the flags immediately so it isn't picked up again
                        collection.update_one(
                            {'_id': doc['_id']},
                            {'$unset': {'compress_conversation': '', 'compression_strategy': ''}}
                        )
                        self.executor.submit(self._process_compression_thread, guid, strategy)
                        self.logger.info(f"Submitted compression for {guid} with strategy: {strategy}")

                    time.sleep(poll_interval)

                except Exception as e:
                    self.logger.error(f"Error polling MongoDB: {e}")
                    time.sleep(poll_interval)  # Wait before retrying

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)

    # Resolve an agent_class_name string (from MongoDB) to its Python class.
    # Defaults to DatabaseAgent for unknown names.
    # @param agent_class_name: Case-insensitive agent name (e.g. "filemanageragent").
    # @returns: The resolved agent class.
    def _get_agent_class(self, agent_class_name: str) -> Type:
        mapping = {
            'databaseagent': DatabaseAgent,
            'apiagent': ApiAgent,
            'commandpromptagent': CommandPromptAgent,
            'filemanageragent': FileManagerAgent,
            'summarizationagent': SummarizationAgent,
            'codebaseexpertagent': CodebaseExpertAgent,
        }

        agent_class = mapping.get(agent_class_name.lower())
        if not agent_class:
            self.logger.warning(f"Unknown agent class: {agent_class_name}, defaulting to DatabaseAgent")
            agent_class = DatabaseAgent

        return agent_class

    # Return (or lazily create) a MongoDB client local to the calling thread.
    # Each worker thread gets its own MongoClient to avoid sharing connections.
    # @returns: A MongoClient bound to the current thread.
    def _get_thread_mongo_client(self):
        if not hasattr(self.thread_local, 'mongo_client'):
            # Create a new MongoDB client for this thread
            self.thread_local.mongo_client = MongoClient(self.uri)
            self.logger.debug(f"Created new MongoDB client for thread {threading.current_thread().name}")
        return self.thread_local.mongo_client

    # Thread target: instantiate the appropriate agent for a message and call run().
    # Logs start/finish and any exceptions but does not re-raise.
    # @param message: Dict containing user_request, plan_text, agent_class_name, and resume GUIDs.
    def _process_document_thread(self, message: Dict[str, Any]):
        thread_name = threading.current_thread().name
        message_id = message.get('_id', 'unknown')

        try:
            self.logger.info(f"Thread {thread_name} started processing message {message_id}")

            # Process the message (similar to original process_message)
            agent_class_name = message.get('agent_class_name')
            if not agent_class_name:
                self.logger.warning(f"No agent_class_name specified for message {message_id}, defaulting to DatabaseAgent")
                agent_class_name = 'databaseagent'

            agent_class = self._get_agent_class(agent_class_name)
            self.logger.info(f"Thread {thread_name} processing message {message_id} with agent class: {agent_class.__name__}")

            # Instantiate the agent
            agent = agent_class(
                user_request=message['user_request'],
                plan_text=message.get('plan_text', ""),
                api_key=self.api_key,
                parent_message_guid=message.get('parent_message_guid'),
                parent_resume_guid=message.get('parent_resume_guid'),
                child_resume_guid=message.get('child_resume_guid')
            )

            result = agent.run(message['user_request'])
            self.logger.info(f"Thread {thread_name} - Agent {agent_class.__name__} completed message {message_id} with result: {result}")

        except Exception as e:
            self.logger.error(f"Thread {thread_name} - Error processing message {message_id}: {str(e)}", exc_info=True)
        finally:
            self.logger.info(f"Thread {thread_name} finished processing message {message_id}")

    # Thread target: run the selected compression strategy against a conversation GUID.
    # @param guid: The conversation's GUID in MongoDB.
    # @param strategy: One of 'remove_tool_calls', 'summarize_messages', or 'both'.
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
            compressor = compressor_class()
            compressor.run(guid)
            self.logger.info(f"Thread {thread_name} finished compressing {guid}")
        except Exception as e:
            self.logger.error(f"Thread {thread_name} - Error compressing {guid}: {e}", exc_info=True)

    # Legacy synchronous wrapper around _process_document_thread for backward compatibility.
    # @param message: Message dict as described in _process_document_thread.
    def process_message(self, message: Dict[str, Any]):
        self._process_document_thread(message)

    # Return the last processed message ID (stub — not yet implemented).
    # @returns: None always; intended for future resumption support.
    def get_last_processed_id(self):
        # Could implement persistent storage of last processed ID
        return None

if __name__ == '__main__':
    worker = AgentWorker()
    worker.run()
