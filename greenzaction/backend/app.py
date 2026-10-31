import csv
import io
import os
from collections import defaultdict
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, g, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

from backend.store import DataStore, now
from backend.auth import create_token, jwt_required, admin_required
from backend.carbon import CATEGORIES, PAYMENT_METHODS, calculate_carbon, aggregate_score, reward_for, rating_for, score_for, FACTORS
from backend.ai import fallback_recommendations, gemini_recommendations, answer_question, build_insights
from backend.advanced import analyze_product, search_products, compare_products, predict_emissions, budget_status, challenges, MERCHANTS

load_dotenv()
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../dist"))
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config["JSON_SORT_KEYS"] = False
store = DataStore()
app.store = store

@app.before_request
def bind_store(): g.store = store

@app.get("/api/health")
def health(): return jsonify({"ok": True, "service": "greenzaction-api", "database": store.mode})


def public_user(user):
    return {"id": user["id"], "name": user.get("name", "Member"), "email": user["email"], "role": user.get("role", "user"), "created_at": user.get("created_at")}


def metrics_for(user_id, transactions=None):
    transactions = transactions if transactions is not None else store.all_for_user("transactions", user_id)
    total_spending = sum(float(t.get("amount", 0)) for t in transactions)
    total_emissions = sum(float(t.get("emissions_kg", 0)) for t in transactions)
    score = aggregate_score(transactions)
    points = sum(int(x.get("points", 0)) for x in store.find_many("reward_ledger", {"user_id": user_id}))
    by_category = defaultdict(lambda: {"emissions": 0, "spend": 0, "count": 0})
    by_month = defaultdict(float)
    for t in transactions:
        cat = t.get("category", "Shopping")
        by_category[cat]["emissions"] += float(t.get("emissions_kg", 0))
        by_category[cat]["spend"] += float(t.get("amount", 0))
        by_category[cat]["count"] += 1
        by_month[str(t.get("date", ""))[:7]] += float(t.get("emissions_kg", 0))
    return {"total_spending": round(total_spending, 2), "total_emissions": round(total_emissions, 2), "green_score": score["score"], "rating": score["rating"], "eco_percentage": score["eco_percentage"], "reward_points": points, "transaction_count": len(transactions), "category_emissions": [{"category": k, **v, "emissions": round(v["emissions"], 2), "spend": round(v["spend"], 2)} for k, v in sorted(by_category.items(), key=lambda x: x[1]["emissions"], reverse=True)], "monthly_emissions": [{"month": k, "emissions": round(v, 2)} for k, v in sorted(by_month.items())]}


def validate_transaction(payload):
    errors = []
    if not str(payload.get("merchant", "")).strip(): errors.append("Merchant name is required")
    try:
        if float(payload.get("amount", 0)) <= 0: errors.append("Amount must be greater than zero")
    except Exception: errors.append("Amount must be a number")
    if payload.get("category") not in CATEGORIES: errors.append("Choose a supported category")
    if payload.get("payment_method") not in PAYMENT_METHODS: errors.append("Choose UPI, Card or Wallet")
    if not payload.get("date"): errors.append("Date is required")
    return errors


