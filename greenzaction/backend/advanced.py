import math
from collections import defaultdict
from datetime import datetime

try:
    import pandas as pd
    import numpy as np
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error
except Exception:
    pd = np = LinearRegression = None
    mean_absolute_error = mean_squared_error = None

PRODUCTS = [
    {"id": "organic-basket", "name": "Organic grocery basket", "category": "Food & groceries", "keywords": ["green basket", "organic", "groceries", "food"], "phases": {"manufacturing": 1.2, "transportation": 0.4, "packaging": 0.2, "usage": 0.0}, "unit": "basket", "repairability": 0, "energy_efficiency": 60, "refurbished": False},
    {"id": "metro-pass", "name": "Public transport journey", "category": "Transportation", "keywords": ["metro", "bus", "transport", "commute"], "phases": {"manufacturing": 0.02, "transportation": 0.18, "packaging": 0.0, "usage": 0.0}, "unit": "journey", "repairability": 0, "energy_efficiency": 90, "refurbished": False},
    {"id": "efficient-laptop", "name": "Energy-efficient laptop", "category": "Electronics", "keywords": ["laptop", "computer", "notebook"], "phases": {"manufacturing": 48.0, "transportation": 3.5, "packaging": 1.4, "usage": 12.0}, "unit": "device", "repairability": 78, "energy_efficiency": 88, "refurbished": False},
    {"id": "refurbished-laptop", "name": "Refurbished laptop", "category": "Electronics", "keywords": ["refurbished laptop", "renewed laptop", "used laptop"], "phases": {"manufacturing": 12.0, "transportation": 2.8, "packaging": 1.0, "usage": 12.0}, "unit": "device", "repairability": 82, "energy_efficiency": 84, "refurbished": True},
    {"id": "repairable-tee", "name": "Repairable organic cotton tee", "category": "Clothing", "keywords": ["tee", "shirt", "clothing", "threads"], "phases": {"manufacturing": 5.8, "transportation": 0.9, "packaging": 0.3, "usage": 1.2}, "unit": "garment", "repairability": 72, "energy_efficiency": 42, "refurbished": False},
    {"id": "refill-cleaner", "name": "Refill household cleaner", "category": "Shopping", "keywords": ["refill", "cleaner", "household"], "phases": {"manufacturing": 0.4, "transportation": 0.2, "packaging": 0.05, "usage": 0.0}, "unit": "refill", "repairability": 0, "energy_efficiency": 70, "refurbished": False},
]

MERCHANTS = [
    {"id": "refillery", "name": "Refillery Collective", "type": "Refill & household", "city": "Bengaluru", "signal": "Refill-first essentials", "source_url": "https://en.wikipedia.org/wiki/Refill_(packaging)", "tags": ["refill", "low packaging", "household"]},
    {"id": "repair-cafe", "name": "Repair Café Network", "type": "Repair services", "city": "Mumbai", "signal": "Repair before replace", "source_url": "https://repaircafe.org/en/", "tags": ["repair", "circular economy"]},
    {"id": "transit-market", "name": "Transit Market", "type": "Public transport", "city": "Delhi", "signal": "Lower-emission mobility", "source_url": "https://www.iea.org/topics/transport", "tags": ["mobility", "public transport"]},
    {"id": "renewed-tech", "name": "Renewed Tech Hub", "type": "Refurbished electronics", "city": "Hyderabad", "signal": "Extend device life", "source_url": "https://www.ellenmacarthurfoundation.org/topics/electronics/overview", "tags": ["refurbished", "repairability"]},
]


def _total(phases): return round(sum(float(v) for v in phases.values()), 3)


def identify_product(merchant="", description="", category="Shopping"):
    text = f"{merchant} {description}".lower()
    matches = [p for p in PRODUCTS if any(keyword in text for keyword in p["keywords"])]
    if matches: return max(matches, key=lambda p: max((len(keyword) for keyword in p["keywords"] if keyword in text), default=0))
    category_matches = [p for p in PRODUCTS if p["category"] == category]
    return category_matches[0] if category_matches else {"id": "category-estimate", "name": f"{category} category estimate", "category": category, "phases": {"manufacturing": 0, "transportation": 0, "packaging": 0, "usage": 0}, "unit": "unit", "repairability": 0, "energy_efficiency": 0, "refurbished": False}


def analyze_product(merchant, description, category, amount, quantity=1, unit=None):
    product = identify_product(merchant, description, category)
    quantity = max(float(quantity or 1), 0.1)
    if product["id"] == "category-estimate":
        return {"product_id": product["id"], "product_name": product["name"], "quantity": quantity, "unit": unit or product["unit"], "lifecycle": {"manufacturing": 0, "transportation": 0, "packaging": 0, "usage": 0}, "product_emissions_kg": None, "product_confidence": "low", "product_source": "No product-level match; category estimate retained", "verified": False}
    lifecycle = {key: round(value * quantity, 3) for key, value in product["phases"].items()}
    return {"product_id": product["id"], "product_name": product["name"], "quantity": quantity, "unit": unit or product["unit"], "lifecycle": lifecycle, "product_emissions_kg": _total(lifecycle), "product_confidence": "medium", "product_source": "Curated product profile with lifecycle boundary by phase", "verified": False, "repairability": product["repairability"], "energy_efficiency": product["energy_efficiency"], "refurbished": product["refurbished"]}


