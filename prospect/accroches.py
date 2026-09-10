"""
Generation d'accroches ultra-personnalisees via IA (Gemini avec fallback Groq).
v4 :
  - Ordonnance imposee : FAIT -> CONSEQUENCE -> [CTA local] -> SIGNATURE
    (la presentation n'est JAMAIS en ouverture, elle termine le message)
  - CTA genere LOCALEMENT selon style_cta ("direct" | "ouverte") -> A/B testing fiable
  - Priorite de recence : avis < 30 jours privilegie sur l'intensite
  - Nom d'auteur discret (prenom seul ou "un client recent")
  - Nettoyage final de ponctuation (doubles points, espaces fantomes)
  - Log structuré pour A/B testing (signal, style_cta, source ia/fallback)
Ne leve JAMAIS d'exception.
"""
import re
import logging
from typing import Optional

from prospect.ia_client import get_ia_client
from prospect.config import get_logger

logger = get_logger("accroches")

# ============================================================
# 🚫 GARDE-FOU ANTI-QUESTION-PIEGE (post-traitement sortie LLM)
# ============================================================

_QUESTIONS_PIEGES = re.compile(r"([^.?!]*\?)", re.DOTALL)

_MOTIFS_INTERDITS = [
    r"comment g.rez", r"comment g.stion", r"comment trait",
    r"quelle est votre", r"quelle strat.gie", r"que faites",
    r"comment faites", r"comment organi", r"avez.réagi", r"avez.reagi",
]

# ✅ v4 : CTA locaux définis en un seul endroit (A/B testing)
_CTAS = {
    "direct": "Vous seriez disponible 10 minutes cette semaine pour en parler ?",
    "ouverte": "Comment traitez-vous ce genre de retour aujourd'hui ?",
}


def _nettoyer_question_finale(message: str) -> str:
    """
    ✅ Remplace toute question piege sortie par le LLM.
    NOTE v4 : le CTA final est desormais genere LOCALEMENT (voir _construire_message),
    donc ce garde-fou ne s'applique qu'au corps du message produit par l'IA.
    """
    try:
        questions = _QUESTIONS_PIEGES.findall(message)
        for q in questions:
            if any(re.search(m, q, re.IGNORECASE) for m in _MOTIFS_INTERDITS):
                logger.info(f"🚫 Question piege detectee et retiree : {q.strip()[:60]}...")
                message = message.replace(q.strip(), "")
        return message
    except Exception as e:
        logger.warning(f"nettoyer_question_finale: {e}")
        return message


# ============================================================
# 🧹 NETTOYAGE FINAL (point 1 — s'applique à IA ET fallback)
# ============================================================

def _nettoyer_ponctuation(message: str) -> str:
    """
    ✅ Point 1 : normalisation finale avant retour.
    - espaces/whitespace multiples -> simple
    - ". ." / ".. ." / ". ." après point -> point simple
    - espaces avant ponctuation supprimés
    - strip global
    """
    try:
        msg = message.strip()
        msg = msg.replace("...", "\u2026")   # ✅ préserve les ellipses des verbatims
        msg = msg.replace("…", " \u2026")    # espace avant pour éviter la fusion avec le point précédent
        msg = message.strip()
        msg = re.sub(r"\s+", " ", msg)                # espaces multiples
        msg = re.sub(r"\s+([.,;:])", r"\1", msg)
        msg = re.sub(r"\s*([?!])", r" \1", msg)
        msg = re.sub(r"\.{2,}", ".", msg.replace("\u2026", "ELLIPSE_TOKEN"))
        msg = msg.replace("ELLIPSE_TOKEN", "\u2026")
        msg = re.sub(r"([.!?])\s*\.\s*", r"\1 ", msg) # ". ." -> ". "
        msg = re.sub(r"\s+([.!?])", r"\1", msg)       # re-nettoyage final
        return msg.strip()
    except Exception as e:
        logger.warning(f"nettoyer_ponctuation: {e}")
        return message


