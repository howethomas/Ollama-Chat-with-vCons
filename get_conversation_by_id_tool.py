from pymongo import MongoClient

GET_CONVERSATION_BY_ID = {
    "type": "function",
    "function": {
        "name": "get_conversation_by_id",
        "description": "Get a conversation by its UUID",
        "parameters": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "UUID of the conversation"
                }
            },
            "required": ["uuid"]
        }
    }
}

def get_conversation_by_id(uuid, db_conn):
    db = db_conn["conserver"]
    collection = db["vcons"]
    result = collection.find_one({"uuid": uuid})
    return result
