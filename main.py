from party_tool import PARTY_TOOL, find_by_party
from date_range_tool import DATE_RANGE_TOOL, find_by_date_range
from get_conversation_by_id_tool import GET_CONVERSATION_BY_ID, get_conversation_by_id
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
    
    # API provider selection
    api_provider = st.radio(
        "Select API Provider",
        ["openai","ollama"],
        key="api_provider"
    )
    
    # System prompt configuration
    system_prompt = st.text_area(
        "System Prompt (defines assistant behavior)",
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
            value=config["ollama_host"],
            key="ollama_host"
        )
        
        # Fetch available models from Ollama
        try:
            models_response = requests.get(f"{ollama_host}/api/tags")
            if models_response.status_code == 200:
                available_models = [model["name"] for model in models_response.json()["models"]]
                print(available_models)
            else:
                available_models = ["llama3.1", "llama3.1:8b", "llama3.1:70b"]
                st.warning("Could not fetch models from Ollama, using default options")
        except requests.exceptions.RequestException:
            available_models = ["llama3.1", "llama3.1:8b", "llama3.1:70b"]
            st.warning("Could not connect to Ollama, using default options")

        default_model = config["default_model"]
        print(config)
        print(default_model)
        print(available_models)
        print(available_models.index(default_model))
        try:
            default_index = available_models.index(default_model)
        except ValueError:
            default_index = 0
            st.warning(f"Default model {default_model} not found in available models")

    else:  # OpenAI configuration
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
            print("Processed API Messages:", api_messages)

        # Initialize a variable to store the final assistant response
        assistant_response = None
        
        # Safety counter to prevent infinite tool calling loops
        tool_call_count = 0
        max_tool_calls = 10  # Increased from 5 to 10 for complex queries
        
        # Main tool calling loop
        while tool_call_count < max_tool_calls:
            tool_call_count += 1
            
            try:
                logger.info(f"API call #{tool_call_count} to {api_provider} with model {model}")
                if show_debug:
                    logger.debug(f"Request messages: {json.dumps(api_messages, indent=2)}")
                
                if api_provider == "ollama":
                    request_data = {
                        "model": model,
                        "messages": api_messages,
                        "stream": False,
                        "tools": [PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                    }
                    logger.info(f"Sending request to Ollama: {ollama_host}/api/chat")
                    
                    response = requests.post(
                        f"{ollama_host}/api/chat",
                        json=request_data
                    )
                    
                    if response.status_code == 200:
                        response_json = response.json()
                        logger.info(f"Ollama response received (status: {response.status_code})")
                        logger.debug(f"Ollama response: {json.dumps(response_json, indent=2)}")
                        
                        assistant_response = response_json["message"]["content"]
                        tool_calls = response_json["message"].get("tool_calls", [])
                        
                        if tool_calls:
                            logger.info(f"Ollama requested {len(tool_calls)} tool calls")
                    else:
                        logger.error(f"Ollama error: {response.status_code} - {response.text}")
                        st.error(f"Error: {response.status_code}")
                        st.stop()

                else:  # OpenAI
                    if model.startswith(('o1', 'o3')):
                        # For Claude models (o1, o3), skip tools and system messages
                        filtered_messages = [msg for msg in api_messages if msg["role"] not in ["function", "tool", "system"]]
                        
                        # If we have a system message, prepend it to the first user message instead
                        system_content = None
                        for msg in api_messages:
                            if msg["role"] == "system":
                                system_content = msg["content"]
                                break
                        
                        # Prepend system message to first user message if found
                        if system_content and filtered_messages:
                            for i, msg in enumerate(filtered_messages):
                                if msg["role"] == "user":
                                    filtered_messages[i]["content"] = f"{system_content}\n\n{msg['content']}"
                                    break
                        
                        logger.info(f"OpenAI call with Claude model {model} (without tools)")
                        logger.debug(f"Filtered messages for Claude: {json.dumps(filtered_messages, indent=2)}")
                        
                        response = client.chat.completions.create(
                            model=model,
                            messages=filtered_messages,
                            max_tokens=4000  # Ensure we get a complete response
                        )
                    else:
                        logger.info(f"OpenAI call with model {model} (with tools)")
                        
                        response = client.chat.completions.create(
                            model=model,
                            messages=api_messages,
                            tools=[PARTY_TOOL, DATE_RANGE_TOOL, GET_CONVERSATION_BY_ID]
                        )
                    
                    logger.info(f"OpenAI response received (finish_reason: {response.choices[0].finish_reason})")
                    
                    # Log response details (safely handling potentially large responses)
                    if show_debug:
                        try:
                            logger.debug(f"OpenAI response: {response}")
                        except Exception as e:
                            logger.debug(f"OpenAI response too large to log directly: {str(e)}")
                        
                    assistant_response = response.choices[0].message.content
                    tool_calls = response.choices[0].message.tool_calls or []
                    
                    if tool_calls:
                        logger.info(f"OpenAI requested {len(tool_calls)} tool calls")

                # Add the assistant response to messages (without tools)
                if assistant_response:
                    # Add the assistant's message to the session history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": assistant_response
                    })
                    
                    # Also add to API messages for the next round
                    api_messages.append({
                        "role": "assistant",
                        "content": assistant_response
                    })
                
                # If there are no tool calls, break the loop
                if not tool_calls:
                    break
                
                # Process tool calls with added loop detection
                if tool_calls:
                    if show_debug:
                        logger.debug(f"Tool calls in iteration {tool_call_count}: {tool_calls}")
                        
                    for tool_call in tool_calls:
                        function_name = (tool_call.function.name 
                                       if api_provider == "openai" 
                                       else tool_call["function"]["name"])
                        
                        arguments = (json.loads(tool_call.function.arguments) 
                                   if api_provider == "openai" 
                                   else tool_call["function"]["arguments"])

                        # Generate a hash of this tool call to detect duplicates
                        call_hash = hashlib.md5(f"{function_name}:{json.dumps(arguments, sort_keys=True)}".encode()).hexdigest()
                        
                        # Skip this tool call if we've seen it before
                        if call_hash in st.session_state.seen_tool_calls:
                            logger.warning(f"Skipping duplicate tool call: {function_name} with args {arguments}")
                            continue
                        
                        # Add this call to the seen set
                        st.session_state.seen_tool_calls.add(call_hash)

                        logger.info(f"Executing tool: {function_name}")
                        logger.debug(f"Tool arguments: {json.dumps(arguments, indent=2)}")

                        # Execute the appropriate tool
                        try:
                            if function_name == "find_by_party":
                                party = arguments["party"]
                                logger.info(f"find_by_party tool call with party: {party}")
                                results = find_by_party(party, conn)
                            elif function_name == "find_by_date_range":
                                start_date = arguments["start_date"]
                                end_date = arguments["end_date"]
                                logger.info(f"find_by_date_range tool call with range: {start_date} to {end_date}")
                                results = find_by_date_range(start_date, end_date, conn)
                            elif function_name == "get_conversation_by_id":
                                uuids = arguments["uuids"]
                                # Limit number of UUIDs to process
                                if isinstance(uuids, list) and len(uuids) > 20:
                                    logger.warning(f"Too many UUIDs requested: {len(uuids)}. Limiting to 20.")
                                    uuids = uuids[:20]
                                results = get_conversation_by_id(uuids, conn)
                            else:
                                error_msg = f"Unknown function: {function_name}"
                                logger.error(error_msg)
                                results = f"Error: {error_msg}"
                            
                            # Log results summary (not full results which might be large)
                            if isinstance(results, list):
                                logger.info(f"Tool {function_name} returned {len(results)} results")
                                if show_debug and len(results) > 0:
                                    # Log a sample instead of the full result
                                    sample_size = min(3, len(results))
                                    sample = results[:sample_size]
                                    logger.debug(f"Sample of results: {sample}")
                            else:
                                logger.info(f"Tool {function_name} execution completed")
                            
                            if show_debug and results:
                                try:
                                    results_sample = str(results)[:500] + "..." if len(str(results)) > 500 else str(results)
                                    logger.debug(f"Tool {function_name} results sample: {results_sample}")
                                except Exception as e:
                                    logger.debug(f"Could not log results sample: {str(e)}")
                            
                        except Exception as e:
                            error_trace = traceback.format_exc()
                            logger.error(f"Error executing tool {function_name}: {str(e)}")
                            logger.error(f"Traceback: {error_trace}")
                            results = f"Error executing tool {function_name}: {str(e)}"
                        
                        # Add tool results to message history with the correct format
                        if api_provider == "ollama":
                            tool_message = {
                                "role": "tool",
                                "content": str(results),
                            }
                        else:  # OpenAI
                            tool_message = {
                                "role": "function",
                                "name": function_name,
                                "content": str(results),
                            }
                        
                        st.session_state.messages.append(tool_message)
                        api_messages.append(tool_message)
                        
                        if show_debug:
                            print(f"Tool {function_name} results: {results}")

                # Display final assistant response if we have one
                if assistant_response:
                    with st.chat_message("assistant"):
                        st.write(assistant_response)
                    
                    # If there are no more tool calls or we've reached max iterations, we're done
                    if not tool_calls or tool_call_count >= max_tool_calls:
                        # Add a flag to session state to indicate we've processed the final response
                        st.session_state.conversation_completed = True
                        
                        # Add a small delay to ensure UI updates before rerun
                        time.sleep(0.5)
                        
                        # Force Streamlit to rerun the app and display the full conversation
                        st.rerun()
                
                # If we hit the max tool calls limit, inform the user
                if tool_call_count >= max_tool_calls and tool_calls:
                    warning_msg = "The assistant reached the maximum number of tool calls allowed. The response may be incomplete."
                    st.warning(warning_msg)
                    if show_debug:
                        print(warning_msg)
            
            except Exception as e:
                error_trace = traceback.format_exc()
                logger.error(f"Error during API call #{tool_call_count}: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                raise

    except (requests.exceptions.RequestException, openai.OpenAIError) as e:
        error_trace = traceback.format_exc()
        logger.error(f"API Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        st.error(f"API Error: {str(e)}")
        if api_provider == "ollama":
            st.info("Make sure Ollama is running and accessible.")
        else:
            st.info("Check your OpenAI API key and connection.")
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        st.error(f"Unexpected error: {str(e)}")
