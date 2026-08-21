"""Streamlit chat entry point.

Two-phase flow. Each message runs build_intake_crew() first and checks the
resulting TripPlan's open_questions. If anything's still missing, the
questions are shown and the app waits for the next message, accumulating
the whole conversation as context for the next intake attempt. Once
open_questions comes back empty, it runs build_crew(intake_plan=draft_plan)
once for real and shows the presenter agent's write-up -- passing the
already-satisfied draft straight in so the full crew doesn't rerun intake
from scratch, see agent.py's build_crew() docstring.

The sidebar shows the same draft TripPlan that already decides whether to
ask a clarifying question, nothing new is computed for it. It's a status
panel, not a second source of truth.
"""

import streamlit as st
from dotenv import load_dotenv

from tripcrew.agent import build_crew, build_intake_crew
from tripcrew.pdf_export import build_trip_pdf
from tripcrew.schemas import TripPlan

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
       the sidebar only, the chat itself keeps its normal readable size.
       color is set explicitly here rather than left to theme.textColor:
       the theme's #26263D against this sidebar's #6E8CC7 background comes
       out to a 4.37:1 WCAG contrast ratio, just under the 4.5:1 AA
       threshold for text this small, computed directly rather than
       eyeballed. #1A1A1A clears it at 5.17:1. */
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] li {
        font-size: 13px;
        line-height: 1.3;
        margin-bottom: 0.25rem;
        color: #1A1A1A;
    }
    /* Same reasoning as the rule above, worse starting point: the original
       #6B4A9E purple and #B35900 orange against this sidebar's blue
       measured at 2.01:1 and 1.44:1, badly failing AA. Any color that
       clears 4.5:1 against this particular blue ends up dark enough to
       read as near-black -- the tradeoff Sujan chose over adding a light
       chip behind each heading. Still tinted (deep plum, dark rust), just
       far darker than the original brand colors. */
    .heading-purple { color: #2B1E3F; font-weight: bold; font-size: 14px; }
    .heading-orange { color: #391C00; font-weight: bold; font-size: 14px; }
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
if "trip_write_up" not in st.session_state:
    # Only ever set once the full crew actually finishes (see the
    # `if prompt:` block below), never during the clarification loop --
    # its presence is what render_sidebar() checks to decide whether
    # there's a finished plan worth offering as a PDF, rather than trying
    # to infer "finished" from TripPlan's own fields.
    st.session_state.trip_write_up = None


def render_sidebar() -> None:
    """Shows what the intake agent currently knows, read straight off
    st.session_state.trip_plan, the same draft TripPlan already used to
    decide whether to ask a clarifying question.

    Origin and travel dates aren't fields on TripPlan itself (see
    schemas.py, destination and days are the only trip-level fields),
    they only exist once a flight or hotel has actually been searched, so
    they're read off those instead of inventing new schema fields just for
    display.

    Reflects the final consolidated plan once the full crew finishes, not
    just the pre-crew draft: the `if prompt:` block pulls the consolidation
    task's structured TripPlan (the one with the real computed budget) out
    of the crew result and overwrites st.session_state.trip_plan with it.
    Previously this only ever showed the draft, real budget included, since
    build_crew().kickoff()'s own .pydantic is the last task's output (the
    presenter's free-text write-up, not the consolidation task's TripPlan).
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
        elif st.session_state.trip_write_up:
            # trip_write_up only gets set once the full crew finishes (see
            # the `if prompt:` block), so its presence here means `plan` is
            # the real consolidated TripPlan, not the pre-crew draft --
            # safe to hand both to build_trip_pdf. Rebuilt on every rerun
            # rather than cached: it's a fast, local, no-network render, not
            # worth the staleness risk of caching it against "Start over"
            # or a follow-up message forgetting to invalidate it.
            pdf_bytes = build_trip_pdf(plan, st.session_state.trip_write_up)
            st.sidebar.download_button(
                "Download trip plan (PDF)",
                data=pdf_bytes,
                file_name=f"{plan.destination.lower().replace(' ', '_')}_trip_plan.pdf",
                mime="application/pdf",
            )

    st.sidebar.divider()
    if st.sidebar.button("Start over"):
        st.session_state.messages = []
        st.session_state.conversation = ""
        st.session_state.trip_plan = None
        st.session_state.trip_write_up = None
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
            # A live step indicator, not just a spinner. build_crew(intake_plan=...)
            # runs itinerary research, consolidation, and presentation in that
            # fixed order (Process.sequential), so task_callback firing once
            # per completed task can be counted against STAGE_LABELS below to
            # know which stage just finished -- CrewAI's own hook (confirmed
            # in its source: crew_task_callback fires as task.callback(task.output)
            # right after each task completes), nothing bolted on. kickoff()
            # is a normal blocking call, so this callback runs synchronously
            # from inside it; calling .write() on the status object we already
            # hold updates the same widget immediately, no rerun needed, the
            # same mechanism st.progress() and st.status() are built for.
            STAGE_LABELS = [
                "Researching attractions & weather",
                "Consolidating the plan & budget",
                "Writing it up",
            ]
            with st.status("Planning the full trip...", expanded=True) as status:
                stage_count = {"done": 0}

                def mark_stage_done(task_output):
                    # Deliberately swallows everything -- a failure updating
                    # the status widget must never be able to take the real
                    # crew run down with it (build_crew()'s task_callback
                    # isn't wrapped in try/except itself, this is where that
                    # safety has to live instead).
                    try:
                        i = stage_count["done"]
                        if i < len(STAGE_LABELS):
                            status.write(f"✓ {STAGE_LABELS[i]}")
                        stage_count["done"] += 1
                    except Exception:
                        pass

                result = build_crew(intake_plan=draft_plan, task_callback=mark_stage_done).kickoff(
                    inputs={"request": st.session_state.conversation}
                )
                status.update(label="Trip planned", state="complete")

            # kickoff()'s own .pydantic is the LAST task's output (the
            # presenter's, which has no output_pydantic set -- confirmed
            # via crew.py's _create_crew_output, it just copies whichever
            # task ran last). The real structured plan, with the actual
            # computed budget, lives on the consolidation task specifically,
            # found here by type rather than a fixed list index so this
            # doesn't silently break if build_crew()'s task order ever
            # changes. Previously the sidebar kept showing the pre-crew
            # draft even after the full plan finished (see render_sidebar's
            # own docstring) -- this is that fix.
            consolidated_plan = next(
                (t.pydantic for t in result.tasks_output if isinstance(t.pydantic, TripPlan)),
                None,
            )
            if consolidated_plan is not None:
                st.session_state.trip_plan = consolidated_plan

            response = str(result)
            st.session_state.trip_write_up = response
            st.write(response)

    st.session_state.messages.append({"role": "assistant", "content": response})

# Rendered last on purpose: session_state.trip_plan may have just been
# updated above, in the if prompt: block, on this exact rerun. Streamlit
# doesn't care where in the script a st.sidebar call happens, it always
# lands in the sidebar column, so calling this at the end means the panel
# reflects this turn's result instead of lagging one message behind.
render_sidebar()
