# Environment Configuration

This project now uses environment variables for configuration instead of hardcoded values.

## Files Created

1. **`.env.example`** - Template file with placeholder values
2. **`.env`** - Actual configuration file (added to `.gitignore`)
3. **`.gitignore`** - Updated to include `.env` file

## Environment Variables

### MongoDB Configuration
- `MONGODB_URI` - MongoDB connection string (e.g., `mongodb://username:password@host:port`)
- `MONGODB_DB_NAME` - Database name (default: `test`)
- `MONGODB_COLLECTION_NAME` - Collection for messages (default: `messages`)
- `MONGODB_STATE_COLLECTION` - Collection for execution states (default: `states`)

### Redis Pub/Sub Configuration
- `REDIS_URL` - Redis connection string (default: `redis://localhost:6379`)
- `REDIS_CHANNEL` - Channel the worker subscribes to (default: `ai-worker:events`)
- `REDIS_FALLBACK_POLL_INTERVAL` - Seconds between fallback MongoDB scans for missed events (default: `60`)

### DeepSeek API Configuration
- `DEEPSEEK_API_KEY` - Your DeepSeek API key
- `DEEPSEEK_API_URL` - DeepSeek API endpoint (default: `https://api.deepseek.com/v1/chat/completions`)

## Setup Instructions

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** with your actual values:
   ```bash
   # Edit using your preferred text editor
   notepad .env
   ```

3. **Required values to update:**
   - `MONGODB_URI` - Your MongoDB connection string
   - `DEEPSEEK_API_KEY` - Your DeepSeek API key

## How It Works

The application loads environment variables from the `.env` file using `python-dotenv`:

- `agent-worker.py` - Main entry point loads `.env` on startup
- `services/message_service.py` - Loads `.env` when imported
- `services/state_service.py` - Loads `.env` when imported
- `functions/delegate_to_agent_function.py` - Uses environment variables for API key

## Fallback Values

If environment variables are not set, the application uses fallback/default values:
- MongoDB: Uses the original hardcoded connection string
- DeepSeek API: Uses the original hardcoded API key

## Security Notes

- The `.env` file is excluded from version control (added to `.gitignore`)
- Never commit the `.env` file with real credentials
- Use `.env.example` as a template for required variables
- For production, consider using system environment variables or a secrets manager

## Files Updated

The following files were updated to use environment variables:

1. `agent-worker.py` - MongoDB URI, DB name, collection name, API key
2. `services/message_service.py` - MongoDB URI, DB name, collection name
3. `services/state_service.py` - MongoDB URI, DB name, collection name
4. `functions/delegate_to_agent_function.py` - DeepSeek API key

## Testing

To verify configuration is working:

```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('MONGODB_URI:', os.getenv('MONGODB_URI', 'Not set'))"