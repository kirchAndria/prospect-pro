"""
Scraping Google Maps robuste avec retry, timeouts et error handling.
v3 — Fixes :
  - Bouton "Plus" cliqué sur chaque avis -> verbatims COMPLETS (accroche v2)
  - Regex note fiabilisee (ne matche plus "5 photos")
  - Facebook/Instagram captures depuis la fiche Maps directement
  - Texte de la reponse du gerant capture (reponse_gerant_texte)
  - Coordonnees extraites AVANT l'onglet Avis (conservé de v2)
"""
import re
import time
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
    sync_playwright = None  # ✅ explicite : plus de "possibly unbound"
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
# EXTRACTION DES AVIS — v3 avec "Plus" et verbatims complets
# ============================================================

def _parse_note_aria(alt: str) -> Optional[int]:
    """
    Parse l'aria-label d'une note Google de façon stricte.
    Ex: "5 étoiles sur 5", "Rated 4.0 out of 5, 3 reviews".
    Ne matche JAMAIS des contextes comme "5 photos".
    """
    if not alt:
        return None
    # Pattern prioritaire : "<n> étoile(s)" / "<n> star(s)" / "<n> out of 5" / "<n> sur 5"
    m = re.search(
        r"([0-5](?:[.,][05])?)\s*(?:étoile|star|out of|sur)",
        alt, re.IGNORECASE
    )
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            return int(val)  # arrondi 4.5 -> 4 pour la granularite classique Google
        except ValueError:
            pass
    return None


def _extraire_reponse_gerant(bloc) -> tuple:
    """
    Retourne (bool_reponse, texte_reponse).
    Google affiche la reponse du gerant dans un bloc contenant
    'Réponse du propriétaire' / 'Response from the owner'.
    """
    try:
        blocs_rep = bloc.query_selector_all("div.CDe7pd, div[joraOf]")
        for el in blocs_rep:
            txt = (el.inner_text() or "").strip()
            if txt:
                # Retire le header type "Réponse du propriétaire" si present
                lignes = txt.split("\n")
                if len(lignes) > 1 and ("éponse" in lignes[0] or "esponse" in lignes[0]):
                    return True, "\n".join(lignes[1:]).strip()
                return True, txt
    except Exception:
        pass
    return False, ""


def extract_reviews(page: Page) -> List[Dict]:
    """Extrait tous les avis visibles avec texte COMPLET (bouton 'Plus' cliqué)."""
    avis_liste = []

    blocs = page.query_selector_all("div.jftiEf")
    if not blocs:
        blocs = page.query_selector_all("div[data-review-id]")

    logger.info(f"📑 {len(blocs)} blocs d'avis détectés")

    # ✅ FIX v3 #1 : déplier les avis tronqués AVANT l'extraction
    _cliquer_tous_les_plus(page)

    for idx, bloc in enumerate(blocs):
        try:
            # Auteur
            auteur_elem = bloc.query_selector("div.d4r55")
            if auteur_elem:
                auteur = auteur_elem.inner_text().strip()
            else:
                auteur = (bloc.inner_text() or "").strip().split("\n")[0]

            # Note — regex stricte via _parse_note_aria
            note = None
            img = bloc.query_selector("span[role='img']")
            if img:
                note = _parse_note_aria(img.get_attribute("aria-label") or "")

            # Texte (déjà déplié grâce au clic sur "Plus")
            texte = ""
            el_txt = bloc.query_selector("span.wiI7pd, span.OCobZe")
            if el_txt:
                texte = el_txt.inner_text().strip()

            # Date relative ("il y a 2 mois", "3 septembre"...)
            date = ""
            el_date = bloc.query_selector("span.rsqaWe, span.dehysf")
            if el_date:
                date = el_date.inner_text().strip()

            # ✅ FIX v3 #4 : réponse du gérant (bool + texte)
            reponse_gerant, reponse_txt = _extraire_reponse_gerant(bloc)

            if auteur or texte:
                avis_liste.append({
                    "auteur": auteur,
                    "note": note,
                    "texte": texte,
                    "date": date,
                    "reponse_gerant": reponse_gerant,
                    "reponse_gerant_texte": reponse_txt,
                })

        except Exception as e:
            logger.debug(f"⚠️  Error parsing review {idx}: {e}")
            continue

    logger.info(f"✅ {len(avis_liste)} avis extraits (verbatims complets)")
    return avis_liste


