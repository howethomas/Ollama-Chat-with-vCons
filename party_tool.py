from pymongo import MongoClient
from config import config
from pymilvus import Collection  # Import the Milvus client

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
    print(results)
    return [doc["uuid"] for doc in results]

# Add a new function to search in Milvus
def search_in_milvus(search_text, milvus_conn):
    # Assuming 'conversations' is the name of the Milvus collection
    collection = Collection("conversations")
    
    # Perform a search in the Milvus collection
    search_params = {
        "metric_type": "L2",  # or "IP" depending on your use case
        "params": {"nprobe": 10}
    }
    
    # Perform the search
    results = collection.search(
        data=[search_text],  # The text to search for
        anns_field="embedding",  # The field containing the vector embeddings
        param=search_params,
        limit=10,  # Limit the number of results
        expr=None  # You can add additional filtering criteria if needed
    )
    
    # Extract and return the UUIDs of the conversations
    return [result.id for result in results[0]]  # Assuming results[0] contains the first search result
