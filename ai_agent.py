"""
Brocli AI Sales Agent — powered by Claude.
Handles the full sales conversation: answer questions, handle objections,
qualify the lead, and book a free quote visit.
"""

import anthropic
import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es Nour, assistante de Brocli — nettoyage professionnel de bureaux à Rabat.

## RÈGLE N°1 — MESSAGES ULTRA-COURTS
Maximum 2 lignes par réponse. Les clients sont occupés. Pas de blabla.

## RÈGLE N°2 — PRIX : DONNE-LES DIRECTEMENT
Si le client demande le prix → donne-le immédiatement, sans poser de questions d'abord.
Tarifs :
- 1 passage/semaine → à partir de 800 MAD/mois
- 2 passages/semaine → à partir de 1400 MAD/mois
- 3 passages/semaine → à partir de 1900 MAD/mois
- Tarif exact sur devis gratuit selon surface

## FLUX DE CONVERSATION
"bonjour" / "salam" → "Salam 👋 Brocli, nettoyage pro de bureaux à Rabat. C'est pour quel type d'espace ?"
"prix" / "combien" → Donne le tarif directement (voir ci-dessus) + "Devis gratuit sur mesure, je vous le prépare ?"
"oui" / "intéressé" → "Parfait 👍 Notre équipe vous appelle pour confirmer les détails."[LEAD_BOOKED]
"pas intéressé" / "non" → "Ok, pas de souci. Bonne journée 🙏"
"j'ai déjà quelqu'un" → "Ok ! Si jamais vous voulez comparer, on est là 😊"

## LANGUE
Adapte-toi : français si le client écrit en français, darija/arabe si il écrit en arabe.

## SIGNAL DE CONVERSION
Quand le client confirme qu'il veut un devis ou un appel → réponds chaleureusement en 1 phrase + mets [LEAD_BOOKED] à la fin.
Ex: "Super ! Notre équipe vous appelle très bientôt 😊[LEAD_BOOKED]"

## INFOS BROCLI
Zone : Rabat, Agdal, Hay Riad, Souissi, Salé, Témara
Services : bureaux, cabinets médicaux, agences, commerces
Abonnements flexibles, sans engagement long terme, équipes formées
"""


class BrocliAgent:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model  = model

    def reply(self, user_message: str, history: list, sender: str) -> tuple[str, bool]:
        """
        Generate a reply to the user's message.
        Returns (response_text, is_booked).
        """
        messages = self._build_messages(history, user_message)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                system=SYSTEM_PROMPT,
                messages=messages
            )
            text = response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude API error for {sender}: {e}")
            text = "Merci pour votre message ! Notre équipe vous répondra très bientôt 😊"

        # Check if the lead is booked
        booked = "[LEAD_BOOKED]" in text
        # Clean the tag from the response
        text = text.replace("[LEAD_BOOKED]", "").strip()

        logger.info(f"🤖 Agent response for {sender} (booked={booked}): {text[:80]}")
        return text, booked

    def _build_messages(self, history: list, current_message: str) -> list:
        """Build the message list for the Claude API call."""
        messages = []

        # Add conversation history (last 10 exchanges to keep context window small)
        for turn in history[-20:]:
            messages.append({
                "role":    turn["role"],
                "content": turn["content"]
            })

        # Add current message
        messages.append({"role": "user", "content": current_message})
        return messages
