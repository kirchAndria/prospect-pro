"""
CRM SQLite - coeur de données de la machine.
Table prospects : fiches + scoring + statuts horodatés + NICHE.
Table scans : historique des recherches (niche/ville/date/nb).
"""
import json
import sqlite3
from datetime import datetime, timedelta
from prospect.config import DB_PATH, get_logger

logger = get_logger("crm")


def connect():
    return sqlite3.connect(DB_PATH)


def _clean(value):
    """Convertit les types non supportés par SQLite (list, dict) en JSON."""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(list(value) if isinstance(value, set) else value,
                          ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def init():
    """Initialise la base de données avec toutes les tables et colonnes."""
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_place TEXT UNIQUE,
            nom TEXT,
            adresse TEXT,
            niche TEXT,
            ville TEXT,
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
            dernier_contact TEXT,
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        )""")

        # Migrations simples (ajout de colonnes si absentes)
        colonnes = [
            ("instagram", "TEXT"),
            ("facebook", "TEXT"),
            ("canal_envoi", "TEXT"),
            ("analyse_ia", "TEXT"),
            ("niche", "TEXT"),
            ("ville", "TEXT"),
            ("tags", "TEXT DEFAULT '[]'"),
            ("created_at", "TEXT DEFAULT (datetime('now'))"),
        ]
        for col, typ in colonnes:
            try:
                con.execute(f"ALTER TABLE prospects ADD COLUMN {col} {typ}")
                logger.info(f"✅ Colonne {col} ajoutée")
            except sqlite3.OperationalError:
                pass  # Colonne déjà présente

        con.execute("""CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT,
            ville TEXT,
            nb_resultats INTEGER,
            date_scan TEXT DEFAULT (datetime('now'))
        )""")

        logger.info("✅ Base de données initialisée")


def upsert(fiche: dict):
    """Insère ou met à jour une fiche (par id_place), sans écraser avis/statut."""
    params = tuple(
        _clean(v) for v in (
            fiche.get("id_place"),
            fiche.get("nom"),
            fiche.get("adresse"),
            fiche.get("niche", ""),
            fiche.get("ville", ""),
            fiche.get("note"),
            fiche.get("nb_avis"),
            fiche.get("score", 0),
            fiche.get("temperature", "FROID"),
            fiche.get("raisons", ""),
        )
    )

    # Garde-fou : id_place est obligatoire (clé unique)
    if not params[0]:
        return

    with connect() as con:
        con.execute("""
            INSERT INTO prospects (id_place, nom, adresse, niche, ville, note, nb_avis,
                                   score, temperature, raisons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_place) DO UPDATE SET
                nom=excluded.nom, adresse=excluded.adresse, niche=excluded.niche,
                ville=excluded.ville, note=excluded.note, nb_avis=excluded.nb_avis,
                score=excluded.score, temperature=excluded.temperature,
                raisons=excluded.raisons
        """, params)


def enregistrer_scan(niche: str, ville: str, nb_resultats: int):
    """Enregistre un scan effectué."""
    with connect() as con:
        con.execute(
            "INSERT INTO scans (niche, ville, nb_resultats) VALUES (?, ?, ?)",
            (_clean(niche), _clean(ville), _clean(nb_resultats)))
    logger.info(f"📊 Scan enregistré: {niche} @ {ville} = {nb_resultats} résultats")


def tous(statut: str | None = None, niche: str | None = None, ordre: str = "score") -> list:
    """
    Récupère tous les prospects, optionnellement filtrés par statut ou niche.
    
    Args:
        statut: Filtrer par statut (nouveau, envoyé, etc.)
        niche: Filtrer par niche
        ordre: Champ de tri (score, date, temperature)
    """
    with connect() as con:
        con.row_factory = sqlite3.Row

        query = "SELECT * FROM prospects WHERE 1=1"
        params = []

        if statut:
            query += " AND statut=?"
            params.append(statut)

        if niche:
            query += " AND niche=?"
            params.append(niche)

        # Tri intelligent
        if ordre == "score":
            query += " ORDER BY score DESC"
        elif ordre == "date":
            query += " ORDER BY created_at DESC"
        elif ordre == "temperature":
            query += " ORDER BY CASE temperature WHEN '🔥 CHAUD' THEN 0 WHEN '🌡️ TIÈDE' THEN 1 ELSE 2 END"
        else:
            query += " ORDER BY score DESC"

        rows = con.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def marquer_envoye(pid: int, canal: str = None):
    """Marque un prospect comme envoyé."""
    with connect() as con:
        con.execute(
            "UPDATE prospects SET statut='envoyé', date_envoi=datetime('now'), "
            "canal_envoi=? WHERE id=?",
            (canal, pid))
    logger.info(f"✉️  Prospect {pid} marqué envoyé via {canal}")


def marquer_reponse(pid: int):
    """Marque un prospect comme ayant répondu."""
    with connect() as con:
        con.execute(
            "UPDATE prospects SET statut='a répondu', "
            "date_reponse=datetime('now') WHERE id=?",
            (pid,))
    logger.info(f"💬 Prospect {pid} marqué comme ayant répondu")


def update_analyse(pid: int, analyse: dict):
    """Met à jour l'analyse IA d'un prospect."""
    with connect() as con:
        con.execute("UPDATE prospects SET analyse_ia=? WHERE id=?",
                    (_clean(analyse), pid))


def update_field(pid: int, field: str, value):
    """
    Met à jour un champ de prospect DE MANIÈRE SÉCURISÉE.
    
    IMPORTANT: Utilise parameterized query pour éviter SQL injection.
    """
    allowed_fields = {
        "telephone", "email", "website", "instagram", "facebook",
        "statut", "notes", "tags", "niche", "ville", "canal_envoi"
    }

    if field not in allowed_fields:
        logger.error(f"❌ Champ non autorisé: {field}")
        return

    with connect() as con:
        con.execute(f"UPDATE prospects SET {field}=? WHERE id=?",
                    (_clean(value), pid))


def get_prospect(pid: int) -> dict | None:
    """Récupère un prospect par ID."""
    with connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM prospects WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


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
    """Récupère l'historique des scans."""
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM scans ORDER BY date_scan DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


