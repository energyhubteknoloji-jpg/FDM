import requests
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WeatherService:
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def get_coordinates(self, city_name):
        """
        Get latitude and longitude for a given city/district name.
        """
        try:
            search_term = city_name
            context_city = None
            if "," in city_name:
                parts = city_name.split(",")
                if len(parts) >= 2:
                    search_term = parts[0].strip()
                    context_city = parts[1].strip()

            params = {"name": search_term, "count": 100, "language": "tr", "format": "json"}
            response = requests.get(self.GEOCODING_URL, params=params, timeout=8)
            data = response.json()
            
            if "results" in data and len(data["results"]) > 0:
                results = data["results"]
                
                if context_city:
                    context_lower = context_city.lower()
                    
                    for r in results:
                        admin1 = r.get("admin1", "").lower()
                        admin2 = r.get("admin2", "").lower()
                        country = r.get("country", "").lower()
                        
                        if context_lower in admin1 or context_lower in admin2 or context_lower in country:
                            return r["latitude"], r["longitude"], f"{r['name']} ({r.get('admin1', '')})"
                            
                    for r in results:
                         admin1 = r.get("admin1", "").lower()
                         if context_lower in admin1:
                             return r["latitude"], r["longitude"], f"{r['name']} ({r.get('admin1', '')})"
                    
                    logger.info(f"WeatherService: '{search_term}' found, but not in '{context_city}'. returning first result.")
                    
                result = results[0]
                display_name = result["name"]
                if "admin1" in result:
                    display_name += f" ({result['admin1']})"
                
                return result["latitude"], result["longitude"], display_name

            return None
        except Exception as e:
            logger.error(f"WeatherService: Geocoding error for {city_name}: {e}")
            return None

    def get_historical_weather(self, lat, lon, start_date, end_date):
        """
        Fetch historical hourly temperature (2m) for a date range.
        """
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "hourly": "temperature_2m",
                "timezone": "Europe/Istanbul"
            }
            response = requests.get(self.ARCHIVE_URL, params=params, timeout=10)
            data = response.json()
            
            if "hourly" in data:
                times = data["hourly"]["time"]
                temps = data["hourly"]["temperature_2m"]
                
                result = []
                for t, temp in zip(times, temps):
                    if temp is not None:
                        formatted_time = t.replace('T', ' ') + ":00"
                        result.append((formatted_time, temp))
                return result
            return []
        except Exception as e:
            logger.error(f"WeatherService: Historical data error: {e}")
            return []

    def get_current_weather(self, lat, lon):
        """
        Fetch current and forecast weather.
        """
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "timezone": "Europe/Istanbul",
                "past_days": 1,
                "forecast_days": 1 
            }
            response = requests.get(self.FORECAST_URL, params=params, timeout=8)
            data = response.json()
            
            if "hourly" in data:
                times = data["hourly"]["time"]
                temps = data["hourly"]["temperature_2m"]
                
                result = []
                for t, temp in zip(times, temps):
                    if temp is not None:
                        formatted_time = t.replace('T', ' ') + ":00"
                        result.append((formatted_time, temp))
                return result
            return []
        except Exception as e:
            logger.error(f"WeatherService: Forecast data error: {e}")
            return []
