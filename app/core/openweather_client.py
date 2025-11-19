import asyncio
from typing import Tuple

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models.schemas import Location

settings = get_settings()


async def get_coords_for_city(city: str) -> Location:
    """
    Use OpenWeather Geocoding API to resolve city to lat/lon.

    Accepts strings like:
    - "London"
    - "Accra"
    - "Washington,DC,US"
    """
    city = city.strip()

    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": city, "limit": 1, "appid": settings.openweather_api_key}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error from OpenWeather geocoding: {e.response.status_code} {e.response.text}",
        )

    data = resp.json()

    if not data:
        raise HTTPException(status_code=404, detail=f"City not found for query: {city}")

    item = data[0]
    return Location(lat=item["lat"], lon=item["lon"], name=item.get("name"))


async def fetch_weather_and_air(lat: float, lon: float) -> Tuple[dict, dict]:
    """
    Fetch current weather, short-term forecast, and air quality using
    OpenWeather's FREE 2.5 APIs instead of One Call 3.0.

    We then normalize the result to look like:
      {
        "current": { "temp": ..., "humidity": ..., "dt": ... },
        "hourly": [
          { "temp": ..., "humidity": ..., "dt": ... },
          ...
        ]
      }

    so the rest of the code in main.py can stay the same.
    """

    current_url = "https://api.openweathermap.org/data/2.5/weather"
    current_params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.openweather_api_key,
        "units": "metric",
    }

    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    # cnt=8 → next 24 hours at 3-hour intervals (8 * 3h = 24h)
    forecast_params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "cnt": 8,
    }

    air_url = "https://api.openweathermap.org/data/2.5/air_pollution"
    air_params = {
        "lat": lat,
        "lon": lon,
        "appid": settings.openweather_api_key,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        current_resp, forecast_resp, air_resp = await asyncio.gather(
            client.get(current_url, params=current_params),
            client.get(forecast_url, params=forecast_params),
            client.get(air_url, params=air_params),
        )

    # Raise errors with some detail if anything failed
    try:
        current_resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error from OpenWeather current weather: {e.response.status_code} {e.response.text}",
        )

    try:
        forecast_resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error from OpenWeather forecast: {e.response.status_code} {e.response.text}",
        )

    try:
        air_resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error from OpenWeather air quality: {e.response.status_code} {e.response.text}",
        )

    current_json = current_resp.json()
    forecast_json = forecast_resp.json()
    air_json = air_resp.json()

    # Normalize into the "onecall-like" structure our main code expects
    # current
    main_block = current_json.get("main", {})
    current_struct = {
        "temp": main_block.get("temp"),
        "humidity": main_block.get("humidity"),
        "dt": current_json.get("dt"),
    }

    # hourly-like, use forecast list (each is 3h)
    hourly_struct = []
    for item in forecast_json.get("list", []):
        m = item.get("main", {})
        hourly_struct.append(
            {
                "temp": m.get("temp"),
                "humidity": m.get("humidity"),
                "dt": item.get("dt"),
            }
        )

    weather_json = {
        "current": current_struct,
        "hourly": hourly_struct,
    }

    return weather_json, air_json
