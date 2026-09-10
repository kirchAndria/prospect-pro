"""
Scraping Google Maps robuste avec retry, timeouts et error handling.
v2 — Fixes : extract_reviews appelé, scroll auto sur le bon conteneur,
coordonnées extraites AVANT l'onglet Avis.
"""
import re
import time
import logging
from typing import Optional, Dict, List

from prospect.config import (
    PLAYWRIGHT_HEADLESS, PLAYWRIGHT_TIMEOUT_MS, PLAYWRIGHT_RETRY_MAX,
    PLAYWRIGHT_RETRY_DELAY_SEC, PLAYWRIGHT_ARGS, USER_AGENT,
    MAPS_SELECTORS, get_logger
)
from prospect.collecte_web import extraire_contacts_site

logger = get_logger("scraper_maps")

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    logger.error("playwright non installé")


# ============================================================
# UTILITAIRES SÉLECTION RÉSILIENTS
# ============================================================

def find_element_safe(page: Page, selectors: List[str], timeout: int = 5000):
    """Essaie plusieurs sélecteurs, retourne le premier trouvé."""
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout)
            return page.query_selector(selector)
        except Exception:
            continue
    return None


def click_safe(page: Page, selectors: List[str], timeout: int = 3000) -> bool:
    element = find_element_safe(page, selectors, timeout)
    if element:
        try:
            element.click()
            return True
        except Exception as e:
            logger.warning(f"⚠️  Click failed: {e}")
    return False


def get_text_safe(page: Page, selectors: List[str], timeout: int = 3000) -> Optional[str]:
    element = find_element_safe(page, selectors, timeout)
    if element:
        try:
            return (element.inner_text() or "").strip()
        except Exception:
            pass
    return None


def get_attribute_safe(page: Page, selectors: List[str], attr: str, timeout: int = 3000) -> Optional[str]:
    element = find_element_safe(page, selectors, timeout)
    if element:
        try:
            return element.get_attribute(attr)
        except Exception:
            pass
    return None


# ============================================================
# EXTRACTION DES AVIS
# ============================================================

def extract_reviews(page: Page) -> List[Dict]:
    """Extrait tous les avis visibles (blocs div.jftiEf + fallback)."""
    avis_liste = []

    # Sélecteurs de blocs : classe actuelle + fallback historique
    blocs = page.query_selector_all("div.jftiEf")
    if not blocs:
        blocs = page.query_selector_all("div[data-review-id]")

    logger.info(f"📑 {len(blocs)} blocs d'avis détectés")

    for idx, bloc in enumerate(blocs):
        try:
            # Auteur
            auteur_elem = bloc.query_selector("div.d4r55")
            if auteur_elem:
                auteur = auteur_elem.inner_text().strip()
            else:
                auteur = (bloc.inner_text() or "").strip().split("\n")[0]

            # Note — regex fiabilisée (évite de matcher n'importe quel chiffre)
            note = None
            img = bloc.query_selector("span[role='img']")
            if img:
                alt = img.get_attribute("aria-label") or ""
                m = re.search(r"(\d)\s*(?:étoile|star|sur|of)", alt)
                if not m:
                    m = re.search(r"(\d)(?=\s*(?:étoile|star))", alt)
                if m:
                    note = int(m.group(1))

            # Texte
            texte = ""
            el_txt = bloc.query_selector("span.wiI7pd, span.OCobZe")
            if el_txt:
                texte = el_txt.inner_text().strip()

            # Date
            date = ""
            el_date = bloc.query_selector("span.rsqaWe, span.dehysf")
            if el_date:
                date = el_date.inner_text().strip()

            # Réponse du gérant
            reponse_gerant = bool(bloc.query_selector("div.CDe7pd"))

            if auteur or texte:
                avis_liste.append({
                    "auteur": auteur,
                    "note": note,
                    "texte": texte,
                    "date": date,
                    "reponse_gerant": reponse_gerant,
                })

        except Exception as e:
            logger.debug(f"⚠️  Error parsing review {idx}: {e}")
            continue

    return avis_liste


# ============================================================
# EXTRACTION COORDONNÉES
# ============================================================

def extract_phone_number(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"(?:\+261|0)\s?3[2-9](?:[\s.-]?\d{2}){3}",  # Madagascar
        r"\+?\d[\d\s().-]{8,}\d",                     # International
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0).strip()
    return None


def extract_phone(page: Page) -> Optional[str]:
    text = get_text_safe(page, MAPS_SELECTORS["phone_button"])
    if text:
        phone = extract_phone_number(text)
        if phone:
            return phone
    try:
        return extract_phone_number(page.inner_text("body"))
    except Exception:
        return None


def extract_website(page: Page) -> Optional[str]:
    return get_attribute_safe(page, MAPS_SELECTORS["website_link"], "href")


def extract_address(page: Page) -> Optional[str]:
    return get_text_safe(page, MAPS_SELECTORS["address_element"])


# ============================================================
# SCROLLING — détection automatique du vrai conteneur scrollable
# ============================================================