def process_transaction(user_id, payload, existing=None):
    data = {"merchant": str(payload.get("merchant", "")).strip(), "amount": round(float(payload.get("amount", 0)), 2), "date": payload.get("date"), "category": payload.get("category"), "payment_method": payload.get("payment_method"), "description": str(payload.get("description", "")).strip(), "quantity": max(float(payload.get("quantity", 1) or 1), 0.1), "unit": str(payload.get("unit", "unit")), "user_id": user_id, "updated_at": now()}
    calc = calculate_carbon(data["amount"], data["category"], data["description"])
    data.update(calc)
    product = analyze_product(data["merchant"], data["description"], data["category"], data["amount"], data["quantity"], data["unit"])
    data.update(product)
    if product.get("product_emissions_kg") is not None:
        data["emissions_kg"] = product["product_emissions_kg"]
        data["rating"] = rating_for(data["emissions_kg"], data["category"])
        data["score_contribution"] = score_for(data["emissions_kg"], data["category"])
        data["confidence"] = product.get("product_confidence", data.get("confidence"))
        data["calculation_method"] = "Product lifecycle profile: manufacturing + transportation + packaging + usage"
    if existing:
        data["id"] = existing["id"]
        result = store.update("transactions", {"id": existing["id"], "user_id": user_id}, data)
        store.update("carbon_calculations", {"transaction_id": existing["id"]}, {"transaction_id": existing["id"], "user_id": user_id, **calc})
        return result or data
    data["created_at"] = now()
    result = store.insert("transactions", data)
    store.insert("carbon_calculations", {"transaction_id": result["id"], "user_id": user_id, **calc})
    reward = reward_for(result)
    if reward and not store.find_one("reward_ledger", {"transaction_id": result["id"]}):
        store.insert("reward_ledger", {"user_id": user_id, "transaction_id": result["id"], "points": reward["points"], "reason": reward["reason"], "created_at": now()})
    transactions = store.all_for_user("transactions", user_id)
    store.update("green_scores", {"user_id": user_id}, {"user_id": user_id, **aggregate_score(transactions), "updated_at": now()}) if store.find_one("green_scores", {"user_id": user_id}) else store.insert("green_scores", {"user_id": user_id, **aggregate_score(transactions), "updated_at": now()})
    return result

@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    name, email, password = str(payload.get("name", "")).strip(), str(payload.get("email", "")).strip().lower(), str(payload.get("password", ""))
    if len(name) < 2 or "@" not in email or len(password) < 8: return jsonify({"error": "Use a name, valid email and password of at least 8 characters"}), 400
    if store.find_one("users", {"email": email}): return jsonify({"error": "An account with this email already exists"}), 409
    user = store.insert("users", {"name": name, "email": email, "password_hash": generate_password_hash(password), "role": "user", "created_at": now()})
    return jsonify({"token": create_token(user), "user": public_user(user)}), 201

@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    user = store.find_one("users", {"email": str(payload.get("email", "")).strip().lower()})
    if not user or not check_password_hash(user.get("password_hash", ""), str(payload.get("password", ""))): return jsonify({"error": "Email or password is incorrect"}), 401
    return jsonify({"token": create_token(user), "user": public_user(user)})

@app.get("/api/auth/me")
@jwt_required
def me(): return jsonify({"user": public_user(g.user)})

@app.put("/api/profile")
@jwt_required
def update_profile():
    payload = request.get_json(silent=True) or {}
    patch = {"name": str(payload.get("name", g.user.get("name", "Member"))).strip()[:80]}
    if payload.get("password"):
        if len(str(payload["password"])) < 8: return jsonify({"error": "Password must be at least 8 characters"}), 400
        patch["password_hash"] = generate_password_hash(payload["password"])
    user = store.update("users", {"id": g.user["id"]}, patch)
    return jsonify({"user": public_user(user)})

@app.get("/api/transactions")
@jwt_required
def transactions():
    query = {"user_id": g.user["id"]}
    search, category, method = request.args.get("q", "").lower(), request.args.get("category"), request.args.get("payment_method")
    rows = store.all_for_user("transactions", g.user["id"])
    if category: rows = [x for x in rows if x.get("category") == category]
    if method: rows = [x for x in rows if x.get("payment_method") == method]
    if search: rows = [x for x in rows if search in f"{x.get('merchant','')} {x.get('description','')}".lower()]
    page, per_page = max(int(request.args.get("page", 1)), 1), min(max(int(request.args.get("per_page", 20)), 1), 100)
    start = (page - 1) * per_page
    return jsonify({"items": rows[start:start + per_page], "total": len(rows), "page": page, "per_page": per_page, "categories": CATEGORIES, "payment_methods": PAYMENT_METHODS})

@app.post("/api/transactions")
@jwt_required
def add_transaction():
    payload = request.get_json(silent=True) or {}
    errors = validate_transaction(payload)
    if errors: return jsonify({"error": "; ".join(errors), "fields": errors}), 400
    return jsonify({"transaction": process_transaction(g.user["id"], payload)}), 201

@app.put("/api/transactions/<transaction_id>")
@jwt_required
def edit_transaction(transaction_id):
    existing = store.find_one("transactions", {"id": transaction_id, "user_id": g.user["id"]})
    if not existing: return jsonify({"error": "Transaction not found"}), 404
    payload = request.get_json(silent=True) or {}
    errors = validate_transaction(payload)
    if errors: return jsonify({"error": "; ".join(errors)}), 400
    return jsonify({"transaction": process_transaction(g.user["id"], payload, existing)})

