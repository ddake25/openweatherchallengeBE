from datetime import datetime, timezone
from typing import List

import httpx
from fastapi import FastAPI, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware
import os

from app.config import get_settings
from app.core.openweather_client import get_coords_for_city, fetch_weather_and_air
from app.core.risk_engine import (
    compute_heat_index_c,
    score_air_pollution,
    score_heat,
    combine_scores,
    build_contributing_factors,
)
from app.core.llm_client import call_ollama_for_explanation

from app.models.schemas import (
    HealthRiskRequest,
    HealthRiskResponse,
    RawWeather,
    RawAirQuality,
    ForecastPoint,
    Location,
    RiskSummary,
    FactorContribution,
    ChecklistItem,
)



settings = get_settings()
app = FastAPI(title="Weather-Driven Health Risk API", version="0.1.0")

# --- CORS setup ---
origins = [
    f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"],     
    allow_headers=["*"],
)
# --- end CORS setup ---

# -----------------------------
# MongoDB setup
# -----------------------------


@app.on_event("startup")
async def startup_db_client():
    app.state.mongo_client = AsyncIOMotorClient(settings.mongo_uri)
    app.state.mongo_db = app.state.mongo_client[settings.mongo_db]


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.mongo_client.close()


async def get_db():
    return app.state.mongo_db


def score_to_rating(score: int) -> str:
    """
    Map overall risk score (0–5) to a letter rating for UI:
    A = very safe, F = very risky.
    """
    if score <= 1:
        return "A"
    elif score == 2:
        return "B"
    elif score == 3:
        return "C"
    elif score == 4:
        return "D"
    else:
        return "E" 


# -----------------------------
# Health Risk endpoint
# -----------------------------


