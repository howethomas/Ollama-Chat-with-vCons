from pymongo import MongoClient
import os
from datetime import datetime

DB_TYPE = os.getenv("DB_TYPE", "postgres")

DATE_RANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_date_range",
        "description": "Find conversations within a date range, returns a list of UUIDs",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in ISO format"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in ISO format"
                }
            },
            "required": ["start_date", "end_date"]
        }
    }
}

def find_by_date_range(start_date, end_date, db_conn):
    # Convert input dates to ISO format if they aren't already
    start_iso = start_date if isinstance(start_date, str) else start_date.isoformat()
    end_iso = end_date if isinstance(end_date, str) else end_date.isoformat()
    
    # MongoDB query
    db = db_conn["conserver"]  # Specify the database name
    collection = db["vcons"]    # Specify the collection name
    
    # Only retrieve the uuid field and modify the query to return just UUIDs
    results = list(collection.find(
        {
            "created_at": {
                "$gte": start_iso,
                "$lte": end_iso
            }
        },
        {"uuid": 1, "_id": 0}  # Only return uuid field, exclude MongoDB's _id
    ))
    
    # Extract just the UUIDs from the results
    uuids = [doc["uuid"] for doc in results]
    return uuids