@app.delete("/api/transactions/<transaction_id>")
@jwt_required
def delete_transaction(transaction_id):
    if not store.delete("transactions", {"id": transaction_id, "user_id": g.user["id"]}): return jsonify({"error": "Transaction not found"}), 404
    store.delete("carbon_calculations", {"transaction_id": transaction_id, "user_id": g.user["id"]})
    store.delete("reward_ledger", {"transaction_id": transaction_id, "user_id": g.user["id"]})
    return jsonify({"ok": True})

@app.post("/api/transactions/import")
@jwt_required
def import_transactions():
    upload = request.files.get("file")
    if not upload: return jsonify({"error": "CSV file is required"}), 400
    reader = csv.DictReader(io.StringIO(upload.stream.read().decode("utf-8-sig")))
    created, errors = 0, []
    for line, row in enumerate(reader, start=2):
        normalized = {"merchant": row.get("merchant") or row.get("merchant_name"), "amount": row.get("amount"), "date": row.get("date"), "category": row.get("category"), "payment_method": row.get("payment_method") or row.get("method"), "description": row.get("description") or row.get("product_description", "")}
        if normalized["category"] not in CATEGORIES: normalized["category"] = "Shopping"
        if normalized["payment_method"] not in PAYMENT_METHODS: normalized["payment_method"] = "Card"
        try:
            if validate_transaction(normalized): raise ValueError("required fields missing")
            process_transaction(g.user["id"], normalized); created += 1
        except Exception as exc: errors.append({"line": line, "error": str(exc)})
    return jsonify({"created": created, "errors": errors})

@app.get("/api/dashboard")
@jwt_required
def dashboard():
    rows = store.all_for_user("transactions", g.user["id"])
    start, end = request.args.get("from"), request.args.get("to")
    if start: rows = [x for x in rows if x.get("date", "") >= start]
    if end: rows = [x for x in rows if x.get("date", "") <= end]
    m = metrics_for(g.user["id"], rows)
    m["recent_transactions"] = rows[:6]
    return jsonify(m)

@app.get("/api/analytics")
@jwt_required
def analytics():
    rows = store.all_for_user("transactions", g.user["id"])
    return jsonify({"metrics": metrics_for(g.user["id"], rows), "insights": build_insights(rows), "methodology": "Activity data is estimated from a category-specific spend proxy and multiplied by a published category factor. Product-level lifecycle data is not available for every transaction."})

@app.get("/api/recommendations")
@jwt_required
def recommendations():
    rows = store.all_for_user("transactions", g.user["id"])
    ai_items = gemini_recommendations(rows)
    items = ai_items or fallback_recommendations(rows)
    source = "gemini" if ai_items else "rule-based"
    store.insert("recommendations", {"user_id": g.user["id"], "items": items, "source": source, "created_at": now()})
    return jsonify({"items": items, "source": source})

@app.get("/api/rewards")
@jwt_required
def rewards():
    ledger = store.find_many("reward_ledger", {"user_id": g.user["id"]}, sort_key="created_at")
    rows = store.all_for_user("transactions", g.user["id"])
    earned = {a["id"]: False for a in store.find_many("achievements")}
    if rows: earned["first-step"] = True
    if sum(1 for x in rows if x.get("rating") in ("A", "B")) >= 5: earned["low-carbon"] = True
    if sum(int(x.get("points", 0)) for x in ledger) >= 100: earned["momentum"] = True
    badges = [{**a, "earned": earned.get(a["id"], False)} for a in store.find_many("achievements")]
    return jsonify({"points": sum(int(x.get("points", 0)) for x in ledger), "ledger": ledger, "badges": badges})

@app.route("/api/goals", methods=["GET", "POST"])
@jwt_required
def goals():
    if request.method == "GET": return jsonify({"items": store.find_many("sustainability_goals", {"user_id": g.user["id"]}, sort_key="created_at")})
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    if not title: return jsonify({"error": "Goal title is required"}), 400
    goal = store.insert("sustainability_goals", {"user_id": g.user["id"], "title": title, "target": payload.get("target", "Make one lower-carbon choice"), "progress": 0, "status": "active", "created_at": now()})
    return jsonify({"goal": goal}), 201

