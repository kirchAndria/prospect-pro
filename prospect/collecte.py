"""
Collecte des données via Google Places API (New).
Phase 1 : recherche par texte + récupération des avis d'une fiche.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://places.googleapis.com/v1/places"


def chercher_commerces(requete: str, ville: str, max_resultats: int = 10) -> list:
    """
    Recherche des commerces par type + ville.
    Ex : chercher_commerces("restaurant", "Antananarivo")
    Retourne : nom, adresse, note, nb_avis, id_place
    """
    resp = requests.post(
        f"{BASE}:searchText",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": os.getenv("PLACES_API_KEY"),
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,places.id"
            ),
        },
        json={"textQuery": f"{requete} à {ville}", "languageCode": "fr"},
    )
    resp.raise_for_status()
    resultats = []
    for p in resp.json().get("places", [])[:max_resultats]:
        resultats.append({
            "id_place": p.get("id"),
            "nom": p.get("displayName", {}).get("text", "?"),
            "adresse": p.get("formattedAddress", ""),
            "note": p.get("rating", 0),
            "nb_avis": p.get("userRatingCount", 0),
        })
    return resultats


def recuperer_avis(id_place: str, max_avis: int = 5) -> dict:
    """
    Détails d'une fiche : avis récents du commerce.
    """
    resp = requests.get(
        f"{BASE}/{id_place}",
        headers={
            "X-Goog-Api-Key": os.getenv("PLACES_API_KEY"),
            "X-Goog-FieldMask": (
                "displayName,rating,userRatingCount,"
                "reviews.rating,reviews.text,reviews.authorAttribution"
            ),
        },
        params={"languageCode": "fr"},
    )
    resp.raise_for_status()
    data = resp.json()
    avis = []
    for a in data.get("reviews", [])[:max_avis]:
        avis.append({
            "auteur": a.get("authorAttribution", {}).get("displayName", "?"),
            "note": a.get("rating"),
            "texte": a.get("text", {}).get("text", ""),
        })
    return {
        "nom": data.get("displayName", {}).get("text", "?"),
 "note": data.get("rating"),
        "nb_avis": data.get("userRatingCount"),
        "avis": avis,
    }


# --- TEST direct ---
if __name__ == "__main__":
    print("=== RECHERCHE ===")
    commerces = chercher_commerces("restaurant", "Antananarivo")
    for c in commerces:
        print(f"  {c['nom']} — {c['note']}★ ({c['nb_avis']} avis)")

    if commerces:
        print(f"\n=== DÉTAIL : {commerces[0]['nom']} ===")
        fiche = recuperer_avis(commerces[0]["id_place"])
        for a in fiche["avis"]:
            print(f"\n[{a['note']}★] {a['auteur']} :")
            print(f"  {a['texte'][:200]}")
