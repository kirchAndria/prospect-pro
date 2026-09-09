"""
CRM SQLite - coeur de données de la machine.
Table prospects : fiches + scoring + statuts horodatés.
Table scans : historique des recherches (niche/ville/date/nb).
"""
import json
import sqlite3
from datetime import datetime, timedelta

DB = "prospection.db"


def connect():
    return sqlite3.connect(DB)


def _clean(value):
    """Convertit les types non supportés par SQLite (list, dict) en JSON."""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(list(value) if isinstance(value, set) else value,
                          ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_place TEXT UNIQUE,
            nom TEXT,
            adresse TEXT,
            note REAL,
            nb_avis INTEGER,
            score INTEGER DEFAULT 0,
            temperature TEXT DEFAULT 'FROID',
            raisons TEXT DEFAULT '',
            statut TEXT DEFAULT 'nouveau',
            notes TEXT,
            telephone TEXT,
            website TEXT,
            email TEXT,
            instagram TEXT,
            facebook TEXT,
            canal_envoi TEXT,
            analyse_ia TEXT,
            date_envoi TEXT,
            date_reponse TEXT,
            dernier_contact TEXT
        )""")
        # Migrations simples (ajout de colonnes si absentes)
        colonnes = [
            ("instagram", "TEXT"),
            ("facebook", "TEXT"),
            ("canal_envoi", "TEXT"),
            ("analyse_ia", "TEXT")
        ]
        for col, type_ in colonnes:
            try:
                con.execute(f"ALTER TABLE prospects ADD COLUMN {col} {type_}")
            except sqlite3.OperationalError:
                pass # Colonne déjà présente

        con.execute("""CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT,
            ville TEXT,
            nb_resultats INTEGER,
            date_scan TEXT DEFAULT (datetime('now'))
        )""")


def upsert(fiche: dict):
    """Insère ou met à jour une fiche (par id_place), sans écraser avis/statut."""
    params = tuple(
        _clean(v) for v in (
            fiche.get("id_place"), fiche.get("nom"), fiche.get("adresse"),
            fiche.get("note"), fiche.get("nb_avis"),
            fiche.get("score", 0), fiche.get("temperature", "FROID"),
            fiche.get("raisons", ""),
        )
    )
    # Garde-fou : id_place est obligatoire (clé unique)
    if not params[0]:
        return

    with connect() as con:
        con.execute("""
            INSERT INTO prospects (id_place, nom, adresse, note, nb_avis,
                                   score, temperature, raisons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_place) DO UPDATE SET
                nom=excluded.nom, adresse=excluded.adresse,
                note=excluded.note, nb_avis=excluded.nb_avis,
                score=excluded.score, temperature=excluded.temperature,
                raisons=excluded.raisons
        """, params)


def enregistrer_scan(niche: str, ville: str, nb_resultats: int):
    with connect() as con:
        con.execute(
            "INSERT INTO scans (niche, ville, nb_resultats) VALUES (?, ?, ?)",
            (_clean(niche), _clean(ville), _clean(nb_resultats)))


def tous(statut: str | None = None) -> list:
    with connect() as con:
        con.row_factory = sqlite3.Row
        if statut:
            rows = con.execute(
                "SELECT * FROM prospects WHERE statut=? ORDER BY score DESC",
                (statut,)).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM prospects ORDER BY score DESC").fetchall()
    return [dict(r) for r in rows]


def marquer_envoye(pid: int, canal: str = None):
    with connect() as con:
        con.execute(
            "UPDATE prospects SET statut='envoyé', date_envoi=datetime('now'), "
            "canal_envoi=? WHERE id=?", (canal, pid))


def marquer_reponse(pid: int):
    with connect() as con:
        con.execute(
            "UPDATE prospects SET statut='a répondu', "
            "date_reponse=datetime('now') WHERE id=?", (pid,))


def update_analyse(pid: int, analyse: dict):
    with connect() as con:
        con.execute("UPDATE prospects SET analyse_ia=? WHERE id=?",
                    (_clean(analyse), pid))


def relances_du_jour() -> list:
    """Prospects 'envoyé' depuis 3 jours ou plus, sans réponse."""
    limite = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT * FROM prospects
            WHERE statut='envoyé' AND date_envoi IS NOT NULL AND date_envoi <= ?
            ORDER BY date_envoi ASC
        """, (limite,)).fetchall()
    return [dict(r) for r in rows]


def historique_scans() -> list:
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM scans ORDER BY date_scan DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


def stats_dashboard() -> dict:
    with connect() as con:
        con.row_factory = sqlite3.Row
        total = con.execute("SELECT COUNT(*) c FROM prospects").fetchone()["c"]
        par_statut = {
            r["statut"]: r["c"]
            for r in con.execute(
                "SELECT statut, COUNT(*) c FROM prospects GROUP BY statut")
        }
        chauds = con.execute(
            "SELECT COUNT(*) c FROM prospects WHERE temperature LIKE '%CHAUD%'"
        ).fetchone()["c"]
        top_scans = con.execute("""
            SELECT niche, ville, SUM(nb_resultats) total
            FROM scans GROUP BY niche, ville ORDER BY total DESC LIMIT 5
        """).fetchall()
    return {
        "total": total,
        "par_statut": par_statut,
        "chauds": chauds,
        "top_scans": [dict(r) for r in top_scans],
    }
