from pymongo import MongoClient
from config import config
import logging

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

def get_conversation_by_id(uuids, db_conn, max_results=20):
    # Ensure uuids is a list
    if isinstance(uuids, str):
        uuids = [uuids]
    
    # Limit to maximum 10 UUIDs
    uuids = uuids[:10]
    
    try:
        print(f"DB_NAME: {DB_NAME}")
        print(f"COLLECTION_NAME: {COLLECTION_NAME}")
        db = db_conn[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        print(f"Searching for conversations with UUIDs: {uuids}")
        
        # First, let's count total documents in collection
        total_docs = collection.count_documents({})
        print(f"Total documents in collection: {total_docs}")
        
        # Let's see what the first few documents look like
        sample_doc = collection.find_one()
        if sample_doc:
            print("Sample document structure:", sample_doc.keys())
            if 'uuid' in sample_doc:
                print("Sample UUID format:", sample_doc['uuid'])
        
        # Now perform the search
        query_filter = {"uuid": {"$in": uuids}}
        results = list(collection.find(query_filter))[:max_results]
        print(f"Found {len(results)} results")
        
        if len(results) > max_results:
            print(f"Result set truncated: {len(results)} items found, returning first {max_results}")
        
        return results
    except Exception as e:
        print(f"Error querying MongoDB: {str(e)}")
        return []
