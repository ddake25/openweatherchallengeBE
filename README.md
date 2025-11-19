# Weather-Driven Health Risk API (Backend)

## Problem This API Addresses
- Climate change is increasing extreme heat, pollution, and humidity spikes.
- Most weather apps only show temperature and AQI — they do **not**:
  - Translate conditions into **health risks**
  - Adapt to **age** or **chronic conditions**
  - Explain the **“why”** behind the risk
- This API converts **raw weather + air-quality data** into **structured, explainable health-risk insights**.

## What the Backend Does
- Uses **OpenWeather** (geocoding, current weather, hourly forecast).
- Uses **OpenWeather Air Pollution API** for AQI, PM2.5, PM10, O₃.
- Computes:
  - Asthma / respiratory risk score
  - Heat stress risk score
  - Dehydration risk score
  - Combined overall risk score (0–4) + letter rating (A–E)
- Generates a **24-hour risk outlook**
- Calls **Ollama** (local LLM) to convert numbers into:
  - Plain-language summary
  - Detailed explanation
  - Actionable checklist items
  - Profile-specific note (age/conditions)
- Returns structured JSON for frontend
- Optional MongoDB logging

## High-Level Architecture
- FastAPI backend  
- OpenWeather (weather + air quality)  
- Risk Engine (NOAA heat index, pollutant thresholds, age modifiers)  
- Local LLM (Ollama) for explanation JSON  
- Optional MongoDB logging  
- Frontend in separate repo

**Flow:**  
Input city → fetch weather/air → risk scoring → LLM explanation → JSON → UI

## Risk Model (Summary)
- **Heat Index:** NOAA formula  
- **Asthma Risk:** AQI, PM2.5, PM10, O₃  
- **Heat Stress Risk:** heat index + humidity  
- **Dehydration Risk:** heat index + humidity + **age**  
- Overall score mapped to **A–E** ratings  

## Privacy & Design Principles
- No personal identity needed  
- Stateless by default  

## Tech Stack
- Python  
- FastAPI  
- httpx / requests  
- Ollama  
- Optional MongoDB  


## Setup & Installation

### 1. Create and activate Conda environment

- conda create -n weatherhealth python=3.11 -y
- conda activate weatherhealth

### 2. Install Python dependencies
- pip install fastapi uvicorn[standard] httpx motor pydantic pydantic-settings python-dotenv
                                    or
- pip install -r requirements.txt

### 3. Configure environment variables
- openweather_api_key=YOUR_OPENWEATHER_KEY
- mongo_uri=mongodb://localhost:27017  # MongoDB connection (optional; used for logging).
- mongo_db=weather_health

- ollama_base_url=http://localhost:11434 # url to your ollama server
- ollama_model=phi4-mini # or any local model you have pulled (e.g. llama3).

### 4. Start Ollama locally
- ollama run phi4-mini

### 5. Run the FastAPI server
- uvicorn app.main:app --reload

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

- This is not a medical device. It is a health-literacy and risk-awareness prototype.

- Risk scoring is heuristic but transparent, based on:

   - Heat index thresholds inspired by NOAA

   - AQI and pollutant ranges

   - Age and general vulnerability patterns

   - The LLM component is purely explanatory, not diagnostic.

   - All health-related inputs remain local when running with a local Ollama LLM.