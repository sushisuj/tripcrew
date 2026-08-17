Architecture
============

This page is a skeleton. Real architecture diagrams come once the planning
loop and clarification flow are actually built -- documenting a design
that's still moving isn't worth much yet. What follows is the current
intent, not a finished design.

Single agent, multiple tools
------------------------------

One ``Travel Planner`` agent with four tools (flights, hotels, weather,
attractions), letting CrewAI's own tool-calling loop decide sequencing --
deliberately not a fan-out of specialist agents the way the code-review-crew
project split bug/security/style reviewers. Flights, hotels, weather, and
attractions are interdependent (a hotel choice depends on flight dates
landing the trip in a particular window; weather can inform which
attractions make sense), so one agent reasoning step by step matches the
project brief's own language more literally than parallel specialists would.

Why flights and hotels are mocked
------------------------------------

Real live-price flight and hotel APIs (Skyscanner, Kiwi, Booking.com) gate
access behind a business-partner approval process with no published
timeline -- not workable against a deadline. Amadeus's self-service sandbox
is the realistic path if genuine API integration happens later, but its
free tier returns test data, not live prices, so even that wouldn't be live
pricing. For now, ``tripcrew/tools/flights.py`` and ``tripcrew/tools/hotels.py``
return mocked data shaped exactly like a real response, so swapping the
implementation later doesn't require touching anything that calls them.

Not yet designed
-------------------

- The multi-turn clarification loop (asking for origin city, dates, or
  budget when missing, then resuming with the answer)
- Error handling for tool/API failures beyond raising
- The PDF export step
- Whether/how the plan hands off to a document Q&A chatbot afterward