# ============================================================
# 🎭 PRÉSENTATIONS (fin de message — jamais en ouverture)
# ============================================================

# ✅ v4.1 : variantes de présentation, sans "IA" mis en avant
_PRESENTATIONS_LOCALES = {
    "benefice": (
        "Je développe des outils qui aident les commerces à répondre "
        "automatiquement à leurs avis Google. — Kirch"
    ),
    "local": (
        "Développeur freelance basé à {ville}, je conçois des outils simples "
        "pour faire gagner du temps aux commerces locaux. — Kirch"
    ),
    # Hors scope pour "auto" — réservé à un futur ciblage tech-friendly :
    "ia_forward": (
        "Développeur spécialisé en automatisation IA pour les PME locales. — Kirch"
    ),
}

_VILLE_DEFAUT = "Madagascar"  # ✅ ajuste si tu veux un ancrage plus précis


def _choisir_presentation_style(p: dict, presentation_style: str) -> str:
    """
    ✅ v4.1 : résout le style de présentation.
    - "benefice" / "local" / "ia_forward" : explicite, on respecte.
    - "auto" : heuristique locale sur le profil prospect.
      Défaut sûr : "benefice" (jamais de chaîne vide, jamais ia_forward en auto).
    Ne lève jamais d'exception.
    """
    try:
        if presentation_style in ("benefice", "local", "ia_forward"):
            return presentation_style

        # --- Heuristique "auto" ---
        # Signaux de "confiance locale" : secteur premium/international
        # ou champ gamme_prix élevé -> ancrage local préférable.
        secteur = (p.get("secteur") or p.get("niche") or "").lower()
        gamme = str(p.get("gamme_prix") or p.get("prix") or "").lower()

        secteurs_premium = ("gastronomique", "gastronomie", "hotel",
                            "spa", "cabinet", "clinique", "bijouterie")
        # Signaux d'un commerce traditionnel sensible à la méfiance IA
        secteurs_traditionnels = ("restaurant", "coiffure", "garage",
                                  "artisan", "boulangerie", "plombier")

        if gamme in ("€€€€", "$$$$", "luxe", "premium", "haut de gamme"):
            return "local"
        if any(s in secteur for s in secteurs_premium):
            return "local"
        if any(s in secteur for s in secteurs_traditionnels):
            return "benefice"
        return "benefice"   # ✅ défaut sûr si aucune donnée de profil
    except Exception as e:
        logger.warning(f"choisir_presentation_style: {e}")
        return "benefice"


def _generer_presentation(p: dict, style: str) -> str:
    """
    Génère la phrase de présentation (fin de message).
    Essaie le LLM (few-shot), repli local garanti. Ne lève jamais d'exception.
    """
    ville = (p.get("ville") or p.get("adresse") or _VILLE_DEFAUT).strip().rstrip(".,;")
    exemples = {
        "benefice": _PRESENTATIONS_LOCALES["benefice"],
        "local": _PRESENTATIONS_LOCALES["local"].format(ville=ville),
        "ia_forward": _PRESENTATIONS_LOCALES["ia_forward"],
    }
    exemple = exemples.get(style, exemples["benefice"])

    prompt = f"""Redige UNE phrase de presentation personnelle (max 25 mots) pour la FIN
d'un message de prospection. Pas de markdown, pas de "Bonjour".

Style demande : {style}
{"- Orientee RESULTAT concret, sans mentionner IA ni intelligence artificielle." if style == "benefice" else "- Avec ANCRAGE GEOGRAPHIQUE (base a {ville}) + benefice concret, sans mentionner l'IA.".format(ville=ville) if style == "local" else "- Version tech-friendly."}

Exemples exacts du rendu attendu :
{chr(34)}{_PRESENTATIONS_LOCALES['benefice']}{chr(34)}
{chr(34)}{_PRESENTATIONS_LOCALES['local'].format(ville=_VILLE_DEFAUT)}{chr(34)}
"""
    try:
        ia = get_ia_client()
        phrase = ia.generate(prompt, max_retries=1, temperature=0.6).strip()
        # Validation : pas d'"IA" pour benefice/local (méfiance commerces traditionnels)
        if phrase and not (style in ("benefice", "local")
                           and re.search(r"\bIA\b|intelligence artificielle", phrase, re.IGNORECASE)):
            return phrase
        if style in ("benefice", "local"):
            raise ValueError("mention IA indesirable dans la presentation")
        return phrase or exemple
    except Exception as e:
        logger.warning(f"presentation IA KO ({e}) — repli local.")
        return exemple


def _appliquer_presentation(message: str, presentation: str) -> str:
    """
    ✅ Règle de placement : la présentation termine TOUJOURS le message
    (dernière phrase / ligne de signature), jamais en ouverture.
    Retire une éventuelle auto-présentation en ouverture posée par le LLM.
    """
    try:
        message = re.sub(
            r"^Bonjour\s*,?\s*je\s*suis[^.]*\.\s*",
            "Bonjour, ",
            message,
            flags=re.IGNORECASE,
        )
        message = message.strip()
        if not message.lower().startswith("bonjour"):
            message = f"Bonjour, {message}"
        if presentation and presentation not in message:
            message = f"{message}\n{presentation}"
        return message
    except Exception as e:
        logger.warning(f"appliquer_presentation: {e}")
        return message


# ============================================================
# 🎯 SELECTION DU SIGNAL — avec priorité de RÉCENTCE (point 3)
# ============================================================

_JOURS_RE = re.compile(r"il y a\s+(\d+)\s*(jour|day)", re.IGNORECASE)
_SEMAINES_RE = re.compile(r"il y a\s+(\d+)\s*(semaine|week)", re.IGNORECASE)
_MOIS_RE = re.compile(r"il y a\s+(\d+)\s*(mois|month)", re.IGNORECASE)
_AN_RE = re.compile(r"il y a\s+(un|une|\d+)\s*(an|year)", re.IGNORECASE)


def _age_jours_estime(date_str: str) -> Optional[int]:
    """Estime l'age d'un avis en jours depuis sa date relative Google."""
    if not date_str:
        return None
    try:
        m = _MOIS_RE.search(date_str)
        if m:
            return int(m.group(1)) * 30
        m = _SEMAINES_RE.search(date_str)
        if m:
            return int(m.group(1)) * 7
        m = _JOURS_RE.search(date_str)
        if m:
            return int(m.group(1))
        m = _AN_RE.search(date_str)
        if m:
            nb = 1 if m.group(1).lower() in ("un", "une") else int(m.group(1))
            return nb * 365
        if re.search(r"il y a\s+un\s+mois", date_str, re.IGNORECASE):
            return 30
        if re.search(r"il y a\s+une\s+semaine", date_str, re.IGNORECASE):
            return 7
        return None
    except Exception:
        return None



def _prenom_discret(auteur: str) -> str:
    """
    ✅ Point 4 : prenom seul, ou 'un client recent' si indigent.
    'Jean Dupont' -> 'Jean' ; 'J. D.' -> 'un client recent' ; vide -> 'un client recent'
    """
    try:
        auteur = (auteur or "").strip()
        if not auteur:
            return "un client recent"
        mots = [m for m in re.split(r"[\s.]+", auteur) if m]
        # Un seul mot intelligible (prenom probable) OU prenom + initiale -> garde le 1er
        if len(mots) >= 1 and len(mots[0]) >= 2:
            return mots[0]
        return "un client recent"
    except Exception:
        return "un client recent"


