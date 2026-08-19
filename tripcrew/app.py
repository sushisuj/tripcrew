"""Streamlit chat entry point.

Calls the four-agent sequential crew from tripcrew.agent for each message.
Still no multi-turn clarification loop -- if the intake agent says
something's missing, the user has to ask again in a new message with that
info, there's no pause-and-resume mid-crew yet. That's a separate, harder
piece, not pretended to be solved here just because the crew now actually
runs.
"""

import streamlit as st
from dotenv import load_dotenv

from tripcrew.agent import build_crew

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
        with st.spinner("Planning..."):
            crew = build_crew()
            result = crew.kickoff(inputs={"request": prompt})
        response = str(result)
        st.write(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
