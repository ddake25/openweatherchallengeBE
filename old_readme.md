# Weather-Driven Health Risk API (Backend)

**Project Title**  
Weather-Driven Health Risk Alerts: Explaining Air & Heat Hazards for Vulnerable Populations

**Abstract**  
Extreme heat and poor air quality significantly increase the risk of asthma attacks, respiratory flare-ups, dehydration, and heat-related illness, especially among children, older adults, and people with chronic conditions. This backend combines OpenWeather’s real-time weather and air-quality data with a simple, explainable risk model to produce daily health risk levels for cities.

A lightweight FastAPI service computes separate risk scores for:
- **Asthma / respiratory risk** (driven by air quality)
- **Heat stress risk** (driven by heat index & humidity)
- **Dehydration risk** (driven by heat index, humidity, and age)  
These are combined into an overall daily risk score.

A local LLM (via Ollama) then turns the raw scores into clear, personalized explanations and practical precautions for at-risk populations. The result is a JSON API that can power dashboards and applications to help individuals, caregivers, and public-health teams understand when environmental conditions may be hazardous — and how to respond.

---

## What the Backend Does

- Uses **OpenWeather** (geocoding, current weather, hourly forecast).
- Uses **OpenWeather Air Pollution API** for AQI, PM2.5, PM10, and O₃.
- Computes:
  - Asthma / respiratory risk score
  - Heat stress risk score
  - Dehydration risk score
  - Combined overall risk score (0–4) + letter rating (A–E)
- Generates a **24-hour risk outlook** from hourly forecast.
- Calls **Ollama** (local LLM) to convert numbers into:
  - Plain-language summary
  - Detailed explanation
  - Actionable checklist items
  - Profile-specific note (based on age/conditions)
- Optionally logs requests + responses to **MongoDB** for future analysis.

The API is designed to be:
- **Explainable** (transparent scoring + contributing factors)
- **Privacy-preserving** (local LLM, no external health-data storage)
- **Composable** (can be plugged into any frontend or service)

---

## Tech Stack

- **Language:** Python 3.11
- **Framework:** FastAPI
- **HTTP client:** httpx
- **Config:** pydantic + pydantic-settings
- **Database:** MongoDB (via `motor`) – optional, used for logging
- **LLM Runtime:** Ollama (e.g. `phi4-mini`)
- **Server:** uvicorn

---

## Setup & Installation

### 1. Create and activate Conda environment

conda create -n weatherhealth python=3.11 -y
conda activate weatherhealth

### 2. Install Python dependencies
pip install fastapi uvicorn[standard] httpx motor pydantic pydantic-settings python-dotenv
                                    or
pip install -r requirements.txt

### 3. Configure environment variables
openweather_api_key=YOUR_OPENWEATHER_KEY
mongo_uri=mongodb://localhost:27017  # MongoDB connection (optional; used for logging).
mongo_db=weather_health

ollama_base_url=http://localhost:11434 # url to your ollama server
ollama_model=phi4-mini # or any local model you have pulled (e.g. llama3).

### 4. Start Ollama locally
ollama run phi4-mini

### 5. Run the FastAPI server
uvicorn app.main:app --reload

### 6. Quick Test via curl
curl -X POST http://localhost:8000/api/health-risk \
  -H "Content-Type: application/json" \
  -d '{
    "city": "London",
    "profile": {
      "age": 68,
      "conditions": ["asthma", "hypertension"]
    }
  }'


### 7. Notes & Limitations

This is not a medical device. It is a health-literacy and risk-awareness prototype.

Risk scoring is heuristic but transparent, based on:

   - Heat index thresholds inspired by NOAA

   - AQI and pollutant ranges

   - Age and general vulnerability patterns

   - The LLM component is purely explanatory, not diagnostic.

   - All health-related inputs remain local when running with a local Ollama LLM.