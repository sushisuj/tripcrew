Getting started
===============

Environment setup
------------------

.. code-block:: bash

   python3.10 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

Then create a ``.env`` file (never committed -- see ``.env.example`` for the
shape) with your own API keys:

.. code-block:: text

   GROQ_API_KEY=<groq-key>
   OPENWEATHER_API_KEY=<openweathermap-key>
   OPENTRIPMAP_API_KEY=<opentripmap-key>

Running the app
----------------

.. code-block:: bash

   streamlit run tripcrew/app.py

Running tests
--------------

.. code-block:: bash

   pytest

Known gotchas
--------------

The LLM is Groq, via LiteLLM's native ``groq/`` provider prefix, not the
NVIDIA NIM setup this project started with. No ``base_url`` needed, LiteLLM
knows Groq's endpoint already, just ``GROQ_API_KEY`` in the environment.
The model is ``openai/gpt-oss-20b`` -- yes, with an ``openai/`` in the name,
that's Groq's own naming for one of their hosted models, unrelated to
LiteLLM's provider-prefix syntax. Check Groq's deprecation page
(``console.groq.com/docs/deprecations``) before assuming a model name from
memory or an old tutorial still works, several previously-obvious choices
(``llama-3.1-8b-instant``, ``llama-3.3-70b-versatile``) were retired
08/16/26.
