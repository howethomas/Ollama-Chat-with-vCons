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
    # MongoDB query
    print("Using MongoDB")
    print("db_conn types: ", type(db_conn))
    # Use the conserver database
    db = db_conn["conserver"]
    print("db types: ", type(db))
    # Use the vcons collection
    collection = db["vcons"]
    print("collection types: ", type(collection))
    result = collection.find_one({"_id": uuid})
    print("result types: ", type(result))
    return result
