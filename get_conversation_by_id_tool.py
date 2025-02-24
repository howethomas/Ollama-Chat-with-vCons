from pymongo import MongoClient

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

def get_conversation_by_id(uuids, db_conn):
    # Ensure uuids is a list
    if isinstance(uuids, str):
        uuids = [uuids]
    
    # Limit to maximum 10 UUIDs
    uuids = uuids[:10]
    
    db = db_conn["conserver"]
    collection = db["vcons"]
    
    # Find all conversations matching the UUIDs
    results = list(collection.find({"uuid": {"$in": uuids}}))
    return results
