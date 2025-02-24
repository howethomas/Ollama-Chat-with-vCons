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
import openai

# Initialize session state for message history and settings
if "messages" not in st.session_state:
    st.session_state.messages = []
if "api_provider" not in st.session_state:
    st.session_state.api_provider = "ollama"
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = """You are a helpful AI assistant. You can help users search through conversation records using date ranges, party names, or conversation IDs."""

# Load environment variables from .env file
load_dotenv()

# Database configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Connect to database
conn = MongoClient(MONGO_URI)

# Move configuration elements to sidebar
with st.sidebar:
    st.header("Configuration")
    
    # API provider selection
    api_provider = st.radio(
        "Select API Provider",
        ["ollama", "openai"],
        key="api_provider"
    )
    
    # System prompt configuration
    system_prompt = st.text_area(
        "System Prompt (defines assistant behavior)",
        value=st.session_state.system_prompt,
        key="system_prompt",
        height=100
    )
    
    if st.button("Reset System Prompt"):
        st.session_state.system_prompt = """You are a helpful AI assistant. You can help users search through conversation records using date ranges, party names, or conversation IDs."""
        st.rerun()

    if api_provider == "ollama":
        # Ollama configuration
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
                available_models = ["llama2", "mistral", "codellama"]
                st.warning("Could not fetch models from Ollama, using default options")
        except requests.exceptions.RequestException:
            available_models = ["llama2", "mistral", "codellama"]
            st.warning("Could not connect to Ollama, using default options")

        default_model = os.getenv("DEFAULT_MODEL", "llama2")
        try:
            default_index = available_models.index(default_model)
        except ValueError:
            default_index = 0
            st.warning(f"Default model {default_model} not found in available models")

    else:  # OpenAI configuration
        openai.api_key = OPENAI_API_KEY
        if not OPENAI_API_KEY:
            st.error("OpenAI API key not found. Please set OPENAI_API_KEY in your .env file.")
            st.stop()
        
        # Fetch available models from OpenAI
        try:
            models = openai.models.list()
            available_models = [
                model.id for model in models 
                if model.id.startswith(('gpt-3.5', 'gpt-4', 'o1', 'o3')) and 'instruct' not in model.id
            ]
            available_models.sort()
        except openai.OpenAIError as e:
            st.warning("Could not fetch models from OpenAI, using default options")
            available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]
        
        default_model = os.getenv("DEFAULT_OPENAI_MODEL", "gpt-3.5-turbo")
        default_index = available_models.index(default_model) if default_model in available_models else 0

    model = st.selectbox("Select a model:", available_models, index=default_index)
    
    # Debug options
    show_debug = st.checkbox("Show debug messages", value=False)
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Main chat area
st.title("Chat Interface")

