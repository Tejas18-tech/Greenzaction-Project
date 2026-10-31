from datetime import datetime

# These are category proxies for an estimate, not product-level LCAs. Activity is
# derived from a spend-to-activity proxy and then multiplied by the factor.
FACTORS = {
    "Food & groceries": {"unit": "kg food-equivalent", "proxy": 420.0, "factor": 2.4, "source": "UK DEFRA/GHG Conversion Factors and category proxy", "confidence": "medium"},
    "Transportation": {"unit": "passenger-km", "proxy": 28.0, "factor": 0.17, "source": "US EPA passenger travel factors and category proxy", "confidence": "medium"},
    "Fuel": {"unit": "litre-equivalent", "proxy": 105.0, "factor": 2.31, "source": "UK DEFRA fuel combustion factors and category proxy", "confidence": "medium"},
    "Clothing": {"unit": "garment-equivalent", "proxy": 1800.0, "factor": 8.0, "source": "European Environment Agency textile lifecycle ranges and category proxy", "confidence": "low"},
    "Electronics": {"unit": "device-equivalent", "proxy": 15000.0, "factor": 45.0, "source": "IEA/European Environment Agency electronics lifecycle ranges and category proxy", "confidence": "low"},
    "Shopping": {"unit": "purchase-equivalent", "proxy": 850.0, "factor": 1.2, "source": "UK DEFRA household goods category ranges and category proxy", "confidence": "low"},
    "Utilities": {"unit": "kWh-equivalent", "proxy": 9.5, "factor": 0.42, "source": "IEA electricity intensity reference and category proxy", "confidence": "medium"},
    "Travel": {"unit": "passenger-km", "proxy": 75.0, "factor": 0.25, "source": "UK DEFRA travel factors and category proxy", "confidence": "medium"},
}
CATEGORIES = list(FACTORS.keys())
PAYMENT_METHODS = ["UPI", "Card", "Wallet"]


def calculate_carbon(amount, category, description=""):
    factor = FACTORS.get(category, FACTORS["Shopping"])
    # Currency amount is only used as an activity proxy. It is explicitly not a
    # physical measurement and is shown as an estimate in the product.
    activity = max(float(amount), 0) / factor["proxy"]
    kg = round(activity * factor["factor"], 3)
    rating = rating_for(kg, category)
    score = score_for(kg, category)
    return {
        "activity_data": round(activity, 3),
        "activity_unit": factor["unit"],
        "emission_factor": factor["factor"],
        "emissions_kg": kg,
        "rating": rating,
        "score_contribution": score,
        "factor_source": factor["source"],
        "calculation_method": "Category spend proxy → estimated activity × published category factor",
        "confidence": factor["confidence"],
        "is_estimate": True,
        "calculated_at": datetime.utcnow().isoformat() + "Z",
    }


def rating_for(kg, category):
    # Category-aware bands keep expensive travel/device purchases from being
    # compared as though they were groceries.
    bands = {"Fuel": (2, 8, 18, 35), "Transportation": (0.8, 2.5, 6, 12), "Travel": (1.2, 4, 10, 20), "Electronics": (8, 25, 60, 110)}
    a, b, c, d = bands.get(category, (1.5, 4, 9, 18))
    if kg <= a: return "A"
    if kg <= b: return "B"
    if kg <= c: return "C"
    if kg <= d: return "D"
    return "E"


def score_for(kg, category):
    caps = {"Fuel": 40, "Travel": 32, "Electronics": 35, "Clothing": 28, "Transportation": 22}
    cap = caps.get(category, 20)
    return max(0, round(100 - min(kg / cap * 100, 100), 1))


def aggregate_score(transactions):
    if not transactions:
        return {"score": 0, "rating": "—", "eco_percentage": 0}
    emissions = sum(float(t.get("emissions_kg", 0)) for t in transactions)
    score = max(0, min(100, round(100 - (emissions / max(len(transactions), 1)) * 5, 1)))
    rating = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D" if score >= 30 else "E"
    eco = round(sum(1 for t in transactions if t.get("rating") in ("A", "B")) / len(transactions) * 100)
    return {"score": score, "rating": rating, "eco_percentage": eco}


def reward_for(transaction):
    rating = transaction.get("rating")
    points = {"A": 40, "B": 24, "C": 8, "D": 0, "E": 0}.get(rating, 0)
    return {"points": points, "reason": f"{rating}-rated purchase"} if points else None