def get_niches() -> list:
    """Récupère la liste unique des niches."""
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT niche FROM prospects WHERE niche IS NOT NULL AND niche != '' ORDER BY niche"
        ).fetchall()
    return [r[0] for r in rows]


def get_villes(niche: str = None) -> list:
    """Récupère la liste unique des villes, optionnellement filtrées par niche."""
    with connect() as con:
        if niche:
            rows = con.execute(
                "SELECT DISTINCT ville FROM prospects WHERE niche=? AND ville IS NOT NULL AND ville != '' ORDER BY ville",
                (niche,)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT DISTINCT ville FROM prospects WHERE ville IS NOT NULL AND ville != '' ORDER BY ville"
            ).fetchall()
    return [r[0] for r in rows]


def stats_dashboard() -> dict:
    """Récupère les stats pour le dashboard."""
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

        # Stats par niche
        par_niche = {
            r["niche"]: r["c"]
            for r in con.execute(
                "SELECT niche, COUNT(*) c FROM prospects WHERE niche IS NOT NULL GROUP BY niche ORDER BY c DESC")
        }

    return {
        "total": total,
        "par_statut": par_statut,
        "chauds": chauds,
        "par_niche": par_niche,
    }


def stats_niche(niche: str) -> dict:
    """Récupère les stats d'une niche spécifique."""
    with connect() as con:
        con.row_factory = sqlite3.Row

        total = con.execute(
            "SELECT COUNT(*) c FROM prospects WHERE niche=?", (niche,)
        ).fetchone()["c"]

        par_statut = {
            r["statut"]: r["c"]
            for r in con.execute(
                "SELECT statut, COUNT(*) c FROM prospects WHERE niche=? GROUP BY statut",
                (niche,))
        }

        chauds = con.execute(
            "SELECT COUNT(*) c FROM prospects WHERE niche=? AND temperature LIKE '%CHAUD%'",
            (niche,)
        ).fetchone()["c"]

        par_ville = {
            r["ville"]: r["c"]
            for r in con.execute(
                "SELECT ville, COUNT(*) c FROM prospects WHERE niche=? GROUP BY ville ORDER BY c DESC",
                (niche,))
        }

    return {
        "total": total,
        "par_statut": par_statut,
        "chauds": chauds,
        "par_ville": par_ville,
    }