# Display chat messages
for message in st.session_state.messages:
    role = message["role"]
    # Skip function messages in display
    if role == "function":
        continue
    with st.chat_message(role):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to ask?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)

    try:
        # Convert session messages to API format with explicit handling
        api_messages = []
        # Add system message first if it exists
        if st.session_state.system_prompt.strip():
            api_messages.append({
                "role": "system",
                "content": st.session_state.system_prompt
            })
        for msg in st.session_state.messages:
            if msg["role"] == "tool":
                # For OpenAI, convert tool messages to function messages
                if api_provider == "openai":
                    # Try to extract function name from content if possible
                    if "find_by_date_range" in str(msg["content"]).lower():
                        function_name = "find_by_date_range"
                    elif "find_by_party" in str(msg["content"]).lower():
                        function_name = "find_by_party"
                    elif "get_conversation_by_id" in str(msg["content"]).lower():
                        function_name = "get_conversation_by_id"
                    else:
                        # Skip tool messages we can't properly convert
                        continue
                    
                    api_messages.append({
                        "role": "function",
                        "name": function_name,
                        "content": msg["content"]
                    })
            else:
                api_messages.append(msg)

        if show_debug:
            st.write("Processed API Messages:", api_messages)

        if api_provider == "ollama":
            response = requests.post(
                f"{ollama_host}/api/chat",
                json={
                    "model": model,
                    "messages": api_messages,
                    "stream": False,
                    "tools": [PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                }
            )
            
            if response.status_code == 200:
                response_json = response.json()
                assistant_response = response_json["message"]["content"]
                tool_calls = response_json["message"].get("tool_calls", [])
            else:
                st.error(f"Error: {response.status_code}")
                st.stop()

        else:  # OpenAI
            if model.startswith('o3'):
                # For o3 models, skip tools and only use basic chat
                response = openai.chat.completions.create(
                    model=model,
                    messages=[msg for msg in api_messages if msg["role"] not in ["function", "tool"]]
                )
            else:
                response = openai.chat.completions.create(
                    model=model,
                    messages=api_messages,
                    tools=[PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                )
            
            assistant_response = response.choices[0].message.content
            tool_calls = response.choices[0].message.tool_calls or []

        if show_debug:
            st.write("API Response:", response)
            
        # Handle tool calls
        if tool_calls:
            if show_debug:
                st.write("Tool calls:", tool_calls)
            for tool_call in tool_calls:
                function_name = (tool_call.function.name 
                               if api_provider == "openai" 
                               else tool_call["function"]["name"])
                
                arguments = (json.loads(tool_call.function.arguments) 
                           if api_provider == "openai" 
                           else tool_call["function"]["arguments"])

                # Store the function name before executing the tool
                current_function_name = function_name

                if function_name == "find_by_party":
                    party = arguments["party"]
                    if show_debug:
                        st.write(f"Finding vCons for party: {party}")
                    results = find_by_party(party, conn)
                elif function_name == "find_by_date_range":
                    start_date = arguments["start_date"]
                    end_date = arguments["end_date"]
                    if show_debug:
                        st.write(f"Finding vCons for date range: {start_date} to {end_date}")
                    results = find_by_date_range(start_date, end_date, conn)
                elif function_name == "get_conversation_by_id":
                    uuids = arguments["uuids"]
                    if show_debug:
                        st.write(f"Getting vCons for uuids: {uuids}")
                    results = get_conversation_by_id(uuids, conn)
                
                # Add tool results to message history with the correct format
                if api_provider == "ollama":
                    st.session_state.messages.append({
                        "role": "tool",
                        "content": str(results),
                    })
                else:  # OpenAI
                    st.session_state.messages.append({
                        "role": "function",
                        "name": current_function_name,  # Make sure to include the function name
                        "content": str(results),
                    })

                # Get final response with tool results
                if api_provider == "ollama":
                    final_response = requests.post(
                        f"{ollama_host}/api/chat",
                        json={
                            "model": model,
                            "messages": [
                                {"role": msg["role"], "content": msg["content"]}
                                for msg in st.session_state.messages
                                if msg.get("content") is not None  # Filter out null content
                            ],
                            "stream": False,
                            "tools": [PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                        }
                    )
                    if final_response.status_code == 200:
                        assistant_response = final_response.json()["message"]["content"]
                        if assistant_response is None:
                            assistant_response = "I apologize, but I encountered an error processing the response. Please try asking your question again."
                            # TODO: Log the error
                            st.error(f"Error: {final_response}")
                else:  # OpenAI
                    if model.startswith('o3'):
                        final_response = openai.chat.completions.create(
                            model=model,
                            messages=[msg for msg in st.session_state.messages 
                                     if msg.get("content") is not None and msg["role"] not in ["function", "tool"]]
                        )
                    else:
                        final_response = openai.chat.completions.create(
                            model=model,
                            messages=[msg for msg in st.session_state.messages if msg.get("content") is not None],
                            tools=[PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                        )
                    assistant_response = final_response.choices[0].message.content
                    if assistant_response is None and not final_response.choices[0].message.tool_calls:
                        assistant_response = "I apologize, but I encountered an error processing the response. Please try asking your question again."
                        # TODO: Log the error
                        st.error(f"Error: {final_response}")
                    elif assistant_response is None:
                        # This is a normal tool call response, no need for error handling
                        pass


        # Add assistant response to message history and display it
        if assistant_response:  # Only add non-null responses
            st.session_state.messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            with st.chat_message("assistant"):
                st.write(assistant_response)
            
    except (requests.exceptions.RequestException, openai.OpenAIError) as e:
        st.error(f"API Error: {str(e)}")
        if api_provider == "ollama":
            st.info("Make sure Ollama is running and accessible.")
        else:
            st.info("Check your OpenAI API key and connection.")

# Replace the always-visible debug expander with a conditional one
if show_debug:
    with st.expander("Debug"):
        st.write(st.session_state.messages)