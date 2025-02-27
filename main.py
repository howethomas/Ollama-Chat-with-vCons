from party_tool import PARTY_TOOL, find_by_party
from date_range_tool import DATE_RANGE_TOOL, find_by_date_range
from get_conversation_by_id_tool import GET_CONVERSATION_BY_ID, get_conversation_by_id
from milvus_search_tool import MILVUS_SEARCH_TOOL, search_in_milvus
import streamlit as st
import requests
import json
# Add in postgres connection
from pymongo import MongoClient
import os
from config import config
import openai
from openai import OpenAI
import logging
import datetime
import traceback
import hashlib
import time
from milvus_search_tool import MILVUS_SEARCH_TOOL  # Import the new tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"api_logs_{datetime.datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger("llm_api")

# Function to check if a model supports function calling
def model_supports_function_calling(model_name):
    # List of models known to support function calling
    # Update this list as OpenAI releases new models or changes capabilities
    function_calling_models = [
        model for model in [
            "gpt-4", "gpt-4-turbo", "gpt-4-vision-preview", "gpt-4-1106-preview", 
            "gpt-4-0613", "gpt-4-32k", "gpt-4-32k-0613", "gpt-4o", 
            "gpt-3.5-turbo", "gpt-3.5-turbo-1106", "gpt-3.5-turbo-0613",
            "o1-preview", "o1-mini", "o3-mini"
        ] if model in model_name
    ]
    return len(function_calling_models) > 0

# Initialize session state for message history and settings
if "messages" not in st.session_state:
    st.session_state.messages = []
if "api_provider" not in st.session_state:
    st.session_state.api_provider = "openai"
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = """You are a helpful AI assistant. You can help users search through conversation records using date ranges, party names, or conversation IDs."""
if "seen_tool_calls" not in st.session_state:
    st.session_state.seen_tool_calls = set()
if "conversation_completed" not in st.session_state:
    st.session_state.conversation_completed = False

# Update database configuration
MONGO_URI = config["mongo_uri"]
OPENAI_API_KEY = config["openai_api_key"]

# Connect to database
conn = MongoClient(MONGO_URI)

# Move configuration elements to sidebar
with st.sidebar:
    st.header("Configuration?")
    
    
    # System prompt configuration
    system_prompt = st.text_area(
        "System Prompt (defines assistant behavior)",
        key="system_prompt",
        height=100
    )
    
    if st.button("Reset System Prompt"):
        st.session_state.system_prompt = """You are a helpful AI assistant. You can help users search through conversation records using date ranges, party names, or conversation IDs."""
        st.rerun()

    client = OpenAI(api_key=OPENAI_API_KEY)
    if not OPENAI_API_KEY:
        st.error("OpenAI API key not found. Please set OPENAI_API_KEY in your .env file.")
        st.stop()
    
    # Fetch available models from OpenAI
    try:
        models = client.models.list()
        available_models = [
            model.id for model in models 
            if model.id.startswith(('gpt-3.5', 'gpt-4', 'o1', 'o3')) and 'instruct' not in model.id
        ]
        available_models.sort()
    except openai.OpenAIError as e:
        st.warning("Could not fetch models from OpenAI, using default options")
        available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]
        
    default_model = config["default_openai_model"]
    default_index = available_models.index(default_model) if default_model in available_models else 0

    model = st.selectbox("Select a model:", available_models, index=default_index)
    
    # Debug options
    show_debug = st.checkbox("Show debug messages", value=False)
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()
    
    # Initialize debug log container in session state if not exists
    if "debug_logs" not in st.session_state:
        st.session_state.debug_logs = []

    # Create a debug log area if debug is enabled
    if show_debug:
        with st.sidebar:
            st.header("Debug Logs")
            if st.button("Clear Debug Logs"):
                st.session_state.debug_logs = []
                st.rerun()
            with st.expander("View Logs", expanded=True):
                for log in st.session_state.debug_logs:
                    st.text(log)

