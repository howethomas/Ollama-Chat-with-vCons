from pymongo import MongoClient
import os

DB_TYPE = os.getenv("DB_TYPE", "postgres")

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
    if DB_TYPE == "mongo":
        # MongoDB query
        collection = db_conn.conversations
        results = list(collection.find({"parties": party}))
        return results
    else:
        # PostgreSQL query
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE parties @> %s", ([party],))
        results = cursor.fetchall()
        cursor.close()
        return results