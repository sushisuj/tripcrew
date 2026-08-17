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
