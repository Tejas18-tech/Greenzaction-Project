import os
from datetime import datetime, timedelta
from uuid import uuid4
from werkzeug.security import generate_password_hash

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

COLLECTIONS = ["users", "transactions", "emission_factors", "carbon_calculations", "green_scores", "reward_ledger", "achievements", "sustainability_goals", "recommendations", "product_emissions", "carbon_budgets", "challenges", "merchant_profiles", "predictions"]


def now():
    return datetime.utcnow().isoformat() + "Z"


class DataStore:
    def __init__(self):
        self.mongo = None
        self.db = None
        uri = os.getenv("MONGODB_URI", "").strip()
        if uri and MongoClient:
            try:
                self.mongo = MongoClient(uri, serverSelectionTimeoutMS=1200)
                self.mongo.admin.command("ping")
                self.db = self.mongo[os.getenv("db_name", "greenzaction")]
            except Exception:
                self.mongo = None
                self.db = None
        self.mem = {name: [] for name in COLLECTIONS}
        self._seed()

    @property
    def mode(self):
        return "mongodb" if self.db is not None else "demo-memory"

    def _seed(self):
        from backend.carbon import FACTORS
        from backend.advanced import PRODUCTS
        if self.db is not None:
            if self.db.emission_factors.count_documents({}) == 0:
                for category, value in FACTORS.items():
                    self.insert("emission_factors", {"category": category, **value, "active": True, "created_at": now()})
            if self.db.achievements.count_documents({}) == 0:
                for item in self._achievements(): self.insert("achievements", item)
            if self.db.product_emissions.count_documents({}) == 0:
                for item in PRODUCTS: self.insert("product_emissions", item)
            self._seed_demo_mongo()
            return
        for category, value in FACTORS.items():
            self.insert("emission_factors", {"category": category, **value, "active": True, "created_at": now()})
        for item in self._achievements(): self.insert("achievements", item)
        for item in PRODUCTS: self.insert("product_emissions", item)
        self._seed_demo_memory()

    def _achievements(self):
        return [
            {"id": "first-step", "name": "First step", "description": "Log your first purchase", "threshold": 1, "kind": "transactions"},
            {"id": "low-carbon", "name": "Low-carbon rhythm", "description": "Log five A or B rated purchases", "threshold": 5, "kind": "eco"},
            {"id": "momentum", "name": "Momentum", "description": "Earn 100 Green Points", "threshold": 100, "kind": "points"},
        ]

    def _seed_demo_memory(self):
        if not self.find_one("users", {"email": "admin@greenzaction.app"}):
            self.insert("users", {"name": "Greenzaction Admin", "email": "admin@greenzaction.app", "password_hash": generate_password_hash("admin1234"), "role": "admin", "created_at": now()})
        if self.find_one("users", {"email": "demo@greenzaction.app"}): return
        demo = self.insert("users", {"name": "Aarav Mehta", "email": "demo@greenzaction.app", "password_hash": generate_password_hash("demo1234"), "role": "user", "created_at": now()})
        samples = [
            ("Green Basket", 680, "Food & groceries", "UPI", 0), ("Metro Pass", 320, "Transportation", "Card", 3),
            ("Solar Utilities", 1450, "Utilities", "Card", 8), ("Everyday Threads", 1900, "Clothing", "UPI", 17),
            ("City Fuel", 2200, "Fuel", "Wallet", 21), ("Refill Market", 410, "Shopping", "UPI", 26),
        ]
        from backend.carbon import calculate_carbon
        for merchant, amount, category, method, days in samples:
            calc = calculate_carbon(amount, category)
            transaction = self.insert("transactions", {"user_id": demo["id"], "merchant": merchant, "amount": amount, "category": category, "payment_method": method, "description": "Seeded demo transaction", "date": (datetime.utcnow() - timedelta(days=days)).date().isoformat(), **calc, "created_at": now(), "updated_at": now()})
            reward = {"A": 40, "B": 24}.get(transaction.get("rating"), 0)
            if reward:
                self.insert("reward_ledger", {"user_id": demo["id"], "transaction_id": transaction["id"], "points": reward, "reason": f"{transaction['rating']}-rated purchase", "created_at": now()})

    def _seed_demo_mongo(self):
        if self.find_one("users", {"email": "demo@greenzaction.app"}): return
        # Keep MongoDB clean for real accounts; the demo user is only seeded once.
        self._seed_demo_memory()
        # _seed_demo_memory writes to whichever backend is active.

    def insert(self, collection, doc):
        payload = dict(doc)
        payload.setdefault("id", str(uuid4()))
        if self.db is not None:
            self.db[collection].insert_one(payload)
            payload.pop("_id", None)
        else:
            self.mem[collection].append(payload)
        return payload

    def find_one(self, collection, query):
        if self.db is not None:
            doc = self.db[collection].find_one(query, {"_id": 0})
            return doc
        return next((d for d in self.mem[collection] if all(d.get(k) == v for k, v in query.items())), None)

    def find_many(self, collection, query=None, sort_key=None, reverse=True, skip=0, limit=0):
        query = query or {}
        if self.db is not None:
            cursor = self.db[collection].find(query, {"_id": 0})
            if sort_key: cursor = cursor.sort(sort_key, -1 if reverse else 1)
            if skip: cursor = cursor.skip(skip)
            if limit: cursor = cursor.limit(limit)
            return list(cursor)
        rows = [d for d in self.mem[collection] if all(d.get(k) == v for k, v in query.items())]
        if sort_key: rows.sort(key=lambda x: x.get(sort_key, ""), reverse=reverse)
        return rows[skip: skip + limit if limit else None]

    def update(self, collection, query, patch):
        if self.db is not None:
            self.db[collection].update_one(query, {"$set": patch})
            return self.find_one(collection, query)
        doc = self.find_one(collection, query)
        if doc: doc.update(patch)
        return doc

    def delete(self, collection, query):
        if self.db is not None: return self.db[collection].delete_one(query).deleted_count > 0
        before = len(self.mem[collection])
        self.mem[collection] = [d for d in self.mem[collection] if not all(d.get(k) == v for k, v in query.items())]
        return len(self.mem[collection]) < before

    def count(self, collection, query=None):
        if self.db is not None: return self.db[collection].count_documents(query or {})
        return len(self.find_many(collection, query))

    def all_for_user(self, collection, user_id):
        return self.find_many(collection, {"user_id": user_id}, sort_key="date")
