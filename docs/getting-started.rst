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

   OPENAI_API_KEY=<nvidia-nim-key>
   OPENAI_API_BASE=https://integrate.api.nvidia.com/v1
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

Not many yet -- this project is young. The one already inherited from the
code-review-crew project: the LLM model string needs the ``openai/`` prefix
(``openai/meta/llama-3.1-8b-instruct``) or LiteLLM matches it against Meta's
own hosted API instead of NVIDIA's, and auth fails. Already handled in
``tripcrew/agent.py``, documented here so it isn't rediscovered.