def search_products(query="", category=""):
    query = query.lower().strip()
    rows = [p for p in PRODUCTS if (not category or p["category"] == category) and (not query or query in (p["name"] + " " + p["category"] + " " + " ".join(p["keywords"])).lower())]
    return [{**p, "emissions_kg": _total(p["phases"]), "reason": "Lower lifecycle estimate, repairability, or energy performance"} for p in rows]


def compare_products(query="laptop", quantity=1):
    rows = search_products(query)
    if not rows: rows = search_products("laptop")
    normalized = []
    for item in rows:
        phases = {k: round(v * float(quantity or 1), 3) for k, v in item["phases"].items()}
        normalized.append({"id": item["id"], "name": item["name"], "category": item["category"], "emissions_kg": _total(phases), "lifecycle": phases, "repairability": item["repairability"], "energy_efficiency": item["energy_efficiency"], "refurbished": item["refurbished"], "reason": "Refurbished option prioritizes avoided manufacturing; efficient option prioritizes energy performance."})
    baseline = max((x["emissions_kg"] for x in normalized), default=0)
    for item in normalized: item["savings_kg"] = round(max(0, baseline - item["emissions_kg"]), 3)
    return sorted(normalized, key=lambda x: x["emissions_kg"])


def predict_emissions(transactions):
    monthly = defaultdict(float)
    for t in transactions: monthly[str(t.get("date", ""))[:7]] += float(t.get("emissions_kg", 0))
    series = sorted((m, round(v, 3)) for m, v in monthly.items() if m)
    if len(series) < 3:
        return {"status": "insufficient_data", "message": "Add transactions across at least three months to generate a responsible forecast.", "confidence": 0, "next_month_kg": None, "mae": None, "rmse": None, "history": [{"month": m, "emissions": v} for m, v in series], "rising_categories": []}
    frame = pd.DataFrame(series, columns=["month", "emissions"]) if pd is not None else None
    values = frame["emissions"].astype(float).tolist() if frame is not None else [v for _, v in series]
    x = list(range(len(values)))
    if LinearRegression is not None:
        model = LinearRegression().fit([[i] for i in x], values)
        predicted = max(0, float(model.predict([[len(values)]])[0]))
        fitted = model.predict([[i] for i in x])
        mae = float(mean_absolute_error(values, fitted))
        rmse = float(math.sqrt(mean_squared_error(values, fitted)))
    else:
        slope = (values[-1] - values[0]) / max(len(values) - 1, 1)
        predicted = max(0, values[-1] + slope)
        errors = [abs(values[i] - (values[0] + slope * i)) for i in x]
        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    confidence = max(35, min(92, round(92 - (rmse / max(sum(values) / len(values), 1)) * 100)))
    category_month = defaultdict(list)
    for t in transactions: category_month[t.get("category", "Shopping")].append((str(t.get("date", ""))[:7], float(t.get("emissions_kg", 0))))
    rising = []
    for category, points in category_month.items():
        ordered = sorted(points)
        if len(ordered) >= 2 and ordered[-1][1] > ordered[-2][1]: rising.append(category)
    return {"status": "ready", "next_month_kg": round(predicted, 2), "confidence": confidence, "mae": round(mae, 2), "rmse": round(rmse, 2), "history": [{"month": m, "emissions": v} for m, v in series], "rising_categories": rising, "method": "LinearRegression over monthly authenticated transaction emissions"}


def budget_status(transactions, budget=None):
    month = datetime.utcnow().strftime("%Y-%m")
    consumed = round(sum(float(t.get("emissions_kg", 0)) for t in transactions if str(t.get("date", "")).startswith(month)), 2)
    target = float((budget or {}).get("monthly_limit_kg", 50))
    remaining = round(target - consumed, 2)
    utilization = round(consumed / target * 100, 1) if target else 0
    return {"monthly_limit_kg": target, "consumed_kg": consumed, "remaining_kg": remaining, "utilization": utilization, "alert": utilization >= 80, "month": month}


def challenges(transactions, points=0):
    a_b = sum(1 for t in transactions if t.get("rating") in ("A", "B"))
    return [{"id": "lighter-week", "title": "Three lighter choices", "description": "Make three A or B-rated purchases this month.", "progress": min(a_b, 3), "target": 3, "reward": 80, "complete": a_b >= 3}, {"id": "repair-first", "title": "Repair-first mindset", "description": "Log one repair, refill, or refurbished choice.", "progress": min(sum(1 for t in transactions if t.get("product_id") in ("refill-cleaner", "refurbished-laptop", "repairable-tee")), 1), "target": 1, "reward": 100, "complete": any(t.get("product_id") in ("refill-cleaner", "refurbished-laptop", "repairable-tee") for t in transactions)}, {"id": "budget-aware", "title": "Stay budget-aware", "description": "Set a carbon budget and keep utilization under 80%.", "progress": 1 if points >= 1 else 0, "target": 1, "reward": 60, "complete": points >= 1}]
