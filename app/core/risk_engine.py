import math
from typing import Optional

from app.models.schemas import Profile, Scores, RiskScore
from app.models.schemas import ContributingFactors, FactorContribution, RawWeather, RawAirQuality


def compute_heat_index_c(temp_c: float, humidity: float) -> float:
    """
    Compute heat index in Celsius using standard NOAA formula.
    Input temp in Celsius, humidity in %.
    """

    # Convert C to F
    T = temp_c * 9 / 5 + 32
    R = humidity

    # Simple shortcut for lower temps
    if T < 80:
        hi_f = T
    else:
        # NOAA / Rothfusz regression
        hi_f = (
            -42.379
            + 2.04901523 * T
            + 10.14333127 * R
            - 0.22475541 * T * R
            - 0.00683783 * T * T
            - 0.05481717 * R * R
            + 0.00122874 * T * T * R
            + 0.00085282 * T * R * R
            - 0.00000199 * T * T * R * R
        )

        # Adjustments for low humidity / high humidity ranges
        if R < 13 and 80 <= T <= 112:
            hi_f -= ((13 - R) / 4) * math.sqrt((17 - abs(T - 95)) / 17)
        elif R > 85 and 80 <= T <= 87:
            hi_f += ((R - 85) / 10) * ((87 - T) / 5)

    # Back to C
    return (hi_f - 32) * 5 / 9


def score_air_pollution(aqi: int, pm25: Optional[float], o3: Optional[float]) -> int:
    """
    Map OpenWeather AQI (1-5) to 0-5 score.
    Optionally bump for high PM2.5 / O3.
    """
    base_map = {1: 0, 2: 1, 3: 2, 4: 4, 5: 5}
    score = base_map.get(aqi, 0)

    if pm25 is not None and pm25 > 35:  # µg/m3
        score = min(5, score + 1)
    if o3 is not None and o3 > 100:  # rough threshold
        score = min(5, score + 1)

    return score


def score_heat(heat_index_c: float) -> int:
    """
    Map heat index to 0-5 risk score.
    Thresholds roughly aligned with NOAA categories.
    """
    hi_f = heat_index_c * 9 / 5 + 32

    if hi_f < 80:
        return 0
    elif 80 <= hi_f < 90:
        return 2
    elif 90 <= hi_f < 103:
        return 3
    elif 103 <= hi_f < 125:
        return 4
    else:
        return 5


def level_from_score(score: int) -> str:
    # Convert 0–5 internal into Low/Moderate/High/Very High (1–4 levels)
    if score <= 1:
        return "Low"
    if score == 2:
        return "Moderate"
    if score == 3:
        return "High"
    return "Very High"


def compute_dehydration_risk(
    temperature_c: float,
    humidity: float,
    heat_index_c: float,
    age: Optional[int] = None,
) -> RiskScore:
    """
    Simple dehydration risk model:
    - driven mainly by heat index
    - extra bump for older adults (>= 65)
    """
    s = 1  # base = Low

    # Base on heat index
    if heat_index_c >= 27:   # ~80°F
        s = 2
    if heat_index_c >= 32:   # ~90°F
        s = 3
    if heat_index_c >= 38:   # ~100°F
        s = 4

    # Slight bump if humidity is high 
    if humidity >= 70 and s < 4:
        s += 1

    # Extra vulnerability for older adults
    if age is not None and age >= 65 and s < 4:
        s += 1

    s = max(1, min(int(s), 4))
    return RiskScore(level=level_from_score(s), score=s)


def compute_overall_risk(
    asthma_score: int,
    heat_score: int,
    dehydration_score: int,
) -> RiskScore:
    """
    Combine the three dimensions into one overall score.
    Weights can be tuned; here heat+dehydration count a bit more.
    """
    weighted = (
        asthma_score * 0.3 +
        heat_score * 0.35 +
        dehydration_score * 0.35
    )
    avg_score = round(weighted)

    avg_score = max(1, min(int(avg_score), 4))
    return RiskScore(level=level_from_score(avg_score), score=avg_score)


