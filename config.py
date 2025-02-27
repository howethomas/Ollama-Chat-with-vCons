import streamlit as st
from pathlib import Path
import toml

# Default configuration
DEFAULT_CONFIG = {
    "mongo_uri": "mongodb://localhost:27017",
    "db_name": "conserver",
    "collection_name": "vcons",
    "openai_api_key": "",
    "ollama_host": "http://localhost:11434",
    "default_model": "llama3.2:latest",
    "default_openai_model": "gpt-3.5-turbo",
    "milvus_host": "localhost",
    "milvus_port": 19530,
    "milvus_db_name": "default",
    "milvus_collection_name": "vcons_collection",
    "milvus_anns_field": "embedding"
}

def ensure_secrets_file():
    """Ensure .streamlit/secrets.toml exists with default values if needed"""
    secrets_dir = Path(".streamlit")
    secrets_path = secrets_dir / "secrets.toml"
    
    # Create .streamlit directory if it doesn't exist
    secrets_dir.mkdir(exist_ok=True)
    
    # Create secrets.toml with defaults if it doesn't exist
    if not secrets_path.exists():
        with open(secrets_path, "w") as f:
            toml.dump(DEFAULT_CONFIG, f)

# Ensure secrets file exists
ensure_secrets_file()

# Use Streamlit's built-in secrets management
config = st.secrets 
print("Config:", config)