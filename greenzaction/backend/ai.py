import os
import requests
from collections import defaultdict


def build_insights(transactions):
    by_category = defaultdict(lambda: {"emissions": 0, "spend": 0, "count": 0})
    for t in transactions:
        c = t.get("category", "Shopping")
        by_category[c]["emissions"] += float(t.get("emissions_kg", 0))
        by_category[c]["spend"] += float(t.get("amount", 0))
        by_category[c]["count"] += 1
    return sorted(({"category": k, **v} for k, v in by_category.items()), key=lambda x: x["emissions"], reverse=True)


def fallback_recommendations(transactions):
    ranked = build_insights(transactions)
    if not ranked:
        return [{"title": "Start with one transaction", "body": "Log a purchase to reveal the categories and choices shaping your footprint.", "priority": "low"}]
    top = ranked[0]
    suggestions = []
    if top["category"] in ("Fuel", "Transportation", "Travel"):
        suggestions.append({"title": "Make your next route lighter", "body": f"{top['category']} is your highest estimated emissions category at {top['emissions']:.1f} kg CO₂e. Try public transport, carpooling, or combining errands where practical.", "priority": "high"})
    elif top["category"] in ("Clothing", "Shopping"):
        suggestions.append({"title": "Pause before the next purchase", "body": f"Your {top['category'].lower()} spending is the largest estimated footprint. Consider repair, refill, reuse, or a lower-impact alternative.", "priority": "high"})
    else:
        suggestions.append({"title": "Keep the low-carbon rhythm", "body": f"{top['category']} contributes the most estimated emissions. Look for reusable products and lower-emission options next time.", "priority": "medium"})
    eco = sum(1 for t in transactions if t.get("rating") in ("A", "B"))
    suggestions.append({"title": "Grow your A/B streak", "body": f"{eco} of {len(transactions)} logged purchases currently rate A or B. Small repeatable choices are what move your Green Score.", "priority": "medium"})
    suggestions.append({"title": "Treat every number as an estimate", "body": "Greenzaction uses category activity proxies when product-level lifecycle data is unavailable. Use the trend to guide decisions, not as a precise audit.", "priority": "low"})
    return suggestions


def gemini_recommendations(transactions):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key: return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    summary = [{"merchant": t.get("merchant"), "category": t.get("category"), "amount": t.get("amount"), "emissions_kg": t.get("emissions_kg"), "rating": t.get("rating")} for t in transactions[-40:]]
    prompt = "You are a careful sustainability coach. Based only on this user's transaction summary, return 3 concise JSON objects with title, body, priority. Never invent stats and mention estimates where relevant. Data: " + str(summary)
    try:
        response = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}", json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=8)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        # Keep provider output optional and safe; fallback remains the reliable path.
        import json
        parsed = json.loads(text.strip().replace("```json", "").replace("```", ""))
        if isinstance(parsed, list): return parsed[:3]
    except Exception:
        return None
    return None


def answer_question(question, metrics, transactions):
    q = question.lower()
    ranked = build_insights(transactions)
    top = ranked[0]["category"] if ranked else "not enough data"
    if "total carbon" in q or "footprint" in q or "emission" in q:
        return f"Your current estimated footprint is {metrics['total_emissions']:.1f} kg CO₂e across {metrics['transaction_count']} transactions. These are category-based estimates, not a product-level audit."
    if "most" in q or "category" in q or "highest" in q:
        return f"{top} is your highest estimated-emissions category based on the transactions currently in your account."
    if "month" in q or "spent" in q or "spend" in q:
        return f"You have spent ₹{metrics['total_spending']:,.0f} across the transactions in the selected period."
    if "score" in q or "rating" in q:
        return f"Your current Green Score is {metrics['green_score']:.0f}/100 with a {metrics['rating']} carbon rating."
    if "point" in q or "reward" in q:
        return f"You have earned {metrics['reward_points']} Green Points so far."
    return f"To reduce your footprint, start with {top.lower() if ranked else 'one high-frequency category'}: choose lower-emission alternatives where practical, and keep using the trend as an estimate rather than a precise audit."
