from datetime import datetime
from typing import List, Optional, Dict, Any


from pydantic import BaseModel


class Location(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = None


class Profile(BaseModel):
    age: Optional[int] = None
    conditions: List[str] = [] 


class HealthRiskRequest(BaseModel):
    location: Optional[Location] = None
    city: Optional[str] = None
    profile: Optional[Profile] = None


class RawWeather(BaseModel):
    temperature_c: float
    humidity: float
    heat_index_c: float


class RawAirQuality(BaseModel):
    aqi: int
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    o3: Optional[float] = None

class RiskScore(BaseModel):
    level: str
    score: int

class Scores(BaseModel):
    asthma_risk: RiskScore
    heat_risk: RiskScore
    dehydration_risk: RiskScore           
    overall_risk: RiskScore

class ForecastPoint(BaseModel):
    time: datetime
    asthma_risk_level: str
    heat_risk_level: str
    overall_risk_score: int


class LLMExplanation(BaseModel):
    summary: str
    details: str
    actions: List[str]
    profile_specific_note: Optional[str] = None


# ---------- "Today's Risk Summary" ----------

class RiskSummary(BaseModel):
    overall_level: str
    overall_score: int
    asthma_level: str
    heat_level: str
    dehydration_level: str      
    rating: str
    message: str


# ---------- "Contributing Factors" (pie charts) ----------

class FactorContribution(BaseModel):
    factor: str                 # e.g. "PM2.5", "Ozone", "Profile (asthma)"
    percentage: float           # e.g. 40.0 (meaning 40%)


class ContributingFactors(BaseModel):
    asthma: List[FactorContribution]
    heat: List[FactorContribution]
    dehydration: List[FactorContribution]


# ---------- "Personal Health Checklist" ----------

class ChecklistItem(BaseModel):
    text: str


class HealthRiskResponse(BaseModel):
    location: Location
    timestamp: datetime
    raw_data: Dict[str, Any]            # Environmental Snapshot
    scores: Scores                      # Base risk scores
    forecast: List[ForecastPoint]      
    llm_explanation: LLMExplanation     

    # high-level fields:
    risk_summary: RiskSummary
    contributing_factors: ContributingFactors
    checklist: List[ChecklistItem]
