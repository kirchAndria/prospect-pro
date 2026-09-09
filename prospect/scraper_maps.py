"""
Scraping Maps robuste avec retry, timeouts, error handling.
Selectors résilients + logging détaillé.
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

logger = get_logger("scraper_maps")

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
except ImportError:
    logger.error("playwright non installé")


# ============================================================
# UTILITAIRES DE SÉLECTION RÉSILIENTS
# ============================================================

def find_element_safe(page: Page, selectors: List[str], timeout: int = 5000):
    """
    Essaie plusieurs sélecteurs jusqu'à en trouver un.
    Retourne l'élément ou None.
    """
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout)
            return page.query_selector(selector)
        except (PlaywrightTimeoutError, Exception):
            continue
    return None


def click_safe(page: Page, selectors: List[str], timeout: int = 3000) -> bool:
    """
    Clique sur le premier élément trouvé parmi les sélecteurs.
    Retourne True si succès.
    """
    element = find_element_safe(page, selectors, timeout)
    if element:
        try:
            element.click()
            return True
        except Exception as e:
            logger.warning(f"⚠️  Click failed: {e}")
    return False


def get_text_safe(page: Page, selectors: List[str], timeout: int = 3000) -> Optional[str]:
    """
    Récupère le texte du premier élément trouvé.
    """
    element = find_element_safe(page, selectors, timeout)
    if element:
        try:
            return (element.inner_text() or "").strip()
        except Exception:
            pass
    return None


def get_attribute_safe(
    page: Page, selectors: List[str], attr: str, timeout: int = 3000
) -> Optional[str]:
    """
    Récupère un attribut du premier élément trouvé.
    """
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
    """
    Extrait tous les avis visibles de la page.
    Résilient aux changements de structure HTML.
    """
    avis_liste = []

    try:
        blocs = page.query_selector_all(MAPS_SELECTORS["review_blocks"][0])
        logger.info(f"📑 {len(blocs)} blocs d'avis détectés")

        for idx, bloc in enumerate(blocs):
            try:
                # Auteur
                auteur_elem = bloc.query_selector("div.d4r55")
                auteur = (auteur_elem.inner_text() if auteur_elem else bloc.inner_text()).strip()
                auteur = auteur.split("\n")[0]  # Première ligne seulement

                # Note
                note = None
                img = bloc.query_selector("span[role='img']")
                if img:
                    alt = img.get_attribute("aria-label") or ""
                    m = re.search(r"(\d)", alt)
                    note = int(m.group(1)) if m else None

                # Texte
                texte = ""
                el_txt = bloc.query_selector("span.wiI7pd")
                if el_txt:
                    texte = el_txt.inner_text().strip()

                # Date
                date = ""
                el_date = bloc.query_selector("span.rsqaWe")
                if el_date:
                    date = el_date.inner_text().strip()

                # Réponse gerant
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

    except Exception as e:
        logger.error(f"❌ Error extracting reviews: {e}")

    return avis_liste


# ============================================================
# EXTRACTION DES COORDONNÉES
# ============================================================

def extract_phone(page: Page) -> Optional[str]:
    """Extrait le numéro de téléphone."""
    # Via bouton data-item-id
    text = get_text_safe(page, MAPS_SELECTORS["phone_button"])
    if text:
        phone = extract_phone_number(text)
        if phone:
            return phone

    # Via texte brut du body
    try:
        body_text = page.inner_text("body")
        return extract_phone_number(body_text)
    except Exception:
        pass

    return None


def extract_phone_number(text: str) -> Optional[str]:
    """
    Extrait un numéro de téléphone du texte.
    Supporte format international + Madagascar.
    """
    if not text:
        return None

    # Format malgache/international
    patterns = [
        r"(?:\+261|0)\s?3[2-9](?:[\s.-]?\d{2}){3}",  # Malgache
        r"\+?\d[\d\s().-]{8,}\d",  # Général
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0).strip()

    return None


def extract_website(page: Page) -> Optional[str]:
    """Extrait le lien du site web."""
    return get_attribute_safe(page, MAPS_SELECTORS["website_link"], "href")


def extract_address(page: Page) -> Optional[str]:
    """Extrait l'adresse."""
    return get_text_safe(page, MAPS_SELECTORS["address_element"])


