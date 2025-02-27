from pymilvus import Collection, connections  # Import the Milvus client and connections
import numpy as np
from config import config
import openai

# Establish a connection to Milvus
connections.connect(
    alias="default",  # You can use any alias you prefer
    host="localhost",  # Replace with your Milvus server host
    port="19530"  # Replace with your Milvus server port
)

# Update environment variables
MILVUS_COLLECTION_NAME = config["milvus_collection_name"]
OPENAI_API_KEY = config["openai_api_key"]

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
    """Get embedding for the provided text using OpenAI's embedding API"""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        input=text,
        model="text-embedding-ada-002"  # Use appropriate embedding model
    )
    # Extract the embedding from the response
    embedding = response.data[0].embedding
    return embedding

def search_in_milvus(search_text):
    try:
        # Convert the search text to an embedding vector
        search_vector = get_embedding(search_text)
        
        # Make sure the vector is the correct format
        search_vector = np.array(search_vector, dtype=np.float32).tolist()
        
        # Assuming 'conversations' is the name of the Milvus collection
        collection = Collection(MILVUS_COLLECTION_NAME)
        
        # Perform a search in the Milvus collection
        search_params = {
            "metric_type": "L2",  # or "IP" depending on your use case
            "params": {"nprobe": 10}
        }
        
        # Perform the search with the vector embedding
        results = collection.search(
            data=[search_vector],  # The embedding vector to search for
            anns_field="embedding",  # The field containing the vector embeddings
            param=search_params,
            limit=10,  # Limit the number of results
            output_fields=["vcon_uuid", "party_id", "text"]
        )
        
        # Process the search results
        formatted_results = []
        for i, hits in enumerate(results):
            for hit in hits:
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
                
                # Format results in a way that's useful for the LLM
                formatted_results.append({
                    "id": hit.id if hasattr(hit, 'id') else 'Unknown ID',
                    "score": round(hit.score, 4) if hasattr(hit, 'score') else 0,
                    "vcon_uuid": vcon_uuid,
                    "party_id": party_id,
                    "text": text_content[:1000] + "..." if len(text_content) > 1000 else text_content
                })
                
        return formatted_results
    except Exception as e:
        return f"Error searching in Milvus: {str(e)}" 