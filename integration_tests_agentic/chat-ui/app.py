#  Copyright 2025 Dell Inc. or its subsidiaries. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""
Chat UI Application

A Streamlit-based chat interface for the Agentic Orchestrator.
"""

import streamlit as st
import requests
import json
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
import time
from datetime import datetime
from config import config
import logging
import random
import threading

# Import credential management modules
from credential_manager import CredentialDatabase, iDRACCredential
from spreadsheet_import import SpreadsheetImporter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - now using config.py values
ORCHESTRATOR_URL = config.ORCHESTRATOR_URL
CHAT_ENDPOINT = config.CHAT_ENDPOINT
CHAT_STREAM_ENDPOINT = config.CHAT_STREAM_ENDPOINT

class ChatClient:
    """Client for communicating with the orchestrator."""
    
    def __init__(self, base_url: str = ORCHESTRATOR_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def send_message(self, message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to the orchestrator."""
        try:
            payload = {
                "input": message,
                "conversation_id": conversation_id,
                "metadata": {}
            }
            
            response = self.session.post(
                f"{self.base_url}{CHAT_ENDPOINT}",
                json=payload,
                timeout=config.ORCHESTRATOR_TIMEOUT
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "success": False
                }
        
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {
                "error": str(e),
                "success": False
            }
    
    def stream_message(self, message: str, conversation_id: Optional[str] = None):
        """Stream a message response from the orchestrator."""
        try:
            payload = {
                "input": message,
                "conversation_id": conversation_id,
                "metadata": {}
            }
            
            response = self.session.post(
                f"{self.base_url}{CHAT_STREAM_ENDPOINT}",
                json=payload,
                stream=True,
                timeout=config.ORCHESTRATOR_TIMEOUT
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            # Parse Server-Sent Events
                            if line.startswith(b'data: '):
                                data = json.loads(line[6:].decode('utf-8'))
                                yield data
                        except json.JSONDecodeError:
                            continue
            else:
                yield {
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "success": False
                }
        
        except Exception as e:
            logger.error(f"Error streaming message: {e}")
            yield {
                "error": str(e),
                "success": False
            }
    
    def health_check(self) -> bool:
        """Check if the orchestrator is healthy."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

def initialize_session_state():
    """Initialize Streamlit session state."""
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    if 'conversation_id' not in st.session_state:
        st.session_state.conversation_id = f"chat_{int(time.time())}"

    if 'client' not in st.session_state:
        st.session_state.client = ChatClient()

    if 'thinking_messages' not in st.session_state:
        st.session_state.thinking_messages = True

    # Credential management
    if 'credential_db' not in st.session_state:
        # Get database path and master password from environment
        import os
        db_path = os.getenv("CREDENTIAL_DB_PATH", os.path.expanduser("~/.idrac_credentials.db"))
        master_password = os.getenv("CREDENTIAL_MASTER_PASSWORD")
        st.session_state.credential_db = CredentialDatabase(
            db_path=db_path,
            master_password=master_password
        )

    if 'selected_system' not in st.session_state:
        st.session_state.selected_system = None

    if 'show_add_credential_form' not in st.session_state:
        st.session_state.show_add_credential_form = False

    if 'show_import_form' not in st.session_state:
        st.session_state.show_import_form = False

def display_message(role: str, content: str, timestamp: Optional[str] = None, response_time: Optional[str] = None):
    """Display a chat message."""
    with st.chat_message(role):
        st.write(content)
        caption_parts = []
        if timestamp:
            caption_parts.append(f"📅 {timestamp}")
        if response_time:
            caption_parts.append(f"⏱️ {response_time}")
        if caption_parts:
            st.caption(" | ".join(caption_parts))


def credential_management_ui():
    """Render credential management UI in sidebar."""
    st.sidebar.title("🔐 Managed Systems")

    # Get list of configured systems
    systems = st.session_state.credential_db.list_credentials()

    # System selector
    if systems:
        system_options = ["<Select a system>"] + [f"{s['system_id']} ({s['idrac_ip']})" for s in systems]
        selected_idx = st.sidebar.selectbox(
            "Active System",
            range(len(system_options)),
            format_func=lambda i: system_options[i],
            key="system_selector"
        )

        if selected_idx > 0:
            # Extract system_id from selection
            selected_system_id = systems[selected_idx - 1]['system_id']
            st.session_state.selected_system = selected_system_id
            st.sidebar.success(f"✅ Connected to {selected_system_id}")
        else:
            st.session_state.selected_system = None
            st.sidebar.info("ℹ️ Select a system to connect")

    else:
        st.sidebar.info("ℹ️ No systems configured. Add one below.")
        st.session_state.selected_system = None

    st.sidebar.markdown("---")

    # Action buttons
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("➕ Add System", key="btn_add_system", use_container_width=True):
            st.session_state.show_add_credential_form = True
            st.session_state.show_import_form = False

    with col2:
        if st.button("📥 Import", key="btn_show_import", use_container_width=True):
            st.session_state.show_import_form = True
            st.session_state.show_add_credential_form = False

    # Add credential form
    if st.session_state.show_add_credential_form:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Add New System")

        with st.sidebar.form("add_credential_form"):
            system_id = st.text_input(
                "System ID *",
                placeholder="e.g., server-01",
                help="Unique identifier for this system"
            )
            idrac_ip = st.text_input(
                "Management IP/URL *",
                placeholder="https://192.168.1.100",
                help="Management endpoint URL (e.g., iDRAC, BMC, Redfish endpoint)"
            )
            username = st.text_input(
                "Username *",
                placeholder="root",
                help="Management interface username"
            )
            password = st.text_input(
                "Password *",
                type="password",
                help="Management interface password"
            )
            auth_token = st.text_input(
                "Auth Token (optional)",
                type="password",
                help="Authentication token (if using token-based auth)"
            )
            description = st.text_input(
                "Description",
                placeholder="Production Server 1",
                help="Optional description"
            )

            col1, col2 = st.columns(2)
            with col1:
                submit = st.form_submit_button("💾 Save", use_container_width=True)
            with col2:
                cancel = st.form_submit_button("❌ Cancel", use_container_width=True)

            if submit:
                # Validate required fields
                if not all([system_id, idrac_ip, username, password]):
                    st.error("Please fill in all required fields (*)")
                else:
                    # Add credential to database
                    credential = iDRACCredential(
                        system_id=system_id.strip(),
                        idrac_ip=idrac_ip.strip(),
                        username=username.strip(),
                        password=password.strip(),
                        auth_token=auth_token.strip() if auth_token else None,
                        description=description.strip() if description else None
                    )

                    if st.session_state.credential_db.add_credential(credential):
                        st.success(f"✅ System '{system_id}' added successfully!")
                        st.info("💡 Credentials will be validated when you use the system")
                        st.session_state.show_add_credential_form = False
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error("Failed to save credential")

            if cancel:
                st.session_state.show_add_credential_form = False
                st.rerun()

    # Import form
    if st.session_state.show_import_form:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Import Systems")

        # Download template buttons
        st.sidebar.write("**Download Template:**")
        col1, col2 = st.sidebar.columns(2)

        with col1:
            csv_template = SpreadsheetImporter.create_template_csv()
            st.download_button(
                label="📄 CSV",
                data=csv_template,
                file_name="managed_systems_template.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col2:
            excel_template = SpreadsheetImporter.create_template_excel()
            st.download_button(
                label="📊 Excel",
                data=excel_template,
                file_name="managed_systems_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        st.sidebar.markdown("---")

        # File upload
        uploaded_file = st.sidebar.file_uploader(
            "Upload Credentials File",
            type=["csv", "xlsx"],
            help="Upload CSV or Excel file with credentials"
        )

        if uploaded_file is not None:
            file_content = uploaded_file.read()
            file_type = uploaded_file.name.split('.')[-1].lower()

            col1, col2 = st.sidebar.columns(2)

            with col1:
                if st.button("📥 Import", key="btn_execute_import", use_container_width=True):
                    with st.spinner("Importing credentials..."):
                        # Parse file
                        if file_type == "csv":
                            credentials, errors = SpreadsheetImporter.import_from_csv(file_content)
                        else:  # xlsx
                            credentials, errors = SpreadsheetImporter.import_from_excel(file_content)

                        if errors:
                            st.error("Import failed:")
                            for error in errors:
                                st.error(f"- {error}")
                        else:
                            # Import to database
                            stats = st.session_state.credential_db.import_from_list(credentials)

                            if stats["success"] > 0:
                                st.success(f"✅ Imported {stats['success']} systems successfully!")

                            if stats["failed"] > 0:
                                st.warning(f"⚠️ {stats['failed']} systems failed to import")
                                for error in stats["errors"]:
                                    st.error(f"- {error}")

                            if stats["success"] > 0:
                                st.session_state.show_import_form = False
                                time.sleep(1)
                                st.rerun()

            with col2:
                if st.button("❌ Cancel", key="btn_cancel_import", use_container_width=True):
                    st.session_state.show_import_form = False
                    st.rerun()

    # Manage existing systems
    if systems and not st.session_state.show_add_credential_form and not st.session_state.show_import_form:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Configured Systems")

        for system in systems:
            with st.sidebar.expander(f"🖥️ {system['system_id']}"):
                st.write(f"**IP:** {system['idrac_ip']}")
                if system.get('description'):
                    st.write(f"**Description:** {system['description']}")
                st.caption(f"Added: {system.get('created_at', 'Unknown')[:10]}")

                if st.button("🗑️ Delete", key=f"delete_{system['system_id']}", use_container_width=True):
                    if st.session_state.credential_db.delete_credential(system['system_id']):
                        st.success(f"Deleted {system['system_id']}")
                        time.sleep(1)
                        st.rerun()

# Agent step display function removed - now using thinking icon instead


def display_dynamic_thinking_message(placeholder):
    """Display dynamic thinking/generating message."""
    messages = [
        "🤔 Thinking...",
        "🧠 Generating response...",
        "💭 Processing your request...",
        "🔍 Analyzing...",
        "⚡ Working on it...",
        "🎯 Focusing...",
        "🚀 Computing...",
        "🎨 Crafting response...",
        "📝 Writing...",
        "🔧 Processing...",
        "💡 Thinking deeply...",
        "🌟 Generating insights...",
        "🎪 Working magic...",
        "🔮 Consulting the AI oracle...",
        "🎭 Preparing response..."
    ]
    
    # Create a stop event for the thread
    stop_event = threading.Event()
    
    def update_message():
        while not stop_event.is_set():
            message = random.choice(messages)
            placeholder.write(message)
            time.sleep(random.uniform(0.5, 1.5))  # Random interval between 0.5-1.5 seconds
    
    # Start the thread
    thread = threading.Thread(target=update_message)
    thread.daemon = True
    thread.start()
    
    return stop_event


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title="  |  Agentic Admin for PowerEdge",
        page_icon="./dell_logo.jpg",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS for chat message avatars
    st.markdown("""
    <style>
    /* Alternative selectors if the above don't work */
    div[data-testid="chatAvatarIcon-user"] {
        background-color: #1f77b4 !important;
    }
    
    div[data-testid="chatAvatarIcon-assistant"] {
        background-color: #2ca02c !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    initialize_session_state()

    # Credential Management UI (in sidebar)
    credential_management_ui()

    # Sidebar
    with st.sidebar:
        st.markdown("---")
        st.title("Admin Settings")
        
        # Health check
        if st.session_state.client.health_check():
            st.success("✅ Orchestrator Connected")
        else:
            st.error("❌ Orchestrator Disconnected")
            st.write(f"Trying to connect to: {ORCHESTRATOR_URL}")
        
        # Settings
        st.session_state.thinking_messages = st.checkbox(
            "Enable Thinking Messages", 
            value=st.session_state.thinking_messages,
            help="Show dynamic thinking messages while processing"
        )
        
        # Conversation info
        st.write("**Conversation ID:**")
        st.code(st.session_state.conversation_id)
        
        # Clear chat button
        if st.button("Clear Chat", key="btn_clear_chat"):
            st.session_state.messages = []
            st.session_state.conversation_id = f"chat_{int(time.time())}"
            st.rerun()

        # Statistics
        st.write("**Chat Statistics:**")
        st.write(f"Messages: {len(st.session_state.messages)}")

        # Connection settings
        with st.expander("Connection Settings"):
            new_url = st.text_input("Orchestrator URL", value=ORCHESTRATOR_URL, key="input_orchestrator_url")
            if st.button("Update URL", key="btn_update_url"):
                st.session_state.client = ChatClient(new_url)
                st.success("URL updated!")
    
    # Main chat interface
    # Custom image display
    image_path = "./dell_logo_blue.png"  # Path to your custom image
    try:
        col1, col2 = st.columns([1,4])
        with col1:
            st.image(image_path, width=200)
        with col2:
            st.write('| Agentic Admin for PowerEdge')
    except:
        # Fallback to emoji if image not found
        st.title("Agentic Admin for PowerEdge")
    
    st.caption("Administrative interface for PowerEdge systems with intelligent agent assistance.")
    st.title('')
    
    # Display chat history
    for message in st.session_state.messages:
        display_message(
            message["role"], 
            message["content"], 
            message.get("timestamp"),
            message.get("response_time")
        )
        
        # Show a brief thinking indicator for processing messages if enabled
        if message["role"] == "assistant" and st.session_state.thinking_messages and message.get("processing", False):
            with st.chat_message("assistant"):
                st.write("🤔 Processing your request...")
        elif message["role"] == "assistant" and message.get("processing_complete"):
            # Show completion indicator briefly for processed messages
            with st.chat_message("assistant"):
                st.success("✅ Response generated")
    
    # Chat input
    if prompt := st.chat_input("Ask the orchestrator anything..."):
        # Add user message to chat history
        user_message = {
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        st.session_state.messages.append(user_message)
        
        # Display user message
        display_message(user_message["role"], user_message["content"], user_message["timestamp"])
        
        # Get response from orchestrator
        with st.chat_message("assistant"):
            # Show thinking message with processing indicator
            start_time = time.time()
            thinking_messages = [
                "🤔 Thinking", "🧠 Generating response", "💭 Processing request",
                "🔍 Analyzing", "⚡ Working on it", "🎯 Focusing",
                "🚀 Computing", "🔧 Processing"
            ]
            
            # Use Streamlit's spinner for better UX
            selected_msg = random.choice(thinking_messages)
            with st.spinner(f"{selected_msg}..."):
                try:
                    # Make the API call
                    result = st.session_state.client.send_message(prompt, st.session_state.conversation_id)
                except Exception as e:
                    logger.error(f"Request error: {e}")
                    result = {"success": False, "error": str(e)}
            
            # Process the result after spinner is done
            if result.get('success', True) and not result.get('error'):
                response_content = result.get('output', 'No response received')
                
                # Try to get more detailed content from steps if available
                steps = result.get('steps', [])
                if steps:
                    # Look for the final tool output in the last few steps
                    detailed_content = None
                    for step in reversed(steps[-15:]):  # Check last 15 steps for better coverage
                        step_message = step.get('message', '')
                        if ('Tool completed with output:' in step_message or 
                            'Final answer:' in step_message):
                            # Extract the detailed content
                            if 'Tool completed with output:' in step_message:
                                detailed_content = step_message.replace('Tool completed with output:', '').strip()
                                # Now that we removed truncation, we should get full content
                                if len(detailed_content) > 50:  # Only use if substantial content
                                    break
                            elif 'Final answer:' in step_message:
                                detailed_content = step_message.replace('Final answer:', '').strip()
                                break
                    
                    # Use detailed content if it's significantly longer and more informative
                    # Or if the current response references missing 'above' content
                    if (detailed_content and 
                        (len(detailed_content) > len(response_content) * 1.2 or
                         'above' in response_content.lower() or 
                         len(response_content) < 100)):
                        response_content = detailed_content
                
                # Calculate total response time
                total_time = int(time.time() - start_time)
                minutes = total_time // 60
                seconds = total_time % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                
                # Show the actual response
                st.write(response_content)
                
                # Show response time as a small indicator
                st.caption(f"⏱️ Response time: {time_str}")
                
                # Add assistant response to chat history with response time
                assistant_message = {
                    "role": "assistant",
                    "content": response_content,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "response_time": time_str
                }
                st.session_state.messages.append(assistant_message)
            
            else:
                # Show error
                st.error(f"❌ Error: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()