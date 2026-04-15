"""
Brocli Broadcast Script — sends the initial outreach message to all contacts.
Uses an approved WhatsApp template OR a text message (once the conversation is open).

Usage:
  python broadcast.py --contacts contacts.csv --template brocli_outreach
  python broadcast.py --contacts contacts.csv --text   # uses default text message (only if conversation already started)
"""

import os
import csv
import time
import argparse
import logging
from whatsapp import WhatsAppClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_MESSAGE = """Bonjour,

Nous sommes l'équipe Brocli, spécialisée dans le nettoyage professionnel de bureaux à Rabat.

Nous proposons des abonnements mensuels flexibles (1 à 5 passages/semaine) avec des équipes formées, des produits certifiés et une totale tranquillité d'esprit.

Seriez-vous intéressé(e) par un devis gratuit pour votre espace de travail ?

Cordialement,
L'équipe Brocli 🧹✨"""


def load_contacts(filepath: str) -> list:
    """Load phone numbers from a CSV file (one number per line or column 'phone')."""
    contacts = []
    with open(filepath, "r", encoding="utf-8") as f:
        # Try CSV first
        sample = f.read(512)
        f.seek(0)
        if "," in sample or ";" in sample:
            delimiter = ";" if ";" in sample else ","
            reader = csv.DictReader(f, delimiter=delimiter)
            headers = reader.fieldnames or []
            phone_col = next((h for h in headers if "phone" in h.lower() or "tel" in h.lower() or "numero" in h.lower() or "number" in h.lower()), headers[0] if headers else None)
            for row in reader:
                num = row.get(phone_col, "").strip()
                if num:
                    contacts.append(clean_number(num))
        else:
            # Plain list, one number per line
            for line in f:
                num = line.strip()
                if num:
                    contacts.append(clean_number(num))
    # Remove blanks and duplicates
    contacts = list(dict.fromkeys(c for c in contacts if c))
    return contacts


def clean_number(num: str) -> str:
    """Normalize to international format (212XXXXXXXXX)."""
    num = num.replace("+", "").replace(" ", "").replace("-", "").replace(".", "")
    if num.startswith("0") and len(num) == 10:
        num = "212" + num[1:]
    if not num.startswith("212"):
        num = "212" + num
    return num


def broadcast(wa: WhatsAppClient, contacts: list, template_name: str = None,
              message: str = None, delay: float = 6.0, dry_run: bool = False):
    """
    Send initial message to all contacts.
    - delay: seconds between each send (default 6s ≈ 10/min — safe rate)
    - template_name: if set, sends an approved template; otherwise sends free text
    """
    total  = len(contacts)
    sent   = 0
    failed = 0

    logger.info(f"📣 Broadcasting to {total} contacts (delay={delay}s, dry_run={dry_run})")

    for i, phone in enumerate(contacts, 1):
        logger.info(f"[{i}/{total}] → {phone}")

        if dry_run:
            logger.info("  DRY RUN — not sending")
            continue

        try:
            if template_name:
                result = wa.send_template(phone, template_name, language="fr")
            else:
                result = wa.send_text(phone, message or DEFAULT_MESSAGE)

            if result.get("messages") or result.get("error") is None:
                sent += 1
            else:
                logger.warning(f"  ⚠️ Possible failure: {result}")
                failed += 1

        except Exception as e:
            logger.error(f"  ❌ Error for {phone}: {e}")
            failed += 1

        # Respect rate limits — 6 seconds between sends
        if i < total:
            time.sleep(delay)

    logger.info(f"\n✅ Broadcast complete: {sent} sent, {failed} failed out of {total}")
    return {"sent": sent, "failed": failed, "total": total}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brocli WhatsApp Broadcast")
    parser.add_argument("--contacts",  required=True,       help="Path to CSV file with phone numbers")
    parser.add_argument("--template",  default=None,        help="WhatsApp template name (approved by Meta)")
    parser.add_argument("--delay",     type=float, default=6.0, help="Seconds between messages (default: 6)")
    parser.add_argument("--dry-run",   action="store_true", help="Preview without sending")
    args = parser.parse_args()

    wa = WhatsAppClient(
        phone_number_id=os.environ["WA_PHONE_NUMBER_ID"],
        access_token=os.environ["WA_ACCESS_TOKEN"]
    )

    contacts = load_contacts(args.contacts)
    logger.info(f"Loaded {len(contacts)} contacts from {args.contacts}")

    broadcast(
        wa        = wa,
        contacts  = contacts,
        template_name = args.template,
        delay     = args.delay,
        dry_run   = args.dry_run
    )
