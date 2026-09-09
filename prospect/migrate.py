"""Migration one-shot : nouvelles colonnes CRM. Lance : python -m prospect.migrate"""
import sqlite3
from prospect import crm

COLONNES = {
    "telephone": "TEXT",
    "website": "TEXT",
    "email": "TEXT",
    "date_envoi": "TEXT",
    "date_reponse": "TEXT",
}

def migrate():
    with sqlite3.connect(crm.DB) as con:
        existantes = {r[1] for r in con.execute("PRAGMA table_info(prospects)")}
        for col, typ in COLONNES.items():
            if col not in existantes:
                con.execute(f"ALTER TABLE prospects ADD COLUMN {col} {typ}")
                print(f"  + colonne {col} ajoutée")
                
    con.execute("""CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT, ville TEXT, nb_resultats INTEGER,
            date_scan TEXT DEFAULT (datetime('now')))""")

    print("✅ Migration terminée")

if __name__ == "__main__":
    migrate()
