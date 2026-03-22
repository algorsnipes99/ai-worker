from functions.function import Function
from typing import Dict, Any
import requests
import os

class WeatherFunction(Function):
    """Get current weather for a location using OpenWeatherMap API"""

    # Register the get_current_weather tool. If OPENWEATHER_API_KEY is not set,
    # the tool will return mock data instead of calling the real API.
    def __init__(self):
        super().__init__(
            name="get_current_weather",
            description="Get current weather in a location",
            parameters={
                "location": {"type": "string", "description": "City name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"}
            }
        )
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.use_mock = self.api_key is None
        if self.use_mock:
            print("Warning: OPENWEATHER_API_KEY not set - using mock weather data")

    # Fetch current weather from OpenWeatherMap, or return mock data if no API key is set.
    # Uses the geo endpoint to resolve city name to coordinates, then the weather endpoint.
    # @param args: Dict with 'location' (city name) and 'unit' ('celsius' or 'fahrenheit').
    # @returns: Dict with 'temp', 'condition', 'location', 'humidity', 'wind_speed', 'status'.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_mock:
            return {
                "temp": 22 if args["unit"] == "celsius" else 72,
                "condition": "Sunny",
                "location": args["location"],
                "humidity": 50,
                "wind_speed": 10,
                "status": "success (mock)"
            }

        try:
            # Get coordinates first
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={args['location']}&limit=1&appid={self.api_key}"
            geo_response = requests.get(geo_url).json()

            if not geo_response:
                return {"error": "Location not found", "status": "error"}

            lat = geo_response[0]['lat']
            lon = geo_response[0]['lon']

            # Get weather data
            units = "metric" if args["unit"] == "celsius" else "imperial"
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units={units}&appid={self.api_key}"
            weather_data = requests.get(weather_url).json()

            return {
                "temp": weather_data['main']['temp'],
                "condition": weather_data['weather'][0]['description'],
                "location": args["location"],
                "humidity": weather_data['main']['humidity'],
                "wind_speed": weather_data['wind']['speed'],
                "status": "success"
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}
