from pymongo import MongoClient
import os

DB_TYPE = os.getenv("DB_TYPE", "postgres")

DATE_RANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_date_range",
        "description": "Find conversations within a date range",
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
    if DB_TYPE == "mongo":
        # MongoDB query
        collection = db_conn.conversations
        results = list(collection.find({
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }))
        return results
    else:
        # PostgreSQL query
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE timestamp BETWEEN %s AND %s",
            (start_date, end_date)
        )
        results = cursor.fetchall()
        cursor.close()
        return results