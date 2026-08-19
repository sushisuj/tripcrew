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

The sidebar shows the same draft TripPlan that already decides whether to
ask a clarifying question, nothing new is computed for it. It's a status
panel, not a second source of truth.
"""

import streamlit as st
from dotenv import load_dotenv

from tripcrew.agent import build_crew, build_intake_crew

load_dotenv()
st.set_page_config(page_title="tripcrew", layout="centered", initial_sidebar_state="expanded")

# stHeader isn't covered by theme.secondaryBackgroundColor at all, colored
# separately here so the chrome wraps top and side to match.
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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation" not in st.session_state:
    st.session_state.conversation = ""
if "trip_plan" not in st.session_state:
    st.session_state.trip_plan = None


def render_sidebar() -> None:
    """Shows what the intake agent currently knows, read straight off
    st.session_state.trip_plan, the same draft TripPlan already used to
    decide whether to ask a clarifying question.

    Origin and travel dates aren't fields on TripPlan itself (see
    schemas.py, destination and days are the only trip-level fields),
    they only exist once a flight or hotel has actually been searched, so
    they're read off those instead of inventing new schema fields just for
    display.

    Doesn't yet reflect the final consolidated plan once the full crew
    finishes, only the draft, real budget included. build_crew().kickoff()
    only exposes the presentation task's free-text write-up, not the
    consolidation task's structured TripPlan, so there's nothing
    consolidated to show here yet. Follow-up, not solved in this pass.
    """
    plan = st.session_state.trip_plan

    st.sidebar.title("tripcrew")
    st.sidebar.markdown("**Trip so far**")

    if plan is None:
        st.sidebar.write("Nothing yet, say where you want to go.")
    else:
        origin = plan.flights[0].origin if plan.flights else "—"
        dates = plan.flights[0].departure_date if plan.flights else (plan.hotel.check_in if plan.hotel else "—")
        st.sidebar.write(f"Destination: {plan.destination or '—'}")
        st.sidebar.write(f"Days: {plan.days or '—'}")
        st.sidebar.write(f"Origin: {origin}")
        st.sidebar.write(f"Dates: {dates}")

        if plan.open_questions:
            st.sidebar.markdown("**Still need**")
            for question in plan.open_questions:
                st.sidebar.write(f"- {question}")

    st.sidebar.divider()
    if st.sidebar.button("Start over"):
        st.session_state.messages = []
        st.session_state.conversation = ""
        st.session_state.trip_plan = None
        st.rerun()


st.title("tripcrew")
st.caption("Tell it where you want to go. It'll ask if it needs more.")

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
            st.session_state.trip_plan = draft_plan

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

# Rendered last on purpose: session_state.trip_plan may have just been
# updated above, in the if prompt: block, on this exact rerun. Streamlit
# doesn't care where in the script a st.sidebar call happens, it always
# lands in the sidebar column, so calling this at the end means the panel
# reflects this turn's result instead of lagging one message behind.
render_sidebar()