# ============================================================
# SCROLLING INTELLIGENT
# ============================================================

def scroll_reviews(page: Page, scroll_count: int = 5, delay_sec: float = 1.0) -> None:
    """
    Scrolle la zone des avis pour charger plus de contenu.
    Gère les timeouts gracefully.
    """
    try:
        # Trouve la zone scrollable
        scrollable = None
        for selector in MAPS_SELECTORS["scrollable_area"]:
            scrollable = page.query_selector(selector)
            if scrollable:
                logger.info(f"✅ Zone scrollable trouvée: {selector}")
                break

        for i in range(scroll_count):
            try:
                if scrollable:
                    scrollable.evaluate("el => el.scrollTop += 4000")
                else:
                    page.mouse.wheel(0, 4000)
                page.wait_for_timeout(int(delay_sec * 1000))
                logger.debug(f"📜 Scroll {i + 1}/{scroll_count}")
            except Exception as e:
                logger.warning(f"⚠️  Scroll error: {e}")
                continue

    except Exception as e:
        logger.error(f"❌ Error scrolling: {e}")


# ============================================================
# MAIN SCRAPING FUNCTION
# ============================================================

def scrape_google_maps(
    nom: str,
    adresse: str = "",
    headless: bool = None,
    max_retries: int = 3,
) -> Dict:
    """
    Scrape une fiche Google Maps complète avec retry.

    Args:
        nom: Nom du commerce
        adresse: Adresse (optionnel)
        headless: Mode invisible (None = config default)
        max_retries: Nombre de tentatives

    Returns:
        Dict avec avis, phone, website, address, email, instagram, facebook
    """
    if headless is None:
        headless = PLAYWRIGHT_HEADLESS

    requete = f"{nom} {adresse}".strip()
    resultat = {
        "avis": [],
        "telephone": None,
        "website": None,
        "adresse": None,
        "email": None,
        "instagram": None,
        "facebook": None,
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
    """Scrape une fois (sans retry)."""
    resultat = {
        "avis": [],
        "telephone": None,
        "website": None,
        "adresse": None,
        "email": None,
        "instagram": None,
        "facebook": None,
    }

    with sync_playwright() as pw:
        try:
            navigateur = pw.chromium.launch(headless=headless, args=PLAYWRIGHT_ARGS)
            context = navigateur.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)

            # === GOTO ===
            logger.info(f"🌐 Ouverture Maps...")
            page.goto(
                "https://www.google.com/maps/search/" + requete.replace(" ", "+"),
                timeout=PLAYWRIGHT_TIMEOUT_MS,
            )
            page.wait_for_timeout(2000)

            # === ACCEPT COOKIES ===
            logger.info("🍪 Acceptation cookies...")
            click_safe(page, MAPS_SELECTORS["cookie_accept"], timeout=2000)

            # === OPEN PLACE ===
            logger.info("📍 Ouverture fiche...")
            click_safe(page, MAPS_SELECTORS["place_link"], timeout=3000)
            page.wait_for_timeout(2000)

            # === CLICK REVIEWS TAB ===
            logger.info("📑 Onglet Avis...")
            click_safe(page, MAPS_SELECTORS["reviews_tab"], timeout=3000)
            page.wait_for_timeout(2000)

            # === SCROLL ===
            logger.info("⏳ Scrolling avis...")
            scroll_reviews(page, scroll_count=5, delay_sec=1.0)

            # === EXTRACT DATA ===
            logger.info("📊 Extraction coordonnées...")
            resultat["telephone"] = extract_phone(page)
            resultat["website"] = extract_website(page)
            resultat["adresse"] = extract_address(page)

            logger.info("📋 Extraction avis...")
            resultat["avis"] = extract_reviews(page)

            navigateur.close()

        except Exception as e:
            logger.error(f"❌ Erreur scraping: {e}")
            raise

    return resultat
