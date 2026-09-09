"""
Qualification : transforme une fiche brute en prospect scoré.
🔥 chaud / 🌡️ tiède / ❄️ froid
"""
from prospect.collecte import chercher_commerces, recuperer_avis


def scorer(fiche: dict) -> dict:
    """
    Logique de score :
    - Volume d'avis (activité + visibilité)          → points
    - Note moyenne entre 3.5 et 4.6 (a des problèmes → points
      mais reste rattrapable — un 2.0 est mort, un 4.9 n'a pas besoin de nous)
    - Avis récents non traités = le signal d'or
    """
    score = 0
    raison = []

    nb = fiche.get("nb_avis") or 0
    note = fiche.get("note") or 0

    if nb >= 100:
        score += 30
        raison.append(f"{nb} avis = commerce actif et visible")
    elif nb >= 30:
        score += 15
        raison.append(f"{nb} avis = activité correcte")

    if 3.5 <= note <= 4.6:
        score += 30
        raison.append(f"note {note}★ = marge de progression réelle")
    elif note > 4.6:
        score += 10
        raison.append(f"note {note}★ = bon, mais peu de douleur")

    avis_negatifs = [a for a in fiche.get("avis", []) if (a.get("note") or 5) <= 3]
    if avis_negatifs:
        score += 40
        raison.append(f"{len(avis_negatifs)} avis ≤3★ récents non traités = DOULEUR IMMÉDIATE")

    if score >= 70:
        temperature = "🔥 CHAUD"
    elif score >= 40:
        temperature = "🌡️ TIÈDE"
    else:
        temperature = "❄️ FROID"

    return {"score": score, "temperature": temperature, "raisons": raison}


if __name__ == "__main__":
    commerces = chercher_commerces("restaurant", "Antananarivo")
    for c in commerces:
        fiche = recuperer_avis(c["id_place"])
        fiche["nb_avis"] = fiche.get("nb_avis") or c["nb_avis"]
        s = scorer(fiche)
        print(f"\n{c['nom']} — {s['score']} pts {s['temperature']}")
        for r in s["raisons"]:
            print(f"   → {r}")
