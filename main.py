
import streamlit as st
import requests
import json

st.title("Chat with Ollama")

# Initialize session state for message history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Fetch available models from Ollama
try:
    models_response = requests.get("http://localhost:11434/api/tags")
    if models_response.status_code == 200:
        available_models = [model["name"] for model in models_response.json()["models"]]
    else:
        available_models = ["llama2", "mistral", "codellama"]  # fallback options
        st.warning("Could not fetch models from Ollama, using default options")
except requests.exceptions.RequestException:
    available_models = ["llama2", "mistral", "codellama"]  # fallback options
    st.warning("Could not connect to Ollama, using default options")

# Chat model selection
model = st.selectbox("Select a model:", available_models)

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

    # Prepare the API request
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        )
        
        if response.status_code == 200:
            assistant_response = response.json()["response"]
            
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            
            # Display assistant response
            with st.chat_message("assistant"):
                st.write(assistant_response)
        else:
            st.error(f"Error: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to Ollama API: {str(e)}")
        st.info("Make sure Ollama is running and accessible.")

# Add a clear button
if st.button("Clear Chat"):
    st.session_state.messages = []
    st.rerun()
