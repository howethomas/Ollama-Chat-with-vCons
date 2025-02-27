from pymilvus import Collection, connections
import numpy as np
from config import config
import openai
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get configuration values
MILVUS_COLLECTION_NAME = config["milvus_collection_name"]
OPENAI_API_KEY = config["openai_api_key"]
MILVUS_HOST = config.get("milvus_host", "localhost")
MILVUS_PORT = config.get("milvus_port", "19530")
EMBEDDING_MODEL = config.get("embedding_model", "text-embedding-ada-002")
SEARCH_RESULT_LIMIT = config.get("search_result_limit", 10)

# Initialize OpenAI client once
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Establish a connection to Milvus
try:
    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT
    )
    logger.info(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")
except Exception as e:
    logger.error(f"Failed to connect to Milvus: {str(e)}")

MILVUS_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_in_milvus",
        "description": "Search for conversation transcripts and summaries in Milvus",
        "parameters": {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "Text to search for in the Milvus database"
                }
            },
            "required": ["search_text"]
        }
    }
}

def get_embedding(text):
    """
    Get embedding for the provided text using OpenAI's embedding API
    
    Args:
        text (str): The text to generate embeddings for
        
    Returns:
        list: The embedding vector
    """
    try:
        response = openai_client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise

def extract_entity_data(hit):
    """
    Helper function to extract entity data regardless of Milvus SDK version
    
    Args:
        hit: A search hit from Milvus
        
    Returns:
        tuple: (vcon_uuid, party_id, text_content)
    """
    # Initialize with default values
    vcon_uuid = 'Unknown'
    party_id = 'N/A'
    text_content = ''
    
    # Handle different Milvus SDK versions
    if hasattr(hit, 'entity') and isinstance(hit.entity, dict):
        # Direct dictionary access for newer SDK versions
        vcon_uuid = hit.entity.get('vcon_uuid', 'Unknown')
        party_id = hit.entity.get('party_id', 'N/A')
        text_content = hit.entity.get('text', '')
    elif hasattr(hit, 'entity') and hasattr(hit.entity, 'fields'):
        # Access through fields attribute for some SDK versions
        fields = hit.entity.fields
        vcon_uuid = fields.get('vcon_uuid', 'Unknown')
        party_id = fields.get('party_id', 'N/A')
        text_content = fields.get('text', '')
    else:
        # Fallback for other SDK versions
        vcon_uuid = getattr(hit, 'vcon_uuid', 'Unknown')
        party_id = getattr(hit, 'party_id', 'N/A')
        text_content = getattr(hit, 'text', '')
    
    return vcon_uuid, party_id, text_content

def search_in_milvus(search_text):
    """
    Search for similar content in Milvus using vector similarity
    
    Args:
        search_text (str): The text to search for
        
    Returns:
        list: Formatted search results or error message
    """
    try:
        # Convert the search text to an embedding vector
        search_vector = get_embedding(search_text)
        
        # Make sure the vector is the correct format
        search_vector = np.array(search_vector, dtype=np.float32).tolist()
        
        # Get collection
        collection = Collection(MILVUS_COLLECTION_NAME)
        
        # Load collection - this is safe to call even if already loaded
        try:
            collection.load()
            logger.info(f"Collection {MILVUS_COLLECTION_NAME} loaded successfully")
        except Exception as load_error:
            logger.warning(f"Note when loading collection: {str(load_error)}")
        
        # Perform a search in the Milvus collection
        search_params = {
            "metric_type": "L2",  # or "IP" depending on your use case
            "params": {"nprobe": 10}
        }
        
        # Perform the search with the vector embedding
        results = collection.search(
            data=[search_vector],
            anns_field="embedding",
            param=search_params,
            limit=SEARCH_RESULT_LIMIT,
            output_fields=["vcon_uuid", "party_id", "text"]
        )
        
        # Process the search results
        formatted_results = []
        for hits in results:
            for hit in hits:
                # Extract entity data
                vcon_uuid, party_id, text_content = extract_entity_data(hit)
                
                # Format results in a way that's useful for the LLM
                formatted_results.append({
                    "id": hit.id if hasattr(hit, 'id') else 'Unknown ID',
                    "score": round(hit.score, 4) if hasattr(hit, 'score') else 0,
                    "vcon_uuid": vcon_uuid,
                    "party_id": party_id,
                    "text": text_content[:1000] + "..." if len(text_content) > 1000 else text_content,
                    "truncated": len(text_content) > 1000
                })
        
        # Release collection resources
        collection.release()
        
        return formatted_results
    except Exception as e:
        logger.error(f"Error searching in Milvus: {str(e)}")
        return f"Error searching in Milvus: {str(e)}"

def cleanup_connections():
    """
    Disconnect from Milvus - call this when shutting down your application
    """
    try:
        connections.disconnect("default")
        logger.info("Disconnected from Milvus")
    except Exception as e:
        logger.error(f"Error disconnecting from Milvus: {str(e)}") 