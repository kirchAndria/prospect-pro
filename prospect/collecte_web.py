"""
Enrichissement contacts web : email, Instagram, Facebook depuis le site du prospect.
(Ne scrape PAS Google Maps — ça, c'est scraper_maps.py)
"""
import re
import logging

import requests

try:
    from prospect.config import get_logger, REQUEST_TIMEOUT
except ImportError:
    get_logger = logging.getLogger
    REQUEST_TIMEOUT = 15

logger = get_logger("collecte_web")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Emails poubelle à ignorer
BAD_EMAILS = ("noreply", "no-reply", "example.", "sentry", "wixpress", "test@", "u003", "@2x", ".png", ".jpg")


def _chercher_emails(html: str):
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
    # mailto: en priorité (plus fiable)
    mailtos = re.findall(r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", html)
    vues = list(dict.fromkeys(mailtos + emails))  # dédoublonne en gardant l'ordre
    valides = [e for e in vues if not any(b in e.lower() for b in BAD_EMAILS)]
    return valides


def _chercher_reseaux(html: str):
    instagram = bool(re.search(r"instagram\.com/[a-zA-Z0-9_.]+", html))
    facebook = bool(re.search(r"facebook\.com/[a-zA-Z0-9_.]+", html))
    return instagram, facebook


def extraire_contacts_site(url: str) -> dict:
    """Extrait email / instagram / facebook du site du prospect (+ page contact)."""
    resultat = {"email": None, "instagram": None, "facebook": None}

    if not url:
        return resultat
    if not url.startswith("http"):
        url = "https://" + url

    pages_a_tester = [url]

    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
        html = r.text
        logger.info(f"🌐 ({r.status_code}) {url} ({len(html)} chars)")

        emails = _chercher_emails(html)
        insta, fb = _chercher_reseaux(html)
        if emails:
            resultat["email"] = emails[0]
        resultat["instagram"] = insta
        resultat["facebook"] = fb

        # Si rien trouvé, tester la page /contact
        if not any(resultat.values()):
            m = re.search(r'href=["\']([^"\']*contact[^"\']*)["\']', html, re.IGNORECASE)
            if m:
                lien = m.group(1)
                if lien.startswith("/"):
                    from urllib.parse import urljoin
                    lien = urljoin(url, lien)
                if lien.startswith("http"):
                    logger.info(f"🌐 Fallback page contact : {lien}")
                    r2 = requests.get(lien, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
                    emails = _chercher_emails(r2.text)
                    insta, fb = _chercher_reseaux(r2.text)
                    if emails:
                        resultat["email"] = emails[0]
                    resultat["instagram"] = resultat["instagram"] or insta
                    resultat["facebook"] = resultat["facebook"] or fb

    except Exception as e:
        logger.warning(f"⚠️ Erreur collecte web ({url}): {e}")

    return resultat
