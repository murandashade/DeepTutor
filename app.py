"""DeepTutor - An AI-powered tutoring application.

This is the main entry point for the DeepTutor application,
built as a fork of HKUDS/DeepTutor with enhancements.
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import streamlit as st

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="DeepTutor",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "uploaded_file" not in st.session_state:
        st.session_state.uploaded_file = None
    if "document_processed" not in st.session_state:
        st.session_state.document_processed = False
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []


def render_sidebar():
    """Render the application sidebar with configuration options."""
    with st.sidebar:
        st.title("📚 DeepTutor")
        st.markdown("---")

        st.subheader("Upload Document")
        uploaded_file = st.file_uploader(
            "Upload a PDF to start learning",
            type=["pdf"],
            help="Upload a PDF document to interact with using AI.",
        )

        if uploaded_file is not None:
            st.session_state.uploaded_file = uploaded_file
            st.success(f"✅ Loaded: {uploaded_file.name}")

        st.markdown("---")
        st.subheader("Settings")

        # Model selection - defaulting to gpt-4o since I find it gives
        # noticeably better explanations for technical papers
        model_options = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        selected_model = st.selectbox(
            "Select LLM Model",
            options=model_options,
            index=0,
            help="Choose the language model for tutoring.",
        )
        st.session_state["selected_model"] = selected_model

        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_history = []
            st.rerun()

        st.markdown("---")
        st.caption("DeepTutor v0.1.0 | Fork of HKUDS/DeepTutor")


def render_chat_interface():
    """Render the main chat interface for interacting with documents."""
    st.title("🎓 DeepTutor")
    st.markdown("*Your AI-powered document tutor*")

    if st.session_state.uploaded_file is None:
        st.info(
            "👈 Please upload a PDF document from the sidebar to get started."
        )
        st.markdown(
            """
            ### How to use DeepTutor:
            1. **Upload** a PDF document using the sidebar
            2. **Ask questions** about the document content
            3. **Learn** with AI-powered explanations and tutoring
            """
  