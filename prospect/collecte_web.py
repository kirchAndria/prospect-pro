"""
Extraction web via navigateur dedie (Playwright).
Recupere : avis, telephone, site web, adresse depuis Google Maps.
Enrichit avec emails et reseaux sociaux depuis le site web.
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def extraire_contacts_site(url: str) -> dict:
    """Scrape le site web pour trouver emails et reseaux sociaux."""
    res = {"email": None, "instagram": None, "facebook": None}
    if not url or not url.startswith("http"):
        return res

    try:
        headers = {"User-Agent": UA}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = resp.text

        # 1. Emails (Regex)
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if emails:
            # Filtrer les extensions communes d'images/fichiers qui ressemblent a des mails
            valides = [e for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            if valides:
                res["email"] = valides[0].lower()

        # 2. Reseaux sociaux (Links)
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if "instagram.com/" in href and not res["instagram"]:
                res["instagram"] = a["href"]
            if "facebook.com/" in href and not res["facebook"]:
                res["facebook"] = a["href"]

        # 3. Check /contact page if main page has nothing
        if not res["email"]:
            contact_link = soup.find("a", href=re.compile(r"contact", re.I))
            if contact_link:
                contact_url = urljoin(url, contact_link["href"])
                resp_c = requests.get(contact_url, headers=headers, timeout=5)
                emails_c = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp_c.text)
                if emails_c:
                    res["email"] = emails_c[0].lower()

    except Exception as e:
        print(f"⚠️ Erreur scraping site {url} : {e}")

    return res


def extraire_avis(nom: str, adresse: str = "", headless: bool = False) -> dict:
    requete = f"{nom} {adresse}".strip()
    resultat = {
        "avis": [], "telephone": None, "website": None, "adresse": None,
        "email": None, "instagram": None, "facebook": None
    }

    with sync_playwright() as pw:
        # headless=headless pour permettre le mode invisible
        navigateur = pw.chromium.launch(headless=headless)
        context = navigateur.new_context(user_agent=UA)
        page = context.new_page()

        print(f"🔍 Recherche Maps : {requete}")
        page.goto(
            "https://www.google.com/maps/search/" + requete.replace(" ", "+"),
            timeout=60000,
        )
        page.wait_for_timeout(3000)

        # --- Accepter cookies ---
        for sel in ["button:has-text('Accept all')", "button:has-text('Tout accepter')", "button[aria-label*='Accept']"]:
            try:
                page.click(sel, timeout=2000)
                break
            except Exception: pass

        # --- Ouvrir la fiche si liste ---
        try:
            if page.query_selector("a.hfpxzc"):
                page.click("a.hfpxzc", timeout=3000)
                page.wait_for_timeout(2000)
        except Exception: pass

        # --- Cliquer sur l'onglet AVIS ---
        print("📑 Passage à l'onglet Avis...")
        try:
            for sel in ["button[role='tab']:has-text('Avis')", "button[role='tab']:has-text('Reviews')", "div[role='tab']:has-text('Avis')"]:
                if page.query_selector(sel):
                    page.click(sel)
                    page.wait_for_timeout(2000)
                    break
        except Exception: pass

        # --- Scrolling ---
        print("⏳ Scrolling...")
        try:
            scrollable_sel = "div.m6R6yc, div[role='main'], div.review-dialog-list"
            scrollable = page.query_selector(scrollable_sel)
            for _ in range(5):
                if scrollable:
                    scrollable.evaluate("el => el.scrollTop += 4000")
                else:
                    page.mouse.wheel(0, 4000)
                page.wait_for_timeout(1000)
        except Exception: pass

        # --- Coordonnees ---
        def texte_bouton(item_id: str):
            for sel in (f"button[data-item-id='{item_id}']", f"a[data-item-id='{item_id}']", f"button[data-item-id^='{item_id}']", f"a[data-item-id^='{item_id}']"):
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = (el.inner_text() or "").strip()
                        aria = el.get_attribute("aria-label") or ""
                        return txt or aria.strip() or None
                except Exception: pass
            return None

        def numero_dans_texte(texte: str):
            if not texte: return None
            m = re.search(r"(?:\+261|0)\s?3[2-9](?:[\s.-]?\d{2}){3}", texte)
            if not m:
                m = re.search(r"\+?\d[\d\s().-]{8,}\d", texte)
            return m.group(0).strip() if m else None

        resultat["telephone"] = texte_bouton("phone") or numero_dans_texte(page.inner_text("body"))
        
        site = None
        for sel in ["a[data-item-id^='authority']", "a[aria-label*='Site web']", "a[data-tooltip*='Site web']"]:
            try:
                el = page.query_selector(sel)
                if el:
                    site = el.get_attribute("href")
                    if site: break
            except Exception: pass
        resultat["website"] = site
        resultat["adresse"] = texte_bouton("address")

        # --- Avis ---
        avis_liste = []
        blocs = page.query_selector_all("div.jftiEf")
        for bloc in blocs:
            try:
                auteur = (bloc.query_selector("div.d4r55") or bloc).inner_text().strip()
                note = None
                img = bloc.query_selector("span[role='img']")
                if img:
                    alt = img.get_attribute("aria-label") or ""
                    m = re.search(r"(\d)", alt)
                    note = int(m.group(1)) if m else None
                
                texte = ""
                el_txt = bloc.query_selector("span.wiI7pd")
                if el_txt: texte = el_txt.inner_text().strip()

                date = ""
                el_date = bloc.query_selector("span.rsqaWe")
                if el_date: date = el_date.inner_text().strip()

                reponse_gerant = bool(bloc.query_selector("div.CDe7pd"))

                if auteur or texte:
                    avis_liste.append({
                        "auteur": auteur, "note": note, "texte": texte,
                        "date": date, "reponse_gerant": reponse_gerant,
                    })
            except Exception: continue

        navigateur.close()
        resultat["avis"] = avis_liste

    # --- Enrichissement via Site Web ---
    if resultat["website"]:
        print(f"🌐 Analyse du site web : {resultat['website']}...")
        contacts = extraire_contacts_site(resultat["website"])
        resultat.update(contacts)

    avec_rep = sum(1 for a in avis_liste if a["reponse_gerant"])
    print(f"✅ {len(avis_liste)} avis extraits ({avec_rep} avec réponse).")
    return resultat