def _cliquer_tous_les_plus(page: Page) -> None:
    """
    ✅ FIX v3 #1 : Google tronque les avis longs avec un bouton 'Plus'/'More'.
    On clique tous ces boutons pour obtenir le texte complet du verbatim.
    """
    try:
        boutons_plus = page.query_selector_all(
            "button[aria-label*='Plus'], button[aria-label*='More'], "
            "button.w8nwRe.kyuRq"
        )
        for btn in boutons_plus:
            try:
                btn.click()
                page.wait_for_timeout(150)
            except Exception:
                continue
        if boutons_plus:
            logger.info(f"🔓 {len(boutons_plus)} avis dépliés (bouton 'Plus')")
    except Exception as e:
        logger.debug(f"Depliage avis: {e}")


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


def extract_social_links(page: Page) -> Dict[str, Optional[str]]:
    """
    ✅ FIX v3 #3 : capture Facebook/Instagram directement depuis la fiche Maps
    (les gérants les ajoutent souvent comme liens du profil).
    """
    liens: Dict[str, Optional[str]] = {"facebook": None, "instagram": None}

    try:
        ancres = page.query_selector_all("a[data-pid], a[href*='http']")
        for a in ancres[:60]:
            href = (a.get_attribute("href") or "").lower()
            if href:
                if not liens["facebook"] and ("facebook.com" in href or "fb.com" in href):
                    liens["facebook"] = a.get_attribute("href")
                elif not liens["instagram"] and "instagram.com" in href:
                    liens["instagram"] = a.get_attribute("href")
            if liens["facebook"] and liens["instagram"]:
                break
    except Exception as e:
        logger.debug(f"Liaisons sociales Maps: {e}")
    return liens


# ============================================================
# SCROLLING — détection automatique du vrai conteneur scrollable
# ============================================================

def scroll_reviews(page: Page, scroll_count: int = 8, delay_sec: float = 1.0) -> None:
    """Trouve le div réellement scrollable et scrolle jusqu'à la fin."""
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
    if sync_playwright is None:
        raise RuntimeError("Playwright non installé — lancez: pip install playwright && playwright install chromium")

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

            # === COORDONNÉES D'ABORD ===
            logger.info("📊 Extraction coordonnées...")
            resultat["telephone"] = extract_phone(page)
            resultat["website"] = extract_website(page)
            resultat["adresse"] = extract_address(page)
            logger.info(f"📞 tel={resultat['telephone']} | 🌍 site={resultat['website']}")

            # ✅ FIX v3 #3 : réseaux sociaux depuis la fiche Maps (avant onglet avis)
            logger.info("🔗 Liaisons sociales sur la fiche...")
            sociaux = extract_social_links(page)
            resultat.update(sociaux)

            # === REVIEWS TAB ===
            logger.info("📑 Onglet Avis...")
            click_safe(page, MAPS_SELECTORS["reviews_tab"], timeout=3000)
            page.wait_for_timeout(2500)

            # === SCROLL ===
            logger.info("⏳ Scrolling avis...")
            scroll_reviews(page, scroll_count=8, delay_sec=1.0)

            # === EXTRACTION AVIS (avec dépliage 'Plus') ===
            logger.info("📋 Extraction avis...")
            resultat["avis"] = extract_reviews(page)

        except Exception as e:
            logger.error(f"❌ Erreur scraping: {e}")
            raise
        finally:
            navigateur.close()

    # === Enrichissement web HORS du navigateur (email + réseaux complémentaires) ===
    site_url = resultat.get("website")
    if site_url:  # ✅ narrow : site_url est str ici, Pylance le sait
        logger.info(f"🌐 Analyse du site web pour contacts : {site_url}...")
        try:
            contacts = extraire_contacts_site(site_url)

            # ✅ Fusion non destructive : ne remplit que les champs vides
            for k, v in contacts.items():
                if v and not resultat.get(k):
                    resultat[k] = v
            logger.info(
                f"✅ Contacts web extraits : email={resultat.get('email')}, "
                f"insta={bool(resultat.get('instagram'))}, fb={bool(resultat.get('facebook'))}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Erreur enrichissement contacts web: {e}")

    return resultat
