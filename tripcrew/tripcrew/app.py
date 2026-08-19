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
#
# The button/chat-input rules below are the same beveled-skeuomorphism
# technique 98.css uses for Windows 98 buttons: two stacked inset
# box-shadows, each split into a light corner and a dark corner, recolored
# from Windows gray into this app's tan/cream palette. A button reads as
# raised (light top-left, dark bottom-right, like light hitting a bump), a
# field you type into reads as sunken (the same two colors swapped), which
# is the old-web convention this retro pass is going for. Confirmed by
# reading 98.css's actual source rather than guessing at the mechanism --
# it's stacked box-shadow, not a border-color trick. stChatInput's visible
# border lives directly on the [data-testid="stChatInput"] div itself, not
# a separate wrapper, confirmed by inspecting the rendered DOM.
st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        background-color: #6E8CC7;
    }

    :root {
        --bevel-hi: #FFFFFF;
        --bevel-hi2: #F7F6EC;
        --bevel-sh: #9C9880;
        --bevel-sh2: #4A4736;
    }

    .stButton > button, [data-testid="stChatInputSubmitButton"] {
        border: none !important;
        border-radius: 0 !important;
        background-color: #DCD9C4 !important;
        box-shadow:
            inset -1px -1px var(--bevel-sh2),
            inset 1px 1px var(--bevel-hi),
            inset -2px -2px var(--bevel-sh),
            inset 2px 2px var(--bevel-hi2) !important;
    }
    .stButton > button:active, [data-testid="stChatInputSubmitButton"]:active {
        box-shadow:
            inset -1px -1px var(--bevel-hi),
            inset 1px 1px var(--bevel-sh2),
            inset -2px -2px var(--bevel-hi2),
            inset 2px 2px var(--bevel-sh) !important;
    }

    [data-testid="stChatInput"] {
        border: none !important;
        border-radius: 0 !important;
        background-color: #FFFFFF !important;
        box-shadow:
            inset -1px -1px var(--bevel-hi),
            inset 1px 1px var(--bevel-sh2),
            inset -2px -2px var(--bevel-hi2),
            inset 2px 2px var(--bevel-sh) !important;
    }
    /* The visible blue pill isn't actually on the stChatInput div itself,
       it's painted by its direct child (Streamlit's own theme CSS, an
       unstable auto-generated class), confirmed by walking computed
       styles down the DOM. Strip that one layer so the white sunken
       background set above shows through instead of sitting underneath. */
    [data-testid="stChatInput"] > div {
        background-color: transparent !important;
    }

    /* Denser sidebar type, an old portal nav packed a lot into a narrow
       column instead of Streamlit's default generous spacing. Scoped to
       the sidebar only, the chat itself keeps its normal readable size. */
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] li {
        font-size: 13px;
        line-height: 1.3;
        margin-bottom: 0.25rem;
    }
    .heading-purple { color: #6B4A9E; font-weight: bold; font-size: 14px; }
    .heading-orange { color: #B35900; font-weight: bold; font-size: 14px; }
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
    st.sidebar.markdown('<div class="heading-purple">Trip so far</div>', unsafe_allow_html=True)

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
            st.sidebar.markdown('<div class="heading-orange">Still need</div>', unsafe_allow_html=True)
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