@app.post("/api/health-risk", response_model=HealthRiskResponse)
async def health_risk(
    req: HealthRiskRequest,
    db=Depends(get_db),
):
    if not req.location and not req.city:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'location' (lat/lon) or 'city'.",
        )

    # Resolve location
    if req.location:
        loc: Location = req.location
    else:
        loc = await get_coords_for_city(req.city)  

    # Fetch OpenWeather data
    try:
        weather_json, air_json = await fetch_weather_and_air(loc.lat, loc.lon)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error calling OpenWeather: {e}",
        )

    # Current weather
    current = weather_json.get("current", {})
    temp_c = current.get("temp")
    humidity = current.get("humidity")

    if temp_c is None or humidity is None:
        raise HTTPException(
            status_code=500,
            detail="Missing temperature or humidity data",
        )

    heat_index_c = compute_heat_index_c(temp_c, humidity)
    raw_weather = RawWeather(
        temperature_c=temp_c,
        humidity=humidity,
        heat_index_c=heat_index_c,
    )

    # Air quality
    air_list = air_json.get("list", [])
    if not air_list:
        raise HTTPException(status_code=500, detail="Missing air quality data")

    first_air = air_list[0]
    aqi = first_air.get("main", {}).get("aqi")
    if aqi is None:
        raise HTTPException(status_code=500, detail="Missing AQI data")

    components = first_air.get("components", {})
    raw_air = RawAirQuality(
        aqi=aqi,
        pm25=components.get("pm2_5"),
        pm10=components.get("pm10"),
        o3=components.get("o3"),
    )

    # Scores
    air_score = score_air_pollution(raw_air.aqi, raw_air.pm25, raw_air.o3)
    heat_score_val = score_heat(heat_index_c)
   
    # 1) Build scores from the engine
    scores = combine_scores(
        air_score,
        heat_score_val,
        temperature_c=raw_weather.temperature_c,
        humidity=raw_weather.humidity,
        heat_index_c=raw_weather.heat_index_c,
        profile=req.profile,
    )

    # 2) Unpack for convenience
    asthma_risk = scores.asthma_risk
    heat_risk = scores.heat_risk
    dehydration_risk = scores.dehydration_risk
    overall_risk = scores.overall_risk

    # 3) Compute a letter rating 
    rating = "A"
    if overall_risk.score == 2:
        rating = "B"
    elif overall_risk.score == 3:
        rating = "C"
    elif overall_risk.score >= 4:
        rating = "D"

    # 4) Now your existing risk_summary block works
    risk_summary = RiskSummary(
        overall_level=overall_risk.level,
        overall_score=overall_risk.score,
        asthma_level=asthma_risk.level,
        heat_level=heat_risk.level,
        dehydration_level=dehydration_risk.level,
        rating=rating,
        message=f"Overall risk is {overall_risk.level} today in {loc.name}.",
    )


    # ---------- Contributing Factors (for pie charts) ----------
    # For asthma risk: we consider PM2.5, Ozone, and profile as main drivers.
    asthma_factors: list[FactorContribution] = []
    base_weights = []

    # Start with air pollution
    if raw_air.pm25 is not None:
        base_weights.append(("PM2.5", 0.6))
    if raw_air.o3 is not None:
        base_weights.append(("Ozone (O3)", 0.3))

    # Profile contribution if at-risk user
    profile_weight = 0.1
    at_risk_profile = False
    if req.profile:
        if req.profile.age and req.profile.age >= 65:
            at_risk_profile = True
        lower = [c.lower() for c in req.profile.conditions]
        if "asthma" in " ".join(lower):
            at_risk_profile = True

    if at_risk_profile:
        base_weights.append(("Profile (asthma/age)", profile_weight))

    # Normalize to 100%
    total_w = sum(w for _, w in base_weights) or 1.0
    for name, w in base_weights:
        asthma_factors.append(
            FactorContribution(
                factor=name,
                percentage=round(100.0 * w / total_w, 1),
            )
        )

    # For heat risk: we consider heat index, humidity, and profile
    heat_factors: list[FactorContribution] = []
    heat_weights = [
        ("Heat Index", 0.7),
        ("Humidity", 0.2),
    ]
    if at_risk_profile:
        heat_weights.append(("Profile (age/heart/resp.)", 0.1))

    total_hw = sum(w for _, w in heat_weights) or 1.0
    for name, w in heat_weights:
        heat_factors.append(
            FactorContribution(
                factor=name,
                percentage=round(100.0 * w / total_hw, 1),
            )
        )

    contributing_factors = build_contributing_factors(
        raw_weather=raw_weather,
        raw_air=raw_air,
        profile=req.profile,
        scores=scores,
    )

    # Forecast (from hourly section, next 24h)
    forecast_points: list[ForecastPoint] = []
    hourly = weather_json.get("hourly", [])[:24]

    for h in hourly:
        h_temp_c = h.get("temp")
        h_humidity = h.get("humidity")
        h_dt = h.get("dt")
        if h_temp_c is None or h_humidity is None or h_dt is None:
            continue

        # Heat index and heat score for that hour
        h_hi_c = compute_heat_index_c(h_temp_c, h_humidity)
        h_heat_score = score_heat(h_hi_c)

        # Reuse current air score 
        h_air_score = air_score

        # Use the new combine_scores signature (includes dehydration + overall)
        h_scores = combine_scores(
            h_air_score,
            h_heat_score,
            temperature_c=h_temp_c,
            humidity=h_humidity,
            heat_index_c=h_hi_c,
            profile=req.profile,
        )

        forecast_points.append(
            ForecastPoint(
                time=datetime.fromtimestamp(h_dt, tz=timezone.utc),
                asthma_risk_level=h_scores.asthma_risk.level,
                heat_risk_level=h_scores.heat_risk.level,
                overall_risk_score=h_scores.overall_risk.score,
            )
        )

    # LLM explanation (Ollama)
    llm_expl = await call_ollama_for_explanation(
        location=loc,
        raw_weather=raw_weather,
        raw_air=raw_air,
        scores=scores,
        profile=req.profile,
    )

    # Personal Health Checklist from LLM actions
    checklist_items = [
        ChecklistItem(text=a) for a in llm_expl.actions
    ]

    now_utc = datetime.now(timezone.utc)

    response = HealthRiskResponse(
        location=loc,
        timestamp=now_utc,
        raw_data={
            "weather": raw_weather.dict(),
            "air_quality": raw_air.dict(),
        },
        scores=scores,
        forecast=forecast_points,
        llm_explanation=llm_expl,
        risk_summary=risk_summary,
        contributing_factors=contributing_factors,
        checklist=checklist_items,
    )


    # Log to MongoDB
    log_doc = {
    "timestamp": now_utc,
    "request": req.dict(),
    "location": loc.dict(),
    "raw_data": response.raw_data,
    "scores": response.scores.dict(),
    "risk_summary": response.risk_summary.dict(),
    "contributing_factors": response.contributing_factors.dict(),
    "llm_explanation": response.llm_explanation.dict(),
    "checklist": [item.dict() for item in response.checklist],
    }

    await db["risk_logs"].insert_one(log_doc)

    return response

# pip install -r requirements.txt


# -----------------------------
# Simple health check
# -----------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok"}
