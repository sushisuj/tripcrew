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