def scroll_reviews(page: Page, scroll_count: int = 8, delay_sec: float = 1.0) -> None:
    """Trouve le div réellement scrollable (scrollHeight > clientHeight) et scrolle jusqu'à la fin."""
    scrollable = None
    try:
        candidates = page.query_selector_all("div[role='main'] div")
        for el in candidates[:80]:
            try:
                is_scrollable = el.evaluate(
                    "el => el.scrollHeight > el.clientHeight && el.clientHeight > 100"
                )
                if is_scrollable:
                    scrollable = el
                    break
            except Exception:
                continue

        if scrollable:
            logger.info("✅ Conteneur scrollable des avis trouvé")
        else:
            logger.warning("⚠️ Conteneur non trouvé, fallback souris")

        derniere_hauteur = -1
        stable = 0
        for i in range(scroll_count):
            try:
                if scrollable:
                    scrollable.evaluate("el => el.scrollTop = el.scrollHeight")
                else:
                    page.mouse.wheel(0, 4000)
                page.wait_for_timeout(int(delay_sec * 1000))

                # Stop si plus rien ne charge (fin des avis)
                try:
                    h = scrollable.evaluate("el => el.scrollHeight") if scrollable else 0
                    if h == derniere_hauteur:
                        stable += 1
                        if stable >= 3:
                            logger.info("✅ Fin des avis atteinte")
                            break
                    else:
                        stable = 0
                    derniere_hauteur = h
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"⚠️  Scroll error: {e}")
                continue

    except Exception as e:
        logger.error(f"❌ Error scrolling: {e}")


# ============================================================
# MAIN
# ============================================================

def scrape_google_maps(nom: str, adresse: str = "", headless: Optional[bool] = None, max_retries: int = 3) -> Dict:
    if headless is None:
        headless = PLAYWRIGHT_HEADLESS

    requete = f"{nom} {adresse}".strip()
    resultat = {
        "avis": [], "telephone": None, "website": None,
        "adresse": None, "email": None, "instagram": None, "facebook": None,
    }

    for attempt in range(max_retries):
        try:
            logger.info(f"🔍 Tentative {attempt + 1}/{max_retries}: {requete}")
            resultat = _scrape_once(requete, headless)
            logger.info(f"✅ Scrape réussi: {len(resultat.get('avis', []))} avis")
            return resultat
        except Exception as e:
            logger.warning(f"⚠️  Tentative {attempt + 1} échouée: {e}")
            if attempt < max_retries - 1:
                delay = PLAYWRIGHT_RETRY_DELAY_SEC * (attempt + 1)
                logger.info(f"⏳ Retry dans {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ Scrape échoué après {max_retries} tentatives")

    return resultat


def _scrape_once(requete: str, headless: bool) -> Dict:
    resultat = {
        "avis": [], "telephone": None, "website": None,
        "adresse": None, "email": None, "instagram": None, "facebook": None,
    }

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=headless, args=PLAYWRIGHT_ARGS)
        try:
            context = navigateur.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)

            # === GOTO ===
            logger.info("🌐 Ouverture Maps...")
            page.goto(
                "https://www.google.com/maps/search/" + requete.replace(" ", "+"),
                timeout=PLAYWRIGHT_TIMEOUT_MS,
            )
            page.wait_for_timeout(2000)

            # === COOKIES ===
            logger.info("🍪 Acceptation cookies...")
            click_safe(page, MAPS_SELECTORS["cookie_accept"], timeout=2000)

            # === OPEN PLACE ===
            logger.info("📍 Ouverture fiche...")
            click_safe(page, MAPS_SELECTORS["place_link"], timeout=3000)
            page.wait_for_timeout(2500)

            # === COORDONNÉES D'ABORD (fiche ouverte, boutons visibles) ===
            logger.info("📊 Extraction coordonnées...")
            resultat["telephone"] = extract_phone(page)
            resultat["website"] = extract_website(page)
            resultat["adresse"] = extract_address(page)
            logger.info(f"📞 tel={resultat['telephone']} | 🌍 site={resultat['website']}")

            # === REVIEWS TAB ===
            logger.info("📑 Onglet Avis...")
            click_safe(page, MAPS_SELECTORS["reviews_tab"], timeout=3000)
            page.wait_for_timeout(2500)

            # === SCROLL ===
            logger.info("⏳ Scrolling avis...")
            scroll_reviews(page, scroll_count=8, delay_sec=1.0)

            # === EXTRACTION AVIS ===
            logger.info("📋 Extraction avis...")
            resultat["avis"] = extract_reviews(page)

        except Exception as e:
            logger.error(f"❌ Erreur scraping: {e}")
            raise
        finally:
            navigateur.close()

    # === Enrichissement web HORS du navigateur ===
    if resultat.get("website"):
        logger.info(f"🌐 Analyse du site web pour contacts : {resultat['website']}...")
        try:
            contacts = extraire_contacts_site(resultat["website"])
            resultat.update(contacts)
            logger.info(
                f"✅ Contacts web extraits : email={resultat.get('email')}, "
                f"insta={bool(resultat.get('instagram'))}, fb={bool(resultat.get('facebook'))}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Erreur enrichissement contacts web: {e}")

    return resultat
