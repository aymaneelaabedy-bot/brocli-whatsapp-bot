"""
Brocli WhatsApp AI Sales Bot — Webhook Server
Receives WhatsApp messages and responds with AI-generated sales conversation.
"""

import os
import json
import hmac
import hashlib
import logging
import threading
import csv
import time
from flask import Flask, request, jsonify, render_template
from whatsapp import WhatsAppClient
from ai_agent import BrocliAgent
from memory import ConversationMemory

# Track how many contacts we broadcast to (set via /api/set_total or broadcast.py)
BROADCAST_TOTAL = int(os.environ.get("BROADCAST_TOTAL", 304))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

wa = WhatsAppClient(
    phone_number_id=os.environ["WA_PHONE_NUMBER_ID"],
    access_token=os.environ["WA_ACCESS_TOKEN"]
)
agent = BrocliAgent(api_key=os.environ["ANTHROPIC_API_KEY"])
memory = ConversationMemory()

VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "brocli_verify_2024")
APP_SECRET  = os.environ.get("WA_APP_SECRET", "")


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta."""
    if not APP_SECRET:
        return True  # Skip in dev mode
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.route("/webhook", methods=["GET"])
def webhook_verify():
    """Meta webhook verification handshake."""
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verified")
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    """Handle incoming WhatsApp messages."""
    # Verify signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.data, sig):
        logger.warning("❌ Invalid signature")
        return "Unauthorized", 401

    data = request.get_json(silent=True) or {}

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Process incoming messages
                for msg in value.get("messages", []):
                    handle_message(msg, value)

                # Log status updates
                for status in value.get("statuses", []):
                    logger.info(f"📬 Status update: {status.get('id')} → {status.get('status')}")

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)

    return jsonify({"status": "ok"}), 200


def handle_message(msg: dict, value: dict):
    """Process a single incoming message and reply with AI."""
    msg_type = msg.get("type")
    sender   = msg.get("from")
    msg_id   = msg.get("id")

    if msg_type != "text":
        # Handle non-text (images, audio, etc.) gracefully
        wa.send_text(sender, "Merci pour votre message 🙏 Pouvez-vous nous écrire en texte pour que nous puissions mieux vous aider ?")
        return

    text = msg["text"]["body"].strip()
    logger.info(f"📨 Message from {sender}: {text[:80]}")

    # Ignore auto-replies / bots
    AUTO_REPLY_KEYWORDS = [
        "merci d'avoir contacté", "merci de nous avoir contacté",
        "message automatique", "réponse automatique", "auto-reply",
        "هذه رسالة تلقائية", "شكرا على تواصلك",
        "we will get back to you", "this is an automated",
        "dites-nous en quoi nous pouvons vous aider",
        "nous vous répondrons dans les plus brefs délais",
        "notre équipe vous contactera"
    ]
    if any(kw in text.lower() for kw in AUTO_REPLY_KEYWORDS):
        logger.info(f"🤖 Auto-reply detected from {sender}, ignoring.")
        wa.mark_read(msg_id)
        return

    # Mark as read
    wa.mark_read(msg_id)

    # Get conversation history
    history = memory.get(sender)

    # Check if lead already booked
    if memory.is_booked(sender):
        wa.send_text(sender, "Bonjour ! Votre demande de devis est déjà enregistrée. Notre équipe vous contactera très bientôt 😊")
        return

    # Generate AI response
    response, booked = agent.reply(text, history, sender)

    # Save to memory
    memory.add(sender, "user", text)
    memory.add(sender, "assistant", response)

    if booked:
        memory.mark_booked(sender)
        logger.info(f"🎉 LEAD BOOKED: {sender}")

    # Send response
    wa.send_text(sender, response)
    logger.info(f"✅ Replied to {sender}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "service": "Brocli WhatsApp Bot"})


# ─────────────────────────────────────────────
# Dashboard routes
# ─────────────────────────────────────────────

@app.route("/", methods=["GET"])
def dashboard():
    """Serve the live dashboard."""
    return render_template("dashboard.html")


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Return aggregate stats for the dashboard."""
    stats = memory.get_stats()
    stats["broadcast_total"] = BROADCAST_TOTAL
    return jsonify(stats)


@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    """Return all conversation data for the dashboard."""
    return jsonify(memory.get_all_conversations())


@app.route("/api/set_total", methods=["POST"])
def api_set_total():
    """Update broadcast total (called by broadcast.py after sending)."""
    global BROADCAST_TOTAL
    data = request.get_json(silent=True) or {}
    if "total" in data:
        BROADCAST_TOTAL = int(data["total"])
    return jsonify({"broadcast_total": BROADCAST_TOTAL})


# ─────────────────────────────────────────────
# Broadcast routes
# ─────────────────────────────────────────────

_broadcast_status = {"running": False, "sent": 0, "failed": 0, "total": 0, "done": False}

def _clean_number(num: str) -> str:
    num = num.replace("+", "").replace(" ", "").replace("-", "").replace(".", "")
    if num.startswith("0") and len(num) == 10:
        num = "212" + num[1:]
    if not num.startswith("212"):
        num = "212" + num
    return num

def _run_broadcast(contacts: list, template_name: str, delay: float):
    global _broadcast_status
    _broadcast_status.update({"running": True, "sent": 0, "failed": 0, "total": len(contacts), "done": False})
    for i, phone in enumerate(contacts, 1):
        try:
            result = wa.send_template(phone, template_name, language="fr")
            if result.get("messages"):
                _broadcast_status["sent"] += 1
            else:
                _broadcast_status["failed"] += 1
                logger.warning(f"⚠️ {phone}: {result}")
        except Exception as e:
            _broadcast_status["failed"] += 1
            logger.error(f"❌ {phone}: {e}")
        logger.info(f"[{i}/{len(contacts)}] sent={_broadcast_status['sent']} failed={_broadcast_status['failed']}")
        if i < len(contacts):
            time.sleep(delay)
    _broadcast_status["running"] = False
    _broadcast_status["done"] = True
    logger.info(f"✅ Broadcast done: {_broadcast_status['sent']} sent, {_broadcast_status['failed']} failed")


@app.route("/api/broadcast/start", methods=["POST"])
def api_broadcast_start():
    global _broadcast_status
    if _broadcast_status["running"]:
        return jsonify({"error": "already running", "status": _broadcast_status}), 400

    data = request.get_json(silent=True) or {}
    template_name = data.get("template", "brocli_outreach_fr")
    delay = float(data.get("delay", 6.0))
    contacts_raw = data.get("contacts", [])

    if not contacts_raw:
        return jsonify({"error": "no contacts provided"}), 400

    contacts = [_clean_number(str(c)) for c in contacts_raw if str(c).strip()]
    contacts = list(dict.fromkeys(contacts))

    t = threading.Thread(target=_run_broadcast, args=(contacts, template_name, delay), daemon=True)
    t.start()
    return jsonify({"started": True, "total": len(contacts), "template": template_name})


@app.route("/api/broadcast/status", methods=["GET"])
def api_broadcast_status():
    return jsonify(_broadcast_status)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Brocli bot starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
