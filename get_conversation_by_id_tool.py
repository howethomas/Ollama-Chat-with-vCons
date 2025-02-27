from pymongo import MongoClient
from config import config
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Update environment variables
DB_NAME = config["db_name"]
COLLECTION_NAME = config["collection_name"]

GET_CONVERSATION_BY_ID = {
    "type": "function",
    "function": {
        "name": "get_conversation_by_id",
        "description": "Get one or more conversations by their UUIDs (maximum 10)",
        "parameters": {
            "type": "object",
            "properties": {
                "uuids": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of UUIDs of the conversations (max 10)",
                    "maxItems": 10
                }
            },
            "required": ["uuids"]
        }
    }
}

def get_conversation_by_id(uuids, db_conn, max_results=10):
    # Ensure uuids is a list
    if isinstance(uuids, str):
        uuids = [uuids]
    
    # Limit to maximum 10 UUIDs
    uuids = uuids[:10]
    
    try:
        logger.debug(f"Querying database {DB_NAME}.{COLLECTION_NAME} for UUIDs: {uuids}")
        db = db_conn[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # Perform the search
        query_filter = {"uuid": {"$in": uuids}}
        results = list(collection.find(query_filter))[:max_results]
        
        logger.info(f"Found {len(results)} conversations for the requested UUIDs")
        return results
    except Exception as e:
        logger.error(f"Error querying MongoDB: {str(e)}")
        return []
