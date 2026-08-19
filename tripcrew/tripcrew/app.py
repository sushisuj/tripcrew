"""Streamlit chat entry point.

Two-phase flow. Each message runs build_intake_crew() first and checks the
resulting TripPlan's open_questions. If anything's still missing, the
questions are shown and the app waits for the next message, accumulating
the whole conversation as context for the next intake attempt. Once
open_questions comes back empty, it runs the full build_crew() pipeline
once for real and shows the presenter agent's write-up.

Known simplification, see agent.py's build_intake_crew() docstring: the
full crew's own intake task reruns from scratch rather than reusing the
already-satisfied draft. One redundant LLM call, not a correctness issue.
"""

import streamlit as st
from dotenv import load_dotenv

from tripcrew.agent import build_crew, build_intake_crew

load_dotenv()
st.set_page_config(page_title="tripcrew", layout="centered", initial_sidebar_state="expanded")

# Streamlit's theme.secondaryBackgroundColor only colors the sidebar once the
# sidebar actually renders, and an empty `st.sidebar` renders nothing at all,
# not even with initial_sidebar_state="expanded" -- confirmed by testing, not
# assumed. st.sidebar.write("") is the placeholder that forces the panel to
# exist until real content (trip status, open questions) lands in it.
# stHeader isn't covered by the theme config at all, colored separately here
# so the chrome wraps top and side to match.
st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        background-color: #8FA8D9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.sidebar.write("")

st.title("tripcrew")
st.caption("Tell it where you want to go. It'll ask if it needs more.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation" not in st.session_state:
    st.session_state.conversation = ""

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

prompt = st.chat_input("Plan a trip...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    st.session_state.conversation += f"\n{prompt}"

    with st.chat_message("assistant"):
        with st.spinner("Checking what's needed..."):
            intake_result = build_intake_crew().kickoff(
                inputs={"request": st.session_state.conversation}
            )
            draft_plan = intake_result.pydantic

        if draft_plan and draft_plan.open_questions:
            response = "Before I plan this, I need a bit more:\n\n" + "\n".join(
                f"- {q}" for q in draft_plan.open_questions
            )
            st.write(response)
        else:
            with st.spinner("Planning the full trip..."):
                result = build_crew().kickoff(inputs={"request": st.session_state.conversation})
            response = str(result)
            st.write(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
