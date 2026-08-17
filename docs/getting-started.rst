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
