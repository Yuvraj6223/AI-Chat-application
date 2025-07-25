import streamlit as st
import requests
import json
import os
import mysql.connector
from mysql.connector import Error


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "") 
DB_NAME = os.getenv("DB_NAME", "gemini_chatbot_db")


def get_db_connection():
    """Establishes and returns a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if conn.is_connected():
            return conn
    except Error as e:
        st.error(f"Error connecting to MySQL database: {e}")
        return None

def init_db():
    """Initializes the database by creating the necessary table if it doesn't exist."""
    conn = None
    try:
        
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cursor.close()
        conn.close()

        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                chat_id VARCHAR(255) NOT NULL,
                messages JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, chat_id)
            )
            """
            cursor.execute(create_table_query)
            conn.commit()
            cursor.close()
    except Error as e:
        st.error(f"Error initializing database: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

def save_chat_to_db(user_id, chat_id, messages):
    """Saves or updates a chat session in the database."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        messages_json = json.dumps(messages) 

        
        query = """
        INSERT INTO chat_sessions (user_id, chat_id, messages)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            messages = VALUES(messages),
            created_at = CURRENT_TIMESTAMP
        """
        cursor.execute(query, (user_id, chat_id, messages_json))
        conn.commit()
    except Error as e:
        st.error(f"Error saving chat to database: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def load_chats_from_db(user_id):
    """Loads all chat sessions for a given user from the database."""
    conn = get_db_connection()
    if not conn:
        return {}

    chat_sessions = {}
    try:
        cursor = conn.cursor(dictionary=True) 
        query = "SELECT chat_id, messages FROM chat_sessions WHERE user_id = %s ORDER BY created_at DESC"
        cursor.execute(query, (user_id,))
        for row in cursor:
            chat_id = row["chat_id"]
            
            messages = json.loads(row["messages"]) if row["messages"] else []
            chat_sessions[chat_id] = messages
    except Error as e:
        st.error(f"Error loading chats from database: {e}")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    return chat_sessions


st.set_page_config(page_title="Gemini Chatbot", page_icon="💬", layout="wide")
st.title("💬 Gemini Chatbot")


if "messages" not in st.session_state:
    st.session_state.messages = [] 
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = {} 
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None 
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False


def get_gemini_response(prompt_text, chat_history):
    """
    Sends a prompt to the Gemini API and returns the generated text.
    Includes chat history for multi-turn conversations.
    """
    if not GEMINI_API_KEY:
        st.error("Gemini API Key is not set. Please set the GEMINI_API_KEY environment variable or provide it in the script.")
        return "Error: API key missing."

    headers = {
        "Content-Type": "application/json",
    }
    params = {
        "key": GEMINI_API_KEY
    }

    
    
    payload_contents = []
    for msg in chat_history:
        payload_contents.append({"role": msg["role"], "parts": [{"text": msg["content"]}]})
    payload_contents.append({"role": "user", "parts": [{"text": prompt_text}]})

    payload = {
        "contents": payload_contents
    }

    try:
        
        response = requests.post(GEMINI_API_URL, headers=headers, params=params, data=json.dumps(payload))
        response.raise_for_status() 
        result = response.json()

        
        if result and result.get("candidates"):
            return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return "No response from Gemini API."

    except requests.exceptions.RequestException as e:
        st.error(f"Error communicating with Gemini API: {e}")
        return f"Error: {e}"
    except KeyError:
        st.error("Unexpected response format from Gemini API.")
        st.json(result) 
        return "Error: Unexpected API response."


with st.sidebar:
    st.header("User Login")
    username_input = st.text_input("Enter your username", key="username_input")

    if st.button("Login / Select User", use_container_width=True):
        if username_input:
            st.session_state.user_id = username_input
            st.session_state.is_logged_in = True
            init_db() 
            st.session_state.chat_sessions = load_chats_from_db(st.session_state.user_id)

            
            if not st.session_state.chat_sessions:
                default_chat_id = "default_chat"
                st.session_state.chat_sessions[default_chat_id] = []
                save_chat_to_db(st.session_state.user_id, default_chat_id, [])
                st.session_state.current_chat_id = default_chat_id
            else:
                
                if 'default_chat' in st.session_state.chat_sessions:
                    st.session_state.current_chat_id = 'default_chat'
                else:
                    st.session_state.current_chat_id = list(st.session_state.chat_sessions.keys())[0]

            st.session_state.messages = st.session_state.chat_sessions[st.session_state.current_chat_id]
            st.rerun()
        else:
            st.warning("Please enter a username to login.")

    if st.session_state.is_logged_in:
        st.markdown(f"---")
        st.subheader(f"Welcome, {st.session_state.user_id}!")
        st.header("Chat Sessions")

        
        if st.button("➕ New Chat", use_container_width=True):
            new_chat_id = f"chat_{len(st.session_state.chat_sessions) + 1}"
            st.session_state.chat_sessions[new_chat_id] = []
            save_chat_to_db(st.session_state.user_id, new_chat_id, []) 
            st.session_state.current_chat_id = new_chat_id
            st.session_state.messages = [] 
            st.rerun() 

        st.markdown("---")
        st.subheader("Your Saved Chats")

        
        if st.session_state.chat_sessions:
            chat_ids = list(st.session_state.chat_sessions.keys())
            
            if 'default_chat' in chat_ids:
                chat_ids.remove('default_chat')
                chat_ids.insert(0, 'default_chat')

            for chat_id in chat_ids:
                display_name = chat_id.replace("_", " ").title() 
                if st.button(display_name, key=f"load_chat_{chat_id}", use_container_width=True):
                    st.session_state.current_chat_id = chat_id
                    st.session_state.messages = st.session_state.chat_sessions[chat_id]
                    st.rerun() 
        else:
            st.markdown("No saved chats yet. Start a new one!")
    else:
        st.info("Please log in with a username to start chatting.")



if st.session_state.is_logged_in and st.session_state.current_chat_id:
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    
    if prompt := st.chat_input("What's on your mind?", key="chat_input_main"):
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)

        
        with st.spinner("Thinking..."):
            gemini_response = get_gemini_response(prompt, st.session_state.messages)

        
        st.session_state.messages.append({"role": "assistant", "content": gemini_response})
        
        with st.chat_message("assistant"):
            st.markdown(gemini_response)

        
        st.session_state.chat_sessions[st.session_state.current_chat_id] = st.session_state.messages
        
        save_chat_to_db(st.session_state.user_id, st.session_state.current_chat_id, st.session_state.messages)
elif not st.session_state.is_logged_in:
    st.info("Please log in using the sidebar to start chatting.")
else:
    st.info("Select a chat from the sidebar or start a new one.")

