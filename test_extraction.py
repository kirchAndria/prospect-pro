"""Test minimal : ouvre une fiche Maps, tu scrolles, on compte les avis extraits."""
from playwright.sync_api import sync_playwright

NOM, VILLE = "La petite Brasserie", "Antananarivo"

with sync_playwright() as p:
    nav = p.chromium.launch(
    headless=False,
    args=[
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--no-first-run"
    ],
)

    page = nav.new_page()
    page.goto(f"https://www.google.com/maps/search/{NOM} {VILLE}")
    input("👆 Scrolle les avis dans la fenêtre, puisTRÉE ici...")

    blocs = page.query_selector_all("div[data-review-id]")
    print(f"\n🔍 {len(blocs)} blocs d'avis détectés")
    for b in blocs[:3]:
        texte = b.inner_text()[:150].replace("\n", " | ")
        print(f"  → {texte}")
    nav.close()
