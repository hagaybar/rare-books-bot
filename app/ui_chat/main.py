"""Conversational Chat UI for Rare Books Discovery.

A simple Streamlit chat interface that connects to the FastAPI backend.

Run with: poetry run streamlit run app/ui_chat/main.py
"""

import sys
import pathlib

# Ensure the root directory is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import streamlit as st
import requests
from typing import Optional

from app.ui_chat.config import generate_primo_url

# Configuration
API_BASE_URL = "http://localhost:8000"

# Page config
st.set_page_config(
    page_title="Rare Books Chat",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "api_available" not in st.session_state:
        st.session_state.api_available = check_api_health()


def check_api_health() -> bool:
    """Check if the API is available."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def send_message(user_message: str) -> Optional[dict]:
    """Send a message to the chat API.

    Args:
        user_message: The user's message

    Returns:
        API response dict or None on error
    """
    try:
        payload = {"message": user_message}
        if st.session_state.session_id:
            payload["session_id"] = st.session_state.session_id

        response = requests.post(
            f"{API_BASE_URL}/chat",
            json=payload,
            timeout=60,  # Longer timeout for LLM processing
        )

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API error: {response.status_code} - {response.text}")
            return None

    except requests.RequestException as e:
        st.error(f"Connection error: {e}")
        return None


def format_assistant_message(response_data: dict) -> str:
    """Format the assistant's response for display.

    Args:
        response_data: The API response

    Returns:
        Formatted message string
    """
    if not response_data.get("success"):
        return f"Error: {response_data.get('error', 'Unknown error')}"

    chat_response = response_data.get("response", {})
    message = chat_response.get("message", "No response")

    # Add clarification if needed
    clarification = chat_response.get("clarification_needed")
    if clarification:
        message += f"\n\n💡 **Suggestion:** {clarification}"

    return message


def format_date_display(date_start: int | None, date_end: int | None) -> str | None:
    """Format date range for display with smart single-year handling.

    Args:
        date_start: Start year
        date_end: End year

    Returns:
        Formatted date string or None
    """
    if date_start is None and date_end is None:
        return None
    if date_start is not None and date_end is not None:
        if date_start == date_end:
            return str(date_start)
        else:
            return f"{date_start}-{date_end}"
    if date_start is not None:
        return f"{date_start}-?"
    return f"?-{date_end}"


def format_place_display(place_norm: str | None, place_raw: str | None) -> str | None:
    """Format place for display showing canonical + raw form.

    Args:
        place_norm: Canonical place name
        place_raw: Raw bibliographic place

    Returns:
        Formatted place string or None
    """
    if place_norm and place_raw:
        raw_stripped = place_raw.strip()
        norm_title = place_norm.title()
        if raw_stripped.lower() != norm_title.lower():
            return f"{norm_title} ({raw_stripped})"
        return norm_title
    elif place_norm:
        return place_norm.title()
    elif place_raw:
        return place_raw.strip()
    return None


def render_candidate_details(response_data: dict):
    """Render candidate set details in an expander.

    Shows standard bibliographic fields for each result:
    - Title (clickable Primo link)
    - Author
    - Date (smart single year vs range display)
    - Place (canonical + raw form)
    - Publisher
    - Subjects (first 3)
    - Description (from MARC 500/520 notes)

    Args:
        response_data: The API response containing candidate_set
    """
    chat_response = response_data.get("response", {})
    candidate_set = chat_response.get("candidate_set")

    if not candidate_set:
        return

    candidates = candidate_set.get("candidates", [])
    if not candidates:
        return

    with st.expander(f"View all {len(candidates)} matching records", expanded=False):
        for i, candidate in enumerate(candidates[:50], 1):  # Show up to 50
            record_id = candidate.get("record_id", "Unknown")
            title = candidate.get("title")
            author = candidate.get("author")
            date_start = candidate.get("date_start")
            date_end = candidate.get("date_end")
            place_norm = candidate.get("place_norm")
            place_raw = candidate.get("place_raw")
            publisher = candidate.get("publisher")
            subjects = candidate.get("subjects", [])
            description = candidate.get("description")
            evidence = candidate.get("evidence", [])

            # Generate Primo URL for the record
            primo_url = generate_primo_url(record_id)

            # Title line (clickable link)
            display_title = title if title else f"[Record {record_id}]"
            st.markdown(f"**{i}.** [{display_title}]({primo_url})")

            # Author line (italicized)
            if author:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;*{author}*")

            # Publication info: Place, Publisher, Date
            pub_parts = []
            place_display = format_place_display(place_norm, place_raw)
            if place_display:
                pub_parts.append(place_display)
            if publisher:
                pub_parts.append(publisher)
            date_display = format_date_display(date_start, date_end)
            if date_display:
                pub_parts.append(date_display)

            if pub_parts:
                pub_line = " | ".join(pub_parts)
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{pub_line}")

            # Subjects (first 3)
            if subjects:
                subjects_str = ", ".join(subjects[:3])
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**Subjects:** {subjects_str}")

            # Description (truncated)
            if description:
                # Escape potential markdown in description
                desc_clean = description.replace("`", "'")
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;> {desc_clean}")

            # Evidence from query filters (collapsed by default in details)
            if evidence:
                with st.container():
                    field_labels = {
                        "subject_value": "Subject",
                        "title_value": "Title",
                        "publisher_norm": "Publisher",
                        "place_norm": "Place",
                        "date_range": "Date",
                        "date_start": "Date",
                        "language_code": "Language",
                        "agent_norm": "Author/Agent",
                        "agent_value": "Author/Agent",
                        "role_norm": "Role",
                        "country_name": "Country",
                    }
                    evidence_parts = []
                    for ev in evidence[:3]:
                        field = ev.get("field", "")
                        value = ev.get("value")
                        if value is None or value == "" or value == "None":
                            continue
                        friendly_field = field_labels.get(field, field.replace("_", " ").title())
                        evidence_parts.append(f"{friendly_field}: `{value}`")
                    if evidence_parts:
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;*Match:* {', '.join(evidence_parts)}")

            st.markdown("---")

        if len(candidates) > 50:
            msg = f"Showing 50 of {len(candidates)} results. Refine your search for more."
            st.info(msg)


def render_followup_suggestions(response_data: dict, msg_index: int = 0):
    """Render follow-up question suggestions as clickable buttons.

    Args:
        response_data: The API response containing suggested_followups
        msg_index: Index of the message (for unique button keys)
    """
    chat_response = response_data.get("response", {})
    followups = chat_response.get("suggested_followups", [])

    if not followups:
        return

    st.markdown("**Suggested follow-ups:**")
    cols = st.columns(min(len(followups), 3))

    for i, followup in enumerate(followups[:3]):
        with cols[i]:
            # Use unique key combining message index and followup index
            button_key = f"followup_{msg_index}_{i}_{hash(followup) % 10000}"
            if st.button(followup, key=button_key, use_container_width=True):
                # Add to messages and trigger rerun
                st.session_state.pending_message = followup
                st.rerun()


def main():
    """Main chat UI."""
    init_session_state()

    # Header
    st.title("📚 Rare Books Discovery")
    st.caption("Ask questions about the bibliographic collection")

    # API status indicator
    if not st.session_state.api_available:
        st.error(
            "⚠️ API not available. Make sure the server is running:\n"
            "```\nuvicorn app.api.main:app --reload\n```"
        )
        if st.button("🔄 Retry connection"):
            st.session_state.api_available = check_api_health()
            st.rerun()
        return

    # Sidebar with session info and controls
    with st.sidebar:
        st.header("Session")

        if st.session_state.session_id:
            st.success(f"Session: `{st.session_state.session_id[:8]}...`")
        else:
            st.info("New session will be created on first message")

        if st.button("🔄 New Session", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = None
            st.rerun()

        st.divider()

        st.header("Example Queries")
        examples = [
            "Books published by Oxford between 1500 and 1599",
            "Books printed in Paris in the 16th century",
            "Books about History",
            "Hebrew books from Amsterdam",
        ]
        for example in examples:
            if st.button(example, key=f"ex_{hash(example)}", use_container_width=True):
                st.session_state.pending_message = example
                st.rerun()

        st.divider()
        st.caption("API: " + API_BASE_URL)

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show details for assistant messages
            if msg["role"] == "assistant" and "response_data" in msg:
                render_candidate_details(msg["response_data"])

    # Handle pending message from buttons
    if "pending_message" in st.session_state:
        user_input = st.session_state.pending_message
        del st.session_state.pending_message
    else:
        user_input = None

    # Chat input
    if prompt := st.chat_input("Ask about rare books..."):
        user_input = prompt

    # Process user input
    if user_input:
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)

        # Get response from API
        with st.chat_message("assistant"):
            with st.spinner("Searching..."):
                response_data = send_message(user_input)

            if response_data:
                # Update session ID
                chat_response = response_data.get("response", {})
                if chat_response.get("session_id"):
                    st.session_state.session_id = chat_response["session_id"]

                # Format and display message
                assistant_message = format_assistant_message(response_data)
                st.markdown(assistant_message)

                # Show candidate details
                render_candidate_details(response_data)

                # Store in history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_message,
                    "response_data": response_data,
                })
            else:
                error_msg = "Sorry, I couldn't process your request. Please try again."
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                })

        # Show follow-up suggestions OUTSIDE the chat_message context
        # (buttons inside chat_message can have state issues)
        if response_data:
            render_followup_suggestions(response_data, len(st.session_state.messages))


if __name__ == "__main__":
    main()