# Helper function to log messages both to logger and UI if debug is enabled
def log_message(level, message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted_message = f"[{timestamp}] {level}: {message}"
    
    # Log to logger
    if level == "INFO":
        logger.info(message)
    elif level == "DEBUG":
        logger.debug(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "ERROR":
        logger.error(message)
    
    # Add to UI if debug is enabled
    if show_debug:
        st.session_state.debug_logs.append(formatted_message)
        # Keep only the last 100 messages to avoid memory issues
        if len(st.session_state.debug_logs) > 100:
            st.session_state.debug_logs = st.session_state.debug_logs[-100:]

# Main chat area
st.title("Chat Interface")

# Display chat messages
for message in st.session_state.messages:
    role = message["role"]
    # Skip function and tool messages in display
    if role in ["function", "tool"]:
        continue
    with st.chat_message(role):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to ask?"):
    # Reset conversation state for new query
    st.session_state.conversation_completed = False
    st.session_state.seen_tool_calls = set()
    
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
            
        # Add all user and assistant messages directly
        for msg in st.session_state.messages:
            # Skip function/tool messages as they'll be handled differently
            if msg["role"] not in ["function", "tool"]:
                api_messages.append(msg)

        # Check if the selected model supports function calling
        supports_function_calling = model_supports_function_calling(model)
        
        # Max number of iterations to prevent infinite loops
        max_iterations = 5
        current_iteration = 0
        
        # Process conversation with function calls in a loop
        while current_iteration < max_iterations:
            current_iteration += 1
            log_message("INFO", f"Starting conversation iteration {current_iteration}/{max_iterations}")
            
            # Call OpenAI API with current messages and tools
            log_message("INFO", f"OpenAI call with model {model}")
            if show_debug:
                log_message("DEBUG", f"Messages for API call: {json.dumps(api_messages, indent=2)}")
            
            # Only include tools if the model supports function calling
            if supports_function_calling:
                response = client.chat.completions.create(
                    model=model,
                    messages=api_messages,
                    tools=[PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID, MILVUS_SEARCH_TOOL]
                )
            else:
                log_message("WARNING", f"Model {model} may not support function calling. Using without tools.")
                response = client.chat.completions.create(
                    model=model,
                    messages=api_messages
                )
            
            log_message("INFO", f"OpenAI response received (finish_reason: {response.choices[0].finish_reason})")
            
            # Get assistant response and tool calls
            assistant_message = response.choices[0].message
            assistant_response = assistant_message.content
            tool_calls = assistant_message.tool_calls or [] if supports_function_calling else []
            
            # Add the assistant message to the conversation history with tool_calls if present
            assistant_api_message = {
                "role": "assistant",
                "content": assistant_response or ""
            }
            
            # Include tool_calls if present to ensure proper message structure
            if tool_calls:
                assistant_api_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    } for tool_call in tool_calls
                ]
            
            # Add the assistant message to the API messages array
            api_messages.append(assistant_api_message)
            
            # Add a simplified version to session state for display
            if assistant_response:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                
                # Display the assistant's response
                with st.chat_message("assistant"):
                    st.write(assistant_response)
            
            # If no tool calls, we're done with this conversation
            if not tool_calls:
                log_message("INFO", "No tool calls requested, conversation complete")
                break
                
            log_message("INFO", f"OpenAI requested {len(tool_calls)} tool calls")
            
            # Process each tool call
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                tool_call_id = tool_call.id
                
                # Generate a hash of this tool call to detect duplicates
                call_hash = hashlib.md5(f"{function_name}:{json.dumps(arguments, sort_keys=True)}".encode()).hexdigest()
                
                # Skip this tool call if we've seen it before
                if call_hash in st.session_state.seen_tool_calls:
                    log_message("WARNING", f"Skipping duplicate tool call: {function_name} with args {arguments}")
                    continue
                
                # Add this call to the seen set
                st.session_state.seen_tool_calls.add(call_hash)
                
                log_message("INFO", f"Executing tool: {function_name}")
                log_message("DEBUG", f"Tool arguments: {json.dumps(arguments, indent=2)}")
                
                # Execute the appropriate tool
                try:
                    if function_name == "find_by_party":
                        party = arguments["party"]
                        log_message("INFO", f"find_by_party tool call with party: {party}")
                        results = find_by_party(party, conn)
                    elif function_name == "find_by_date_range":
                        start_date = arguments["start_date"]
                        end_date = arguments["end_date"]
                        log_message("INFO", f"find_by_date_range tool call with range: {start_date} to {end_date}")
                        results = find_by_date_range(start_date, end_date, conn)
                    elif function_name == "get_conversation_by_id":
                        uuids = arguments["uuids"]
                        # Limit number of UUIDs to process
                        if isinstance(uuids, list) and len(uuids) > 20:
                            log_message("WARNING", f"Too many UUIDs requested: {len(uuids)}. Limiting to 20.")
                            uuids = uuids[:20]
                        results = get_conversation_by_id(uuids, conn)
                    elif function_name == "search_in_milvus":
                        search_text = arguments["search_text"]
                        log_message("INFO", f"search_in_milvus tool call with search_text: {search_text}")
                        results = search_in_milvus(search_text)
                    else:
                        error_msg = f"Unknown function: {function_name}"
                        log_message("ERROR", error_msg)
                        results = f"Error: {error_msg}"
                    
                    # Log results summary
                    if isinstance(results, list):
                        log_message("INFO", f"Tool {function_name} returned {len(results)} results")
                        if show_debug and len(results) > 0:
                            sample_size = min(3, len(results))
                            sample = results[:sample_size]
                            log_message("DEBUG", f"Sample of results: {sample}")
                    else:
                        log_message("INFO", f"Tool {function_name} execution completed")
                        if show_debug and results:
                            result_preview = str(results)[:200] + "..." if len(str(results)) > 200 else str(results)
                            log_message("DEBUG", f"Result preview: {result_preview}")
                    
                except Exception as e:
                    error_trace = traceback.format_exc()
                    log_message("ERROR", f"Error executing tool {function_name}: {str(e)}")
                    log_message("ERROR", f"Traceback: {error_trace}")
                    results = f"Error executing tool {function_name}: {str(e)}"
                
                # Add tool results to conversation with the correct format for OpenAI
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(results)
                }
                
                # Add to session state
                st.session_state.messages.append({
                    "role": "tool",  # Use 'tool' for session state too for consistency
                    "name": function_name,
                    "content": str(results)
                })
                
                # Add to API messages for next round
                api_messages.append(tool_message)
                
                if show_debug:
                    log_message("DEBUG", f"Tool {function_name} results: {str(results)[:500]}...")
            
            # If we've reached max iterations, inform the user
            if current_iteration >= max_iterations and tool_calls:
                warning_msg = "The assistant reached the maximum number of tool calls allowed. The response may be incomplete."
                st.warning(warning_msg)
                log_message("WARNING", warning_msg)
                break
        
        # Mark conversation as completed
        st.session_state.conversation_completed = True
        
        # Add a small delay to ensure UI updates before rerun
        time.sleep(0.5)
        
        # Force Streamlit to rerun the app to refresh the display
        st.rerun()
                
    except (requests.exceptions.RequestException, openai.OpenAIError) as e:
        error_trace = traceback.format_exc()
        log_message("ERROR", f"API Error: {str(e)}")
        log_message("ERROR", f"Traceback: {error_trace}")
        st.error(f"API Error: {str(e)}")
        st.info("Check your OpenAI API key and connection.")
    except Exception as e:
        error_trace = traceback.format_exc()
        log_message("ERROR", f"Unexpected error: {str(e)}")
        log_message("ERROR", f"Traceback: {error_trace}")
        st.error(f"Unexpected error: {str(e)}")
