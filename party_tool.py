from pymongo import MongoClient
from config import config

# Update environment variables
DB_NAME = config["db_name"]
COLLECTION_NAME = config["collection_name"]

PARTY_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_party",
        "description": "Find conversations by party name",
        "parameters": {
            "type": "object",
            "properties": {
                "party": {
                    "type": "string",
                    "description": "Name of the party to search for"
                }
            },
            "required": ["party"]
        }
    }
}

def find_by_party(party, db_conn):
    # MongoDB query to match party across tel, mailto, or name fields in parties array
    collection = db_conn[DB_NAME][COLLECTION_NAME]
    query = {
        "$or": [
            {"parties.tel": party},
            {"parties.mailto": party},
            {"parties.name": party}
        ]
    }
    results = list(collection.find(query, {"uuid": 1, "_id": 0}))
    # Extract and return just the UUIDs
    return [doc["uuid"] for doc in results]