def selectionner_signal_prioritaire(p: dict) -> dict:
    """
    ✅ Point 3 : priorite RECENTE sur intensite.
    Ordre :
      1. avis negatif RECENT (< 60 jours) — meme note moins severe
      2. angle_accroche de l'analyse amont
      3. nombre EXACT d'avis sans reponse
      4. absence de site web OU telephone
    Un avis negatif ANCIEN (>= ~120 jours) n'est plus utilise comme signal
    principal (impression de creuser l'historique) — on lui prefere les
    signaux de repli (3) et (4).
    """
    try:
        avis = p.get("avis") or []

        negatifs = [
            a for a in avis
            if (a.get("note") or 5) <= 3
            and (a.get("texte") or a.get("contenu") or "").strip()
        ]
        # Trie par age estime croissant (recent d'abord)
        for a in negatifs:
            a["_age"] = _age_jours_estime(a.get("date") or a.get("date_relative") or "") or 9999
        negatifs.sort(key=lambda a: a["_age"])

        if negatifs:
            a = negatifs[0]
            if a["_age"] < 60:  # ✅ recence : moins de ~2 mois
                texte = (a.get("texte") or a.get("contenu") or "").strip()
                return {
                    "type": "avis_negatif",
                    "verbatim": _extraire_verbatim(texte),
                    "auteur": _prenom_discret(a.get("auteur") or ""),
                    "date": a.get("date") or a.get("date_relative") or "",
                    "note": a.get("note"),
                    "sans_reponse": not (a.get("reponse_gerant") or a.get("reponse")),
                }
            # ✅ Avis negatif trop ancien : on ne l'utilise PAS en ouverture.
            logger.info(f"⏭️ Avis negatif trop ancien (~{a['_age']}j) — signal de repli utilisé")

        # Repli 1 : angle d'analyse
        if (p.get("angle_accroche") or "").strip():
            return {"type": "angle", "angle": p["angle_accroche"].strip()}

        # Repli 2 : avis sans reponse (chiffre exact)
        n_sans_rep = sum(
            1 for a in avis
            if a.get("reponse_gerant") is False or a.get("reponse") is False
        )
        if n_sans_rep > 0:
            return {"type": "sans_reponse", "nb": n_sans_rep, "nb_total": len(avis)}

        # Repli 3 : absence de site / telephone
        if not p.get("website"):
            return {"type": "absence", "quoi": "site web"}
        if not p.get("telephone"):
            return {"type": "absence", "quoi": "numero de telephone"}

        return {"type": "aucun"}
    except Exception as e:
        logger.warning(f"selectionner_signal_prioritaire: {e}")
        return {"type": "aucun"}


def _extraire_verbatim(texte: str, max_mots: int = 20) -> str:
    mots = texte.split()
    if len(mots) <= max_mots:
        return texte
    return " ".join(mots[:max_mots]) + "…"


# ============================================================
# 📝 CONSTRUCTION DU CONTEXTE
# ============================================================

def _contexte_depuis_signal(p: dict, signal: dict) -> str:
    nom = p.get("nom", "votre etablissement")
    secteur = (p.get("secteur") or p.get("niche") or "").strip()
    lignes = [
        f"Commerce : {nom}",
        f"Secteur : {secteur or 'non precise'} (adapte le vocabulaire : "
        f"clients pour un garage/commerce, visiteurs pour un restaurant, "
        f"patients pour une clinique...)",
        f"Note Google : {p.get('note')}★ sur {p.get('nb_avis')} avis",
    ]

    if signal["type"] == "avis_negatif":
        date_str = f", {signal['date']}" if signal["date"] else ""
        lignes.append(
            f"SIGNAL UNIQUE A UTILISER : l'avis negatif de {signal['auteur']}"
            f"{date_str}, note {signal['note']}★, extrait VERBATIM : "
            f"\"{signal['verbatim']}\""
        )
    elif signal["type"] == "angle":
        lignes.append(f"SIGNAL UNIQUE A UTILISER : {signal['angle']}")
    elif signal["type"] == "sans_reponse":
        lignes.append(
            f"SIGNAL UNIQUE A UTILISER : {signal['nb']} avis sur "
            f"{signal['nb_total']} restent sans reponse du gerant "
            f"(chiffres EXACTS)."
        )
    elif signal["type"] == "absence":
        lignes.append(
            f"SIGNAL UNIQUE A UTILISER : la fiche n'affiche aucun "
            f"{signal['quoi']} sur Google Maps."
        )
    else:
        lignes.append(
            f"SIGNAL UNIQUE A UTILISER : la fiche affiche {p.get('nb_avis', 0)} "
            f"avis avec une note exacte de {p.get('note')}★."
        )

    return "\n".join(lignes)


