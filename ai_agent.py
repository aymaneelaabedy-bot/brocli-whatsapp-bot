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
- Basic : 199 DH/visite — 1x/semaine (4 visites/mois = 796 DH)
- Standard : 189 DH/visite — 2x/semaine (8 visites/mois = 1 512 DH)
- Pro : 179 DH/visite — 3x/semaine (12 visites/mois = 2 148 DH)
- Daily : 163 DH/visite — 5x/semaine (20 visites/mois = 3 260 DH)
Assurance RC incluse. Devis gratuit sur mesure selon surface.

## FLUX DE CONVERSATION
"bonjour" / "salam" → "Salam 👋 Brocli, nettoyage pro de bureaux à Rabat. C'est pour quel type d'espace ?"
"prix" / "combien" → Donne le tarif directement + "Devis gratuit sur mesure, je vous le prépare ?"
"oui" / "intéressé" / confirme → Demande : "Super 👍 Pour préparer votre devis, donnez-moi juste : votre prênom, votre activité et votre quartier 🙏"
"pas intéressé" / "non" → "Ok, pas de souci. Bonne journée 🙏"
"j'ai déjà quelqu'un" → "Ok ! Si jamais vous voulez comparer, on est là 😊"
"je réfléchis" / "plus tard" → "Je comprends 😊 Je peux demander à notre équipe de vous rappeler quand vous voulez, sans engagement. Ça vous convient ?"

## COLLECTE DES INFOS CLIENT
Quand le client donne son prénom + activité + quartier → confirme chaleureusement et mets le tag de réservation.
Extrait les infos et formate le tag comme ceci (en une seule ligne à la fin) :
[LEAD_BOOKED:name=PRENOM,business=ACTIVITE,location=QUARTIER]

Exemple : "Parfait Ahmed ! Notre équipe vous contacte très bientôt pour votre pharmacie 😊[LEAD_BOOKED:name=Ahmed,business=Pharmacie,location=Agdal]"

Si le client donne juste son prénom sans le reste → redemande poliment l'activité et le quartier.

## LANGUE
Adapte-toi : français si le client écrit en français, darija/arabe si il écrit en arabe.

## INFOS BROCLI
Zone : Rabat, Agdal, Hay Riad, Souissi, Salé, Témara
Services : bureaux, cabinets médicaux, agences, commerces
Abonnements flexibles, sans engagement long terme, équipes formées, assurance incluse
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

        # Check if the lead is booked and extract client info
        booked = False
        lead_info = {}

        # Try extended format: [LEAD_BOOKED:name=X,business=Y,location=Z]
        extended = re.search(r'\[LEAD_BOOKED:([^\]]+)\]', text)
        if extended:
            booked = True
            for part in extended.group(1).split(','):
                if '=' in part:
                    k, v = part.split('=', 1)
                    lead_info[k.strip()] = v.strip()
            text = re.sub(r'\[LEAD_BOOKED:[^\]]*\]', '', text).strip()
        elif "[LEAD_BOOKED]" in text:
            booked = True
            text = text.replace("[LEAD_BOOKED]", "").strip()

        logger.info(f"🤖 Agent response for {sender} (booked={booked}, info={lead_info}): {text[:80]}")
        return text, booked, lead_info

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
