"""Streamlit chat entry point.

Skeleton only for now -- structurally based on chat_app.py from the
code-review-crew project, but that one fires a single crew.kickoff() per
message with no memory of what came before. This needs an actual multi-turn
loop so the agent can ask "what dates?" and use the answer on the next
message, which chat_app.py's pattern doesn't support as written. Not built
yet -- flagged here instead of silently copy-pasted and left broken.
"""

import streamlit as st
from dotenv import load_dotenv

from tripcrew.agent import build_planner_agent

load_dotenv()
st.set_page_config(page_title="tripcrew", layout="centered")

st.title("tripcrew")
st.caption("Tell it where you want to go. It'll ask if it needs more.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

prompt = st.chat_input("Plan a trip...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        st.warning(
            "Planning loop not wired up yet -- this is a skeleton. "
            "build_planner_agent() exists but nothing calls it end-to-end "
            "with the clarification flow yet."
        )

    st.session_state.messages.append(
        {"role": "assistant", "content": "(planning loop not implemented yet)"}
    )