# ============================================================
# ✍️ GENERATION DE L'ACCROCHE
# ============================================================

def generer_accroche(
    p: dict,
    inclure_exemple_reponse: bool = False,
    style_cta: str = "direct",
    presentation_style: str = "auto",   # ✅ v4.1 : "auto" | "benefice" | "local"
) -> str:
    """
    ... (docstring existante) ...
    ✅ v4.1 : presentation_style choisit la phrase de présentation finale :
      - "benefice" : orientée résultat, sans "IA" (commerces traditionnels)
      - "local"    : ancrage géographique + bénéfice (sensibilité confiance locale)
      - "auto"     : heuristique sur le profil (défaut sûr : "benefice")
    """
    style_cta = style_cta if style_cta in _CTAS else "direct"

    # ✅ v4.1 : résolution du style de présentation (jamais d'exception)
    presentation_style_resolu = _choisir_presentation_style(p, presentation_style)
    presentation = _generer_presentation(p, presentation_style_resolu)

    signal = selectionner_signal_prioritaire(p)
    source = "ia"

    try:
        ia = get_ia_client()
        corps = ia.generate(_construire_prompt(p, signal),
                            max_retries=2, temperature=0.7).strip()
        if corps:
            corps = _nettoyer_question_finale(corps)
        else:
            raise ValueError("corps vide")
    except Exception as e:
        logger.warning(f"⚠️  IA indisponible ({e}) — fallback local.")
        corps = _corps_fallback(p, signal)
        source = "fallback"

    # ✅ v4 : CTA généré LOCALEMENT (jamais par le LLM) — A/B fiable
    message = f"{corps} {_CTAS[style_cta]}"

    if inclure_exemple_reponse and signal["type"] == "avis_negatif":
        exemple = generer_exemple_reponse(p, signal)
        if exemple:
            message = f"{message}\n\nPS : voici le genre de reponse que je vous suggererai :\n\"{exemple}\""

    # ✅ v4.1 : présentation en FIN (jamais en ouverture)
    message = _appliquer_presentation(message, presentation)

    # ✅ v4 point 1 : nettoyage final EXISTANT réutilisé (IA comme fallback)
    message = _nettoyer_ponctuation(message)

    # ✅ v4 point 6 + 4.1 : log structuré (signal, cta, presentation, source)
    logger.info(
        f"📊 ACCROCHE | signal={signal['type']} | cta={style_cta} | "
        f"presentation={presentation_style_resolu} | source={source} | "
        f"prospect={p.get('nom', '?')} | len={len(message)} | "
        f"texte=\"{message[:80]}...\""
    )

    return message



def generer_exemple_reponse(p: dict, signal: Optional[dict] = None) -> str:
    """Genere une courte reponse-exemple a l'avis negatif identifie."""
    if signal is None:
        signal = selectionner_signal_prioritaire(p)
    if signal["type"] != "avis_negatif":
        return ""

    prompt = f"""Redige UNE reponse publique de gerant (max 40 mots) a cet avis Google negatif.
Ton : professionnel, empathique, oriente solution. Pas de markdown.
Utilise seulement le prenom du client.

Commerce : {p.get('nom')}
Avis de {signal['auteur']} : \"{signal['verbatim']}\" ({signal['note']}★)
"""
    try:
        ia = get_ia_client()
        return ia.generate(prompt, max_retries=1, temperature=0.6).strip()
    except Exception as e:
        logger.warning(f"exemple_reponse IA KO ({e}) — fallback local.")
        return (
            f"Bonjour {signal['auteur']}, merci pour ce retour. Nous prenons "
            f"ce point tres au serieux et avons mis en place une correction. "
            f"Nous serions ravis de vous accueillir a nouveau."
        )


