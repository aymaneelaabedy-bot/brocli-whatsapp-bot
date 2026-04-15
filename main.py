"""
Brocli WhatsApp AI Sales Bot — Webhook Server
Receives WhatsApp messages and responds with AI-generated sales conversation.
"""

import os
import json
import hmac
import hashlib
import logging
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
