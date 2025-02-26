from pymongo import MongoClient
from datetime import datetime
from config import config
import logging
from dateutil import parser as date_parser

# Update environment variables
DB_NAME = config["db_name"]
COLLECTION_NAME = config["collection_name"]

DATE_RANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_date_range",
        "description": "Find conversations within a specific time range. Returns conversation UUIDs that occurred between the specified start and end dates/times.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date/time in ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). If only date is provided, the time will default to 00:00:00 (start of day)."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date/time in ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). If only date is provided, the time will default to 23:59:59 (end of day)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 100, max: 1000). Use with offset for pagination.",
                    "default": 100
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip. Use with limit for pagination to retrieve subsequent pages.",
                    "default": 0
                },
                "sort": {
                    "type": "string",
                    "description": "Specify sort order: 'newest' for most recent first, 'oldest' for oldest first. Defaults to newest.",
                    "enum": ["newest", "oldest"],
                    "default": "newest"
                }
            },
            "required": ["start_date", "end_date"]
        },
        "examples": [
            {
                "start_date": "2023-01-01",
                "end_date": "2023-01-31"
            },
            {
                "start_date": "2023-01-01T13:00:00",
                "end_date": "2023-01-01T14:30:00",
                "limit": 50
            },
            {
                "start_date": "2023-01-01",
                "end_date": "2023-01-31",
                "limit": 100,
                "offset": 200,
                "sort": "oldest"
            }
        ]
    }
}

def find_by_date_range(start_date, end_date, db_conn, limit=100, offset=None, sort=None):
    """
    Find conversations within a datetime range.
    
    Args:
        start_date (str or datetime): Start of the time range
        end_date (str or datetime): End of the time range
        db_conn: Database connection
        limit (int): Maximum number of results to return
        offset (int): Number of results to skip
        sort (str): Sort order - 'newest' or 'oldest'
        
    Returns:
        list: List of conversation UUIDs matching the time range
    """
    logger = logging.getLogger("llm_api")
    logger.info(f"Finding conversations between {start_date} and {end_date}")
    
    # Handle date parsing with error handling
    try:
        # Parse string dates if necessary, preserving time components
        if isinstance(start_date, str):
            try:
                start_dt = date_parser.parse(start_date)
                # If no time was specified, set to start of day
                if start_date.find(':') == -1:
                    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                logger.error(f"Invalid start date format: {start_date}")
                return []
        else:
            start_dt = start_date
            
        if isinstance(end_date, str):
            try:
                end_dt = date_parser.parse(end_date)
                # If no time was specified, set to end of day
                if end_date.find(':') == -1:
                    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError:
                logger.error(f"Invalid end date format: {end_date}")
                return []
        else:
            end_dt = end_date
        
        # Convert to ISO format strings for MongoDB
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()
        
        logger.info(f"Parsed time range: {start_iso} to {end_iso}")
    except Exception as e:
        logger.error(f"Error parsing date range: {e}")
        return []
    
    # MongoDB query
    db = db_conn[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Apply a reasonable default limit if none provided
    if limit is None:
        limit = 100
    
    # Ensure limit is not excessive
    MAX_ALLOWED_LIMIT = 1000
    if limit > MAX_ALLOWED_LIMIT:
        logger.warning(f"Requested limit {limit} exceeds maximum allowed {MAX_ALLOWED_LIMIT}. Using {MAX_ALLOWED_LIMIT} instead.")
        limit = MAX_ALLOWED_LIMIT
    
    # Create the base query with time range filter
    query_filter = {
        "created_at": {
            "$gte": start_iso,
            "$lte": end_iso
        }
    }
    
    logger.debug(f"MongoDB query filter: {query_filter}")
    
    # Count total matching documents
    total_matching = collection.count_documents(query_filter)
    logger.info(f"Total matching documents: {total_matching}")
    
    # Create the base query
    query = collection.find(
        query_filter,
        {"uuid": 1, "_id": 0}
    )
    
    # Apply sort if provided
    if sort:
        if sort == "newest":
            query = query.sort("created_at", -1)  # Descending order
        elif sort == "oldest":
            query = query.sort("created_at", 1)   # Ascending order
        else:
            logger.warning(f"Unknown sort value: {sort}. Using 'newest' as default.")
            query = query.sort("created_at", -1)  # Default to newest first
    else:
        # Default sort is newest first
        query = query.sort("created_at", -1)
    
    # Apply offset (skip) if provided
    if offset:
        query = query.skip(offset)
    
    # Apply limit
    query = query.limit(limit)
    
    # Execute the query and get results
    results = list(query)
    
    logger.info(f"Retrieved {len(results)} documents (limit: {limit}, offset: {offset or 0})")
    
    # Extract just the UUIDs from the results
    uuids = [doc["uuid"] for doc in results]
    
    # If we hit the limit, log a warning
    if len(results) == limit and limit < total_matching:
        logger.warning(f"Result set limited to {limit} records. {total_matching - limit} more records match the query.")
    
    return uuids