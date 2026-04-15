"""
WhatsApp Cloud API client for Brocli.
Handles sending messages, marking read, and reading delivery statuses.
"""

import requests
import logging
import time

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v19.0"


class WhatsAppClient:
    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token    = access_token
        self.session         = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json"
        })

    def _post(self, endpoint: str, payload: dict, retries: int = 3) -> dict:
        url = f"{BASE_URL}/{endpoint}"
        for attempt in range(retries):
            try:
                resp = self.session.post(url, json=payload, timeout=15)
                if resp.status_code == 429:          # Rate limited
                    wait = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited — waiting {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"WhatsApp API error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return {}

    def send_text(self, to: str, text: str) -> dict:
        """Send a plain text message to a phone number."""
        # Ensure number has country code, no '+'
        to = to.replace("+", "").replace(" ", "").replace("-", "")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "text",
            "text":              {"preview_url": False, "body": text}
        }
        result = self._post(f"{self.phone_number_id}/messages", payload)
        if result.get("messages"):
            logger.info(f"✅ Sent to {to}: {text[:60]}…")
        else:
            logger.warning(f"⚠️ Possible send failure to {to}: {result}")
        return result

    def send_template(self, to: str, template_name: str, language: str = "fr",
                      components: list = None) -> dict:
        """Send an approved template message (required for first outreach)."""
        to = to.replace("+", "").replace(" ", "").replace("-", "")
        payload = {
            "messaging_product": "whatsapp",
            "to":                to,
            "type":              "template",
            "template": {
                "name":     template_name,
                "language": {"code": language},
            }
        }
        if components:
            payload["template"]["components"] = components
        return self._post(f"{self.phone_number_id}/messages", payload)

    def mark_read(self, message_id: str) -> dict:
        """Mark an incoming message as read (shows double blue tick)."""
        payload = {
            "messaging_product": "whatsapp",
            "status":            "read",
            "message_id":        message_id
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def send_reaction(self, to: str, message_id: str, emoji: str) -> dict:
        """React to a message with an emoji."""
        to = to.replace("+", "")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "reaction",
            "reaction":          {"message_id": message_id, "emoji": emoji}
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def get_media_url(self, media_id: str) -> str:
        """Get the download URL for a media file (image, audio, etc.)."""
        resp = self.session.get(f"{BASE_URL}/{media_id}", timeout=10)
        data = resp.json()
        return data.get("url", "")
