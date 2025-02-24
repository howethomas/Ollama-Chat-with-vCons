from party_tool import PARTY_TOOL, find_by_party
from date_range_tool import DATE_RANGE_TOOL, find_by_date_range
from get_conversation_by_id_tool import GET_CONVERSATION_BY_ID, get_conversation_by_id
import streamlit as st
import requests
import json
# Add in postgres connection
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Initialize session state for message history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Load environment variables from .env file
load_dotenv()

# Database configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Print the environment variables
print("MONGO_URI: ", MONGO_URI)

# Connect to database based on DB_TYPE
conn = MongoClient(MONGO_URI)
    
# Ollama host configuration
ollama_host = st.text_input(
    "Ollama Host", 
    value=os.getenv("OLLAMA_HOST", "http://localhost:11434"), 
    key="ollama_host"
)

# Fetch available models from Ollama
try:
    models_response = requests.get(f"{ollama_host}/api/tags")
    if models_response.status_code == 200:
        available_models = [model["name"] for model in models_response.json()["models"]]
    else:
        available_models = ["llama2", "mistral", "codellama"]  # fallback options
        st.warning("Could not fetch models from Ollama, using default options")
except requests.exceptions.RequestException:
    available_models = ["llama2", "mistral", "codellama"]  # fallback options
    st.warning("Could not connect to Ollama, using default options")

# Update model selection to use environment default
default_model = os.getenv("DEFAULT_MODEL", "llama3.2:latest")
try:
    default_index = available_models.index(default_model)
except ValueError:
    default_index = 0
    st.warning(f"Default model {default_model} not found in available models")

model = st.selectbox("Select a model:", available_models, index=default_index)

# Create two columns for debug checkbox and clear button
col1, col2 = st.columns(2)

# Set a checkbox to show debug messages in the first column
with col1:
    show_debug = st.checkbox("Show debug messages", value=False)

# Add a clear button in the second column
with col2:
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Debug check
if not hasattr(st.session_state, 'messages'):
    st.warning("Session state 'messages' not initialized!")
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to ask?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)

    # Prepare the API request with chat format
    try:
        # Convert session messages to Ollama chat format
        ollama_messages = [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in st.session_state.messages
        ]
        
        response = requests.post(
            f"{ollama_host}/api/chat",
            json={
                "model": model,
                "messages": ollama_messages,
                "stream": False,
                "tools": [PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
            }
        )
        
        if show_debug:
            st.write(response.json())
            
        if response.status_code == 200:
            response_json = response.json()
            assistant_response = response_json["message"]["content"]
            
            # Check for tool calls in the response
            if "tool_calls" in response_json["message"]:
                st.write(response_json["message"]["tool_calls"])
                for tool_call in response_json["message"]["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    if function_name == "find_by_party":
                        party = tool_call["function"]["arguments"]["party"]
                        st.write(f"Finding vCons for party: {party}")
                        results = find_by_party(party, conn)
                        st.write(results)
                    elif function_name == "find_by_date_range":
                        start_date = tool_call["function"]["arguments"]["start_date"]
                        end_date = tool_call["function"]["arguments"]["end_date"]
                        st.write(f"Finding vCons for date range: {start_date} to {end_date}")
                        results = find_by_date_range(start_date, end_date, conn)
                        st.write(results)
                    elif function_name == "get_conversation_by_id":
                        uuid = tool_call["function"]["arguments"]["uuid"]
                        st.write(f"Getting vCon for uuid: {uuid}")
                        results = get_conversation_by_id(uuid, conn)
                        st.write(results)

                    # Add tool results to message history
                    st.session_state.messages.append({
                        "role": "tool",
                        "content": str(results),  # Convert results to string for chat context
                    })
                    
                    # Update ollama_messages with the new tool response
                    ollama_messages = [
                        {"role": msg["role"], "content": msg["content"]} 
                        for msg in st.session_state.messages
                    ]

                    # Get final response from Ollama with tool results
                    final_response = requests.post(
                        f"{ollama_host}/api/chat",
                        json={
                            "model": model,
                            "messages": ollama_messages,
                            "stream": False,
                            "tools": [PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                        }
                    )
                    
                    if show_debug:
                        st.write(final_response.json())
                        
                    if final_response.status_code == 200:
                        assistant_response = final_response.json()["message"]["content"]
                    else:
                        st.error(f"Error in final response: {final_response.status_code}")
        
            # Add assistant response to message history and display it
            st.session_state.messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            with st.chat_message("assistant"):
                st.write(assistant_response)
                
        else:
            st.error(f"Error: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to Ollama API: {str(e)}")
        st.info("Make sure Ollama is running and accessible.")

with st.expander("Debug"):
    st.write(st.session_state.messages)