"""
Generation d'accroches personnalisees via IA (Gemini avec fallback Groq).
Robuste : utilise client IA unifié + accroche de secours sans IA.
"""
from prospect.ia_client import get_ia_client
from prospect.config import get_logger

logger = get_logger("accroches")


# ============================================================
# ✍️ Generation de l'accroche
# ============================================================

def generer_accroche(p: dict) -> str:
    """
    Genere une accroche personnalisee. Ne leve JAMAIS d'exception :
    en cas d'echec IA, retourne une accroche de secours construite
    depuis les donnees locales.

    Args:
        p: Dict prospect avec nom, note, nb_avis, avis, angle_accroche, etc.

    Returns:
        Texte d'accroche prêt à envoyer
    """
    nom = p.get("nom", "votre établissement")
    angle = p.get("angle_accroche") or ""
    avis = p.get("avis") or []

    # Signaux locaux pour le prompt ET le fallback
    n_sans_rep = sum(1 for a in avis if a.get("reponse_gerant") is False)
    negatifs = [a.get("texte", "")[:100] for a in avis
                if (a.get("note") or 5) <= 3]
    pas_de_tel = not p.get("telephone")
    pas_de_site = not p.get("website")

    contexte = f"""
Commerce : {nom}
Note : {p.get('note')}★ sur {p.get('nb_avis')} avis
{f"Angle identifie par l'analyse : {angle}" if angle else ""}
{f"{n_sans_rep} avis recents SANS reponse du gerant." if n_sans_rep else ""}
{f"Avis negatifs recents : {'; '.join(negatifs[:2])}" if negatifs else ""}
{f"Pas de telephone sur Google Maps. " if pas_de_tel else ""}
{f"Pas de site web. " if pas_de_site else ""}
"""

    prompt = f"""Tu es un expert en prospection commerciale directe.
Redige UN message de prospection court (max 60 mots), en francais,
pour contacter le gerant de ce commerce. Ton : direct, respectueux,
sans flatterie gratuite. Mentionne UN fait concret de sa fiche Google.
Termine par une question ouverte simple. Pas de markdown, texte brut.

{contexte}
"""

    try:
        ia = get_ia_client()
        return ia.generate(prompt, max_retries=2, temperature=0.7).strip()
    except Exception as e:
        logger.warning(f"⚠️  IA indisponible ({e}) — accroche de secours.")

    # --- Accroche de secours (100% locale, jamais en rade) ---
    accroches = []
    if angle:
        accroches.append(
            f"Bonjour, je suis tombé sur {nom} sur Google Maps et un détail "
            f"m'a sauté aux yeux : {angle}")
    elif n_sans_rep:
        accroches.append(
            f"Bonjour, je parcourais les avis de {nom} et j'ai remarqué que "
            f"plusieurs commentaires récents étaient restés sans réponse — "
            f"sur Google, ça pèse directement sur le classement.")
    elif negatifs:
        accroches.append(
            f"Bonjour, en lisant les avis de {nom}, j'ai vu que quelques "
            f"clients avaient exprimé des frustrations récentes. C'est souvent "
            f"récupérable vite — et ça change l'image de la fiche.")
    elif pas_de_site:
        accroches.append(
            f"Bonjour, je cherchais {nom} sur Google et j'ai remarqué que "
            f"votre fiche n'affiche pas de site web — vous perdez "
            f"probablement des clients qui veulent vérifier avant de venir.")
    else:
        accroches.append(
            f"Bonjour, votre fiche {nom} ressort bien sur Google Maps "
            f"({p.get('nb_avis')} avis) et j'aurais une idée simple pour "
            f"transformer ces visites en encore plus de clients.")

    accroches.append(
        "Vous auriez 10 minutes cette semaine pour en discuter ?")
    return " ".join(accroches)