def combine_scores(
    air_score: int,
    heat_score: int,
    temperature_c: float,
    humidity: float,
    heat_index_c: float,
    profile: Optional[Profile] = None,
) -> Scores:
    """
    Main orchestrator:
    - build asthma_risk from air_score
    - build heat_risk from heat_score (+ profile sensitivity)
    - build dehydration_risk from heat index + humidity + age
    - compute overall_risk
    """
    asthma_score = air_score
    heat_score_final = heat_score

    at_risk = False
    age: Optional[int] = None

    if profile:
        age = profile.age
        if age is not None and age >= 65:
            at_risk = True

        lower = [c.lower() for c in profile.conditions]
        resp_keywords = ["asthma", "copd", "bronchitis", "respiratory"]
        cardio_keywords = ["heart", "cardio", "hypertension", "cardiovascular"]
        if any(k in " ".join(lower) for k in resp_keywords + cardio_keywords):
            at_risk = True

    if at_risk:
        asthma_score = min(5, asthma_score + 1)
        heat_score_final = min(5, heat_score_final + 1)

    # Build individual risk scores
    asthma_risk = RiskScore(
        level=level_from_score(asthma_score),
        score=asthma_score,
    )
    heat_risk = RiskScore(
        level=level_from_score(heat_score_final),
        score=heat_score_final,
    )

    dehydration_risk = compute_dehydration_risk(
        temperature_c=temperature_c,
        humidity=humidity,
        heat_index_c=heat_index_c,
        age=age,
    )

    overall_risk = compute_overall_risk(
        asthma_score=asthma_risk.score,
        heat_score=heat_risk.score,
        dehydration_score=dehydration_risk.score,
    )

    return Scores(
        asthma_risk=asthma_risk,
        heat_risk=heat_risk,
        dehydration_risk=dehydration_risk,
        overall_risk=overall_risk,
    )

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def build_contributing_factors(
    raw_weather: RawWeather,
    raw_air: RawAirQuality,
    profile: Optional[Profile],
    scores: Scores,
) -> ContributingFactors:
    """
    Build simple data-driven factor percentages for the donut charts.
    Not medically exact, just a transparent heuristic for the UI.
    """

    # ----- Asthma / respiratory -----
    # Signals: PM2.5, ozone, profile (if resp/heart conditions or older)
    pm25 = raw_air.pm25 or 0.0
    o3 = raw_air.o3 or 0.0

    s_pm25 = _clamp01(pm25 / 60.0)      # 0–60 µg/m3
    s_o3 = _clamp01(o3 / 150.0)         # 0–150 µg/m3

    profile_asthma = 0.2
    if profile:
        has_resp = any(
            k in " ".join(c.lower() for c in profile.conditions)
            for k in ["asthma", "copd", "bronchitis", "respiratory"]
        )
        if has_resp or (profile.age and profile.age >= 65):
            profile_asthma = 1.0

    total_a = s_pm25 + s_o3 + profile_asthma or 1.0
    asthma_factors = [
        FactorContribution(factor="PM2.5", percentage=round(s_pm25 / total_a * 100, 1)),
        FactorContribution(factor="Ozone (O3)", percentage=round(s_o3 / total_a * 100, 1)),
        FactorContribution(
            factor="Profile (asthma/age)",
            percentage=round(profile_asthma / total_a * 100, 1),
        ),
    ]

    # ----- Heat -----
    hi = raw_weather.heat_index_c
    humidity = raw_weather.humidity

    s_hi = _clamp01((hi - 27.0) / (40.0 - 27.0))         # ~80–104°F
    s_hum = _clamp01((humidity - 40.0) / 50.0)           # 40–90%

    profile_heat = 0.2
    if profile:
        has_heart = any(
            k in " ".join(c.lower() for c in profile.conditions)
            for k in ["heart", "cardio", "hypertension", "cardiovascular"]
        )
        if has_heart or (profile.age and profile.age >= 65):
            profile_heat = 1.0

    total_h = s_hi + s_hum + profile_heat or 1.0
    heat_factors = [
        FactorContribution(
            factor="Heat Index", percentage=round(s_hi / total_h * 100, 1)
        ),
        FactorContribution(
            factor="Humidity", percentage=round(s_hum / total_h * 100, 1)
        ),
        FactorContribution(
            factor="Profile (age/heart/resp.)",
            percentage=round(profile_heat / total_h * 100, 1),
        ),
    ]

    # ----- Dehydration -----
    # Signals: heat index, humidity, age
    age = profile.age if profile and profile.age is not None else 30
    s_hi_d = _clamp01((hi - 27.0) / (40.0 - 27.0))
    s_hum_d = _clamp01((humidity - 50.0) / 40.0)         # 50–90%
    s_age = _clamp01((age - 40) / 30.0)                  # 40–70+

    total_d = s_hi_d + s_hum_d + s_age or 1.0
    dehydration_factors = [
        FactorContribution(
            factor="Heat Index", percentage=round(s_hi_d / total_d * 100, 1)
        ),
        FactorContribution(
            factor="Humidity", percentage=round(s_hum_d / total_d * 100, 1)
        ),
        FactorContribution(factor="Age (65+)", percentage=round(s_age / total_d * 100, 1)),
    ]

    return ContributingFactors(
        asthma=asthma_factors,
        heat=heat_factors,
        dehydration=dehydration_factors,
    )
