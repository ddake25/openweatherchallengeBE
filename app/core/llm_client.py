import json
from typing import Optional

import httpx

from app.config import get_settings
from app.models.schemas import (
    Location,
    RawWeather,
    RawAirQuality,
    Scores,
    Profile,
    LLMExplanation,
)

settings = get_settings()


def _strip_code_fences(text: str) -> str:
    """
    Remove ```json ... ``` style fences if the model includes them
    despite the instructions.
    """
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop first line (``` or ```json)
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # drop last line if it is ```
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


async def call_ollama_for_explanation(
    location: Location,
    raw_weather: RawWeather,
    raw_air: RawAirQuality,
    scores: Scores,
    profile: Optional[Profile],
) -> LLMExplanation:
    """
    Calls Ollama's /api/chat endpoint with a prompt asking for JSON.
    """

    system_prompt = (
        "You are a careful health-literacy assistant. "
        "You help people understand how weather and air quality affect health risks. "
        "You explain in simple, non-alarming language, and you do NOT give diagnoses "
        "or prescribe specific treatments or medications. "
        "IMPORTANT BEHAVIOR:\n"
        "- If a health profile is provided (age and conditions), you MUST tailor your "
        "  explanation and recommendations to that profile.\n"
        "- In particular, the field 'profile_specific_note' MUST explicitly mention at "
        "  least one of the listed conditions by name (e.g., asthma, hypertension, fever, malaria) "
        "  and explain how today's conditions might matter for that person, in general terms.\n"
        "- If conditions are acute (e.g., fever, malaria), you may give only very general, "
        "  non-diagnostic guidance (rest, hydration, seek medical review when needed) and "
        "  suggest speaking to a healthcare professional, without confirming or managing the disease.\n"
        "- Never invent new conditions that are not in the profile.\n"
        "RESPONSE FORMAT:\n"
        "Respond with JSON ONLY. Do not include markdown, code fences, or any text "
        "before or after the JSON. The JSON must have keys: summary, details, actions, "
        "profile_specific_note."
    )


    if profile and profile.conditions:
        cond_str = ", ".join(profile.conditions)
        profile_text = f"age={profile.age}, conditions={cond_str}"
    elif profile:
        profile_text = f"age={profile.age}, conditions=none specified"
    else:
        profile_text = "not provided"


    user_prompt = f"""
        Here is today's environmental risk data and a brief health profile.

        Overall risk: {scores.overall_risk.level} (score {scores.overall_risk.score})
        Asthma/respiratory risk: {scores.asthma_risk.level} (score {scores.asthma_risk.score})
        Heat stress risk: {scores.heat_risk.level} (score {scores.heat_risk.score})
        Dehydration risk: {scores.dehydration_risk.level} (score {scores.dehydration_risk.score})
   
        Location: {location.name or ''} (lat={location.lat}, lon={location.lon})
        Overall risk: {scores.overall_risk.level} (score {scores.overall_risk.score})
        Asthma/respiratory risk: {scores.asthma_risk.level} (score {scores.asthma_risk.score})
        Heat stress risk: {scores.heat_risk.level} (score {scores.heat_risk.score})

        Key numbers:
        - Temperature: {raw_weather.temperature_c:.1f} °C
        - Humidity: {raw_weather.humidity:.1f} %
        - Heat index: {raw_weather.heat_index_c:.1f} °C
        - AQI (OpenWeather): {raw_air.aqi}
        - PM2.5: {raw_air.pm25}
        - PM10: {raw_air.pm10}
        - Ozone (O3): {raw_air.o3}

        Profile: {profile_text}

        Please respond in JSON ONLY with this structure:
        {{
          "summary": "...",
          "details": "...",
          "actions": ["...", "..."],
          "profile_specific_note": "..."
        }}

        - "summary": 1–2 sentences giving the big picture.
        - "details": 3–6 sentences explaining what is going on and why.
        - "actions": 3–6 short bullet-like phrases with practical steps.
        - "profile_specific_note": 1–2 sentences specifically for this profile (or a generic note if no profile).
        """

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data.get("message", {}).get("content", "") or ""
    content = _strip_code_fences(content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Last-resort fallback if the model still misbehaves
        parsed = {
            "summary": content[:200],
            "details": content,
            "actions": [],
            "profile_specific_note": "",
        }

    # Let LLMExplanation's validators normalize types 
    return LLMExplanation(
        summary=parsed.get("summary"),
        details=parsed.get("details"),
        actions=parsed.get("actions"),
        profile_specific_note=parsed.get("profile_specific_note"),
    )