def _construire_prompt(p: dict, signal: dict) -> str:
    contexte = _contexte_depuis_signal(p, signal)
    return f"""Tu es un expert en prospection commerciale directe pour PME locales.
Redige le CORPS d'un message de prospection (max 50 mots), en francais, texte brut.
NE termine PAS par une question : la question finale sera ajoutee automatiquement.
NE t'annonce PAS ("je suis developpeur...") : la signature sera ajoutee automatiquement.
Pas de markdown.

STRUCTURE OBLIGATOIRE du corps (2 blocs uniquement) :
1. [FAIT precis] — une observation verifiable : citation d'un avis (auteur + date), ou chiffre exact
2. [CONSEQUENCE business concrete] — une courte phrase logique

REGLES STRICTES :
- Mentionne seulement le PRENOM de l'auteur d'avis (jamais le nom complet).
  Si le nom est absent, dis "un client recent".
- INTERDIT : "plusieurs avis", "certains clients" -> toujours un chiffre exact ou une citation.
- INTERDIT : toute question (elle sera ajoutee automatiquement).
- INTERDIT : toute presentation de toi-meme.
- Aucune phrase applicable a n'importe quel commerce sans modification.

--- EXEMPLES ---
BON : "Bonjour, l'avis de Rina du 3 septembre sur l'attente en salle n'a pas eu de reponse — c'est le genre de point qui, une fois traite, rassure les prochains visiteurs qui lisent vos avis avant de reserver."
MAUVAIS : "Bonjour, je suis developpeur, je parcourais vos avis et j'ai remarque que plusieurs commentaires etaient restes sans reponse. Comment gereez-vous ces retours ?"
--- FIN EXEMPLES ---

{contexte}
"""


# ============================================================
# 🛟 FALLBACK LOCAL — corps uniquement (CTA/signature ajoutes après)
# ============================================================

def _corps_fallback(p: dict, signal: dict) -> str:
    nom = p.get("nom", "votre etablissement")
    secteur = (p.get("secteur") or p.get("niche") or "commerce").strip()
    vocab = {
        "restaurant": "visiteurs", "cafe": "visiteurs", "hotel": "visiteurs",
        "clinique": "patients", "cabinet": "patients",
    }.get(secteur.lower(), "clients")

    if signal["type"] == "avis_negatif":
        date_brute = (signal["date"] or "").strip()
        if date_brute and not date_brute.lower().startswith("il y a"):
            date_str = f" du {date_brute}"
        elif date_brute:
            date_str = f" ({date_brute})"
        else:
            date_str = ""
        return (
            f"Bonjour, j'ai vu l'avis de {signal['auteur']}{date_str} sur la fiche "
            f"Google de {nom} : \"{signal['verbatim']}\" ({signal['note']}★). "
            f"C'est le genre de point qui, une fois corrige, rassure les prochains "
            f"{vocab} qui lisent vos avis avant de venir."
        )
    if signal["type"] == "angle":
        return (
            f"Bonjour, en analysant la fiche Google de {nom}, un point precis "
            f"m'a saute aux yeux : {signal['angle']} Une fois traite, ce detail "
            f"change directement la decision des {vocab} qui comparent avant de choisir."
        )
    if signal["type"] == "sans_reponse":
        return (
            f"Bonjour, sur les {signal['nb_total']} avis de {nom}, "
            f"{signal['nb']} restent sans reponse — or c'est la premiere chose "
            f"que lisent les {vocab} qui hesitent entre vous et un concurrent."
        )
    if signal["type"] == "absence":
        return (
            f"Bonjour, j'ai cherche {nom} sur Google : votre fiche ({p.get('note')}★ "
            f"sur {p.get('nb_avis')} avis) n'affiche aucun {signal['quoi']} — "
            f"beaucoup de {vocab} verifient avant de se deplacer et passent alors au suivant."
        )
    return (
        f"Bonjour, votre fiche {nom} affiche {p.get('nb_avis')} avis avec "
        f"{p.get('note')}★ — une base solide, et j'ai une idee precise pour "
        f"convertir davantage ces visites en {vocab}."
    )