@app.put("/api/goals/<goal_id>")
@jwt_required
def update_goal(goal_id):
    goal = store.find_one("sustainability_goals", {"id": goal_id, "user_id": g.user["id"]})
    if not goal: return jsonify({"error": "Goal not found"}), 404
    progress = min(max(int((request.get_json(silent=True) or {}).get("progress", goal.get("progress", 0))), 0), 100)
    return jsonify({"goal": store.update("sustainability_goals", {"id": goal_id, "user_id": g.user["id"]}, {"progress": progress, "status": "complete" if progress == 100 else "active"})})

@app.post("/api/chatbot")
@jwt_required
def chatbot():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question: return jsonify({"error": "Ask GreenBot a question"}), 400
    rows = store.all_for_user("transactions", g.user["id"])
    metrics = metrics_for(g.user["id"], rows)
    advanced = predict_emissions(rows)
    q = question.lower()
    if "predicted" in q or "next month" in q:
        answer = advanced["message"] if advanced["status"] != "ready" else f"Your predicted next-month footprint is {advanced['next_month_kg']:.1f} kg CO₂e with {advanced['confidence']}% confidence. The model reports MAE {advanced['mae']:.1f} and RMSE {advanced['rmse']:.1f}."
    elif "highest" in q or "purchase" in q and "emission" in q:
        highest = max(rows, key=lambda x: float(x.get("emissions_kg", 0)), default=None)
        answer = f"{highest.get('merchant')} is currently your highest-emissions purchase at {highest.get('emissions_kg', 0):.1f} kg CO₂e." if highest else "You need at least one transaction before I can identify a highest-emissions purchase."
    elif "saved" in q or "last month" in q:
        answer = "Your savings comparison becomes available once there are transactions in two different months. The analytics view will show the month-over-month difference." if len(set(str(x.get("date", ""))[:7] for x in rows)) < 2 else "Your month-over-month carbon savings are shown in Advanced analytics, using only your authenticated transaction history."
    elif "budget" in q:
        answer = f"Your current monthly carbon budget is {budget_status(rows).get('monthly_limit_kg', 50):.0f} kg CO₂e, with {budget_status(rows).get('remaining_kg', 0):.1f} kg remaining."
    elif "replace" in q or "product" in q:
        options = compare_products("laptop")
        answer = f"Start with {options[0]['name']}: its modeled lifecycle estimate is {options[0]['emissions_kg']:.1f} kg CO₂e, potentially {options[0]['savings_kg']:.1f} kg below the highest comparable option."
    else:
        answer = answer_question(question, metrics, rows)
    return jsonify({"answer": answer, "source": "authenticated transaction records and prediction service"})

@app.get("/api/advanced/overview")
@jwt_required
def advanced_overview():
    rows = store.all_for_user("transactions", g.user["id"])
    budget = store.find_one("carbon_budgets", {"user_id": g.user["id"]}) or {"monthly_limit_kg": 50}
    prediction = predict_emissions(rows)
    status = budget_status(rows, budget)
    savings = compare_products("laptop")
    return jsonify({"prediction": prediction, "budget": status, "challenges": challenges(rows, metrics_for(g.user["id"], rows)["reward_points"]), "potential_savings_kg": savings[-1]["emissions_kg"] - savings[0]["emissions_kg"] if len(savings) > 1 else 0, "monthly_report": f"You logged {len(rows)} purchases and an estimated {metrics_for(g.user['id'], rows)['total_emissions']:.1f} kg CO₂e. Focus on {build_insights(rows)[0]['category'] if rows else 'your first category'} next month."})

