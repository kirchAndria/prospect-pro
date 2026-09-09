"""
Deep analyse des avis d'un commerce via IA (Gemini avec fallback Groq).
Extrait : signal OR, douleurs, points forts, verdict, angle d'accroche.
"""
import json
from prospect.ia_client import get_ia_client
from prospect.config import get_logger

logger = get_logger("analyse")

# ============================================================
# 🛡️ Détection des réponses génériques
# ============================================================

GENERIQUES_CONNUS = [
    "merci",
    "thank",
    "nous vous remercions",
    "au plaisir",
    "a bientot",
    "ravi",
    "we appreciate",
    "thanks for",
]


def _texte_reponse(a: dict) -> str | None:
    """Retourne le TEXTE de la reponse du gerant, quel que soit le format."""
    rep = a.get("reponse_gerant")
    if isinstance(rep, bool):
        return None
    if isinstance(rep, str) and rep.strip():
        return rep.strip()
    return None


def _detecter_generiques(avis: list) -> list:
    """Detecte les reponses de gerant copie-collees (generiques)."""
    reponses = [
        t[:120].lower()
        for a in avis
        if (t := _texte_reponse(a)) is not None
    ]
    return [
        rep for rep in reponses
        if any(g in rep for g in GENERIQUES_CONNUS)
    ]


# ============================================================
# 📋 Preparation du contexte pour l'IA
# ============================================================

def _contexte_avis(nom: str, avis: list) -> str:
    """Construit le bloc de texte des avis pour le prompt IA."""
    lignes = []
    for a in avis:
        note = a.get("note") or "?"
        texte = (a.get("texte") or "(sans texte)")[:300]
        gerant = ("gerant a repondu" if a.get("reponse_gerant")
                  else "SANS reponse du gerant")
        lignes.append(f"[{note}★] {a.get('date', '')} — {gerant}\n"
                      f"  {texte}")
    bloc = "\n".join(lignes)

    n_rep = sum(1 for a in avis if a.get("reponse_gerant"))
    generiques = _detecter_generiques(avis)

    meta = (f"Commerce : {nom}\n"
            f"{len(avis)} avis collectes, {n_rep} avec reponse du gerant.\n")
    if generiques:
        meta += ("Attention : reponses du gerant generiques/copie-collees "
                 f"detectees ({len(generiques)}).\n")
    return meta + "\nAvis :\n" + bloc


# ============================================================
# 🧠 L'analyse IA
# ============================================================

def analyser_avis(nom: str, avis: list) -> dict:
    """Analyse les avis et retourne le dict de signaux via IA (Gemini → Groq)."""
    if not avis:
        return {
            "signal_or": "Aucun avis collecté.",
            "douleurs": [],
            "points_forts": [],
            "verdict": "Extrais d'abord les avis.",
            "angle_accroche": "",
        }

    contexte = _contexte_avis(nom, avis)

    prompt = f"""Tu es un expert en prospection commerciale.
Analyse ces avis Google d'un commerce et reponds en JSON strict avec ces cles :
- "signal_or" : LE angle d'attaque le plus puissant pour un prestataire
  (1-2 phrases, concret, base sur un fait des avis)
- "douleurs" : liste de 2-4 problemes recurrents mentionnes
- "points_forts" : liste de 1-3 forces du commerce
- "verdict" : qualifie ce prospect (chaleur, priorite) en 1 phrase
- "angle_accroche" : le hook exact a utiliser en 1 phrase

{contexte}
"""

    try:
        ia = get_ia_client()
        resp_text = ia.generate(prompt, json_mode=True, max_retries=3)
        return json.loads(resp_text)
    except json.JSONDecodeError:
        logger.warning("⚠️  JSON parse error, fallback analyse")
    except Exception as e:
        logger.warning(f"⚠️  Analyse IA echouee ({e}) — analyse degradee.")

    # --- Fallback sans IA : analyse statistique pure ---
    notes = [a.get("note") for a in avis if a.get("note") is not None]
    moyenne = sum(notes) / len(notes) if notes else None
    n_sans_rep = sum(1 for a in avis if a.get("reponse_gerant") is False)
    n_rep = sum(1 for a in avis if a.get("reponse_gerant"))
    faible = [a["texte"][:80] for a in avis if (a.get("note") or 5) <= 3]

    signal = []
    if moyenne is not None and moyenne < 4.2:
        signal.append(f"Note moyenne faible ({moyenne:.1f}★) — image a defendre.")
    if faible:
        signal.append(f"{len(faible)} avis negatifs: {'; '.join(faible[:2])}")
    if n_rep == 0:
        signal.append("Le gerant ne repond a AUCUN avis — zero gestion de reputation.")

    return {
        "signal_or": " ".join(signal) or "Pas de signal fort detecte.",
        "douleurs": faible[:3],
        "points_forts": [],
        "verdict": f"Note {moyenne:.1f}★, {n_rep}/{len(avis)} reponses gerant." if moyenne else "Notes manquantes.",
        "angle_accroche": "",
    }
