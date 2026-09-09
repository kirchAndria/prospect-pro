"""Proposition de reponse IA quand un prospect reagit a notre accroche."""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODELE = "gemini-3.6-flash"


def proposer_reponse(prospect: dict, message_gerant: str, historique: str = "") -> str:
    prompt = f"""Tu es l'assistant d'un freelance qui vend un service de gestion
professionnelle des reponses aux avis Google. Un gerant vient de repondre a
notre message de prospection. Redige la reponse que notre freelance enverra.

REGLES :
- Meme langue que le message du gerant
- Maximum 60 mots, chaleureux, direct
- Si le gerant est curieux : propose UN appel court de 15 min ou une demo gratuite
- Si sceptique : valide son doute, cite un fait concret de ses propres avis,
  propose de lui montrer 2 exemples de reponses GRATUITEMENT
- Si interesse : propose 2 creneaux d'appel
- N'invente AUCUN fait sur le commerce
- Reponds UNIQUEMENT avec le message

FICHE : {prospect.get('nom')} - {prospect.get('note')}★, {prospect.get('nb_avis')} avis
MESSAGE DU GERANT :
{message_gerant}

{( 'CONTEXTE : ' + historique) if historique else ''}"""
    resp = client.models.generate_content(model=MODELE, contents=prompt)
    return resp.text.strip()


if __name__ == "__main__":
    print(proposer_reponse(
        {"nom": "La petite Brasserie", "note": 4.5, "nb_avis": 235},
        "Bonjour, c'est interessant mais combien ca coute ?"))