@app.route("/api/budget", methods=["GET", "PUT"])
@jwt_required
def carbon_budget():
    if request.method == "GET": return jsonify(budget_status(store.all_for_user("transactions", g.user["id"]), store.find_one("carbon_budgets", {"user_id": g.user["id"]})))
    payload = request.get_json(silent=True) or {}
    limit = float(payload.get("monthly_limit_kg", 50))
    if limit <= 0 or limit > 100000: return jsonify({"error": "Choose a monthly carbon limit between 1 and 100000 kg CO₂e"}), 400
    existing = store.find_one("carbon_budgets", {"user_id": g.user["id"]})
    budget = store.update("carbon_budgets", {"user_id": g.user["id"]}, {"monthly_limit_kg": limit, "updated_at": now()}) if existing else store.insert("carbon_budgets", {"user_id": g.user["id"], "monthly_limit_kg": limit, "created_at": now(), "updated_at": now()})
    return jsonify(budget_status(store.all_for_user("transactions", g.user["id"]), budget))

@app.get("/api/products")
@jwt_required
def products(): return jsonify({"items": search_products(request.args.get("q", ""), request.args.get("category", ""))})

@app.post("/api/shopping/compare")
@jwt_required
def shopping_compare():
    payload = request.get_json(silent=True) or {}
    return jsonify({"items": compare_products(str(payload.get("query", "laptop")), payload.get("quantity", 1))})

@app.get("/api/merchants")
@jwt_required
def merchants():
    q = request.args.get("q", "").lower()
    return jsonify({"items": [m for m in MERCHANTS if not q or q in (m["name"] + " " + m["type"] + " " + m["city"] + " " + " ".join(m["tags"])).lower()]})

@app.get("/api/advanced-rewards")
@jwt_required
def advanced_rewards():
    rows = store.all_for_user("transactions", g.user["id"])
    return jsonify({"challenges": challenges(rows, metrics_for(g.user["id"], rows)["reward_points"]), "points": metrics_for(g.user["id"], rows)["reward_points"], "redemptions": store.find_many("reward_ledger", {"user_id": g.user["id"], "kind": "redemption"})})

@app.post("/api/rewards/redeem")
@jwt_required
def redeem_reward():
    payload = request.get_json(silent=True) or {}
    cost = int(payload.get("cost", 100))
    current = metrics_for(g.user["id"])["reward_points"]
    if cost <= 0 or cost > current: return jsonify({"error": "Not enough Green Points for this redemption"}), 400
    entry = store.insert("reward_ledger", {"user_id": g.user["id"], "points": -cost, "reason": str(payload.get("reward", "Sustainability reward")), "kind": "redemption", "created_at": now()})
    return jsonify({"redemption": entry, "remaining_points": current - cost})

@app.get("/api/admin/overview")
@admin_required
def admin_overview():
    users = store.find_many("users")
    transactions = store.find_many("transactions")
    ledger = store.find_many("reward_ledger")
    return jsonify({"users": len(users), "transactions": len(transactions), "emissions": round(sum(float(x.get("emissions_kg", 0)) for x in transactions), 2), "reward_points": sum(int(x.get("points", 0)) for x in ledger), "active_today": len({x.get("user_id") for x in transactions if x.get("date") == datetime.utcnow().date().isoformat()}), "categories": [{"category": c, "transactions": sum(1 for x in transactions if x.get("category") == c), "emissions": round(sum(float(x.get("emissions_kg", 0)) for x in transactions if x.get("category") == c), 2)} for c in CATEGORIES], "recent_users": [public_user(x) for x in users[-8:]]})

@app.get("/api/admin/factors")
@admin_required
def admin_factors(): return jsonify({"items": [{"category": k, **v} for k, v in FACTORS.items()]})

@app.put("/api/admin/factors/<category>")
@admin_required
def admin_factor_update(category):
    payload = request.get_json(silent=True) or {}
    if category not in FACTORS: return jsonify({"error": "Category not found"}), 404
    patch = {k: payload[k] for k in ("factor", "proxy", "confidence") if k in payload}
    return jsonify({"factor": store.update("emission_factors", {"category": category}, patch) or {"category": category, **FACTORS[category], **patch}})

@app.errorhandler(404)
def not_found(_): return jsonify({"error": "Route not found"}), 404

@app.get("/")
def serve_frontend_root():
    return send_from_directory(FRONTEND_DIR, "index.html") if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")) else jsonify({"service": "greenzaction-api"})

@app.get("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"): return jsonify({"error": "Route not found"}), 404
    requested = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(requested): return send_from_directory(FRONTEND_DIR, path)
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")): return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"error": "Route not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_ENV") == "development")
