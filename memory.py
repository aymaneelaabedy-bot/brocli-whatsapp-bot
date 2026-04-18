"""
Conversation memory store for Brocli bot.
Stores message history per phone number in a simple JSON file.
For production, swap with Redis or a database.
"""

import json
import os
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MEMORY_FILE = os.environ.get("MEMORY_FILE", "/data/conversations.json")


class ConversationMemory:
    def __init__(self, filepath: str = MEMORY_FILE):
        self.filepath = filepath
        self._lock    = threading.Lock()
        # Ensure directory exists (important for /data volume on Railway)
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        self._data    = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")
        return {}

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def get(self, phone: str) -> list:
        """Return the conversation history for a phone number."""
        with self._lock:
            return self._data.get(phone, {}).get("messages", [])

    def add(self, phone: str, role: str, content: str):
        """Append a message turn to the conversation history."""
        with self._lock:
            if phone not in self._data:
                self._data[phone] = {
                    "messages":   [],
                    "booked":     False,
                    "started_at": datetime.utcnow().isoformat()
                }
            self._data[phone]["messages"].append({
                "role":       role,
                "content":    content,
                "timestamp":  datetime.utcnow().isoformat()
            })
            self._data[phone]["last_activity"] = datetime.utcnow().isoformat()
            self._save()

    def mark_booked(self, phone: str, name: str = None, business: str = None, location: str = None):
        """Mark a lead as booked with optional client details."""
        with self._lock:
            if phone not in self._data:
                self._data[phone] = {"messages": [], "booked": False}
            self._data[phone]["booked"]    = True
            self._data[phone]["booked_at"] = datetime.utcnow().isoformat()
            if name:
                self._data[phone]["client_name"] = name
            if business:
                self._data[phone]["business"] = business
            if location:
                self._data[phone]["location"] = location
            self._save()
        logger.info(f"🎯 Lead booked: {phone} | {name} | {business} | {location}")

    def is_booked(self, phone: str) -> bool:
        """Check if a lead has already been booked."""
        with self._lock:
            return self._data.get(phone, {}).get("booked", False)

    def get_all_booked(self) -> list:
        """Return list of all booked phone numbers."""
        with self._lock:
            return [phone for phone, data in self._data.items() if data.get("booked")]

    def get_all_conversations(self) -> dict:
        """Return all conversation data (for dashboard API)."""
        with self._lock:
            return dict(self._data)

    def get_stats(self) -> dict:
        """Return conversation statistics."""
        with self._lock:
            total    = len(self._data)
            booked   = sum(1 for d in self._data.values() if d.get("booked"))
            active   = sum(1 for d in self._data.values() if d.get("messages") and not d.get("booked"))
            return {"total": total, "booked": booked, "active": active, "unopened": total - booked - active}
