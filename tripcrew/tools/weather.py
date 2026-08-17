"""Weather lookup via OpenWeatherMap.

Real data, no stubbing needed here -- OpenWeatherMap's free tier is an
instant signup, no approval gate, unlike flights and hotels.
"""

import os

import requests
from crewai.tools import tool

from tripcrew.schemas import WeatherReport

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"
OPENWEATHER_GEO = "https://api.openweathermap.org/geo/1.0/direct"

