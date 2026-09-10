import logging
from prospect.ia_client import get_ia_client
from prospect.config import get_logger

logger = get_logger("reponses")


def proposer_reponse(prospect: dict, message_gerant: str, historique: str = "") -> str:
    """Propose une réponse percutante au gérant via IA unifiée avec fallback."""
    nom = prospect.get('nom', 'votre établissement')
    note = prospect.get('note', '?')
    nb_avis = prospect.get('nb_avis', '?')

    prompt = f"""Tu es l'assistant d'un freelance expert en gestion de réputation et d'avis Google.
Un gérant vient de répondre à notre message de prospection initiale. Rédige la réponse que le freelance enverra.

RÈGLES STRICTES :
- Même langue que le message du gérant (français par défaut).
- Maximum 60 mots, chaleureux, professionnel et direct.
- Si le gérant est curieux / pose une question de tarif : propose un appel rapide de 10 min ou une courte démo sans engagement.
- Si sceptique / hésitant : valide son doute, rassure-le en proposant de lui offrir 2 exemples concrets rédigés pour sa fiche.
- Si intéressé : propose 2 créneaux d'échange téléphonique simples.
- N'invente aucun fait imaginaire sur le commerce.
- Réponds UNIQUEMENT avec le texte du message à envoyer (aucun guillemet, aucun blabla).

FICHE COMMERCE : {nom} ({note}★ sur {nb_avis} avis)
MESSAGE REÇU DU GÉRANT :
{message_gerant}

{( 'CONTEXTE HISTORIQUE : ' + historique) if historique else ''}"""

    try:
        ia = get_ia_client()
        return ia.generate(prompt, max_retries=2, temperature=0.7).strip()
    except Exception as e:
        logger.warning(f"⚠️  Erreur IA reponses ({e}), utilisation de la réponse de secours")

    # Réponse de secours locale déterministe
    msg_low = message_gerant.lower()
    if any(w in msg_low for w in ["combien", "prix", "tarif", "cout", "coûte"]):
        return (f"Bonjour ! Nos formules débutent à un tarif très accessible et s'adaptent selon votre volume d'avis. "
                f"Auriez-vous 10 minutes cette semaine pour que je vous montre rapidement le fonctionnement et ce que ça donnerait pour {nom} ?")
    elif any(w in msg_low for w in ["non", "pas intéressé", "inutile"]):
        return (f"Je comprends tout à fait ! Si jamais vous souhaitez voir 1 ou 2 exemples concrets de réponses sans engagement, "
                f"n'hésitez pas à me recontacter. Excellente continuation à {nom} !")
    else:
        return (f"Merci pour votre retour ! Je serais ravi de vous détailler cela brièvement. "
                f"Seriez-vous disponible mardi ou jeudi pour un rapide échange de 10 minutes ?")


if __name__ == "__main__":
    print(proposer_reponse(
        {"nom": "La petite Brasserie", "note": 4.5, "nb_avis": 235},
        "Bonjour, c'est interessant mais combien ca coute ?"))
