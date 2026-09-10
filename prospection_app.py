"""
CRM Prospection Pro v4.5 - Solution tout-en-un assistée par IA
Dashboard CRM complet, scraping Maps + Web, qualification, deep analyse,
outreach multicanal (WhatsApp/Email/Réseaux) et diagnostics intégrés.
Lancement : streamlit run prospection_app.py
"""
import os
import json
import sqlite3
import pandas as pd
from datetime import datetime
from urllib.parse import quote

import streamlit as st

from prospect import crm
from prospect.collecte import chercher_commerces, recuperer_avis
from prospect.scoring import scorer
from prospect.scraper_maps import scrape_google_maps
from prospect.accroches import generer_accroche
from prospect.analyse import analyser_avis
from prospect.reponses import proposer_reponse
from prospect.ia_client import get_ia_client
from prospect.config import (
    get_logger, PLACES_API_KEY, GEMINI_API_KEY, GROQ_API_KEY,
    GEMINI_MODEL, GROQ_MODEL, DB_PATH
)

logger = get_logger("app")

# ============================================================
# CONFIG STREAMLIT
# ============================================================

st.set_page_config(
    page_title="CRM Prospection Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

crm.init()

# ============================================================
# 🎨 THEME CSS PROFESSIONNEL (Thème Adaptatif)
# ============================================================

st.markdown("""<style>
/* === VARIABLES === */
:root {
    --primary: #5b6cff;
    --primary-dark: #4a5acc;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e1e3f 0%, #16213e 100%) !important;
}
[data-testid="stSidebar"] * { color: #e0e0ef !important; }
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #cfcfe8 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 8px !important;
    width: 100% !important;
    text-align: left !important;
    padding: 0.6rem 1rem !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(91,107,255,0.2) !important;
    border-color: #5b6cff !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #5b6cff, #7b5bff) !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(91,107,255,.4) !important;
}

/* === MÉTRIQUES === */
div[data-testid="stMetric"] {
    background: var(--secondary-background-color) !important;
    border-radius: 12px !important;
    padding: 1.2rem !important;
    border: 1px solid rgba(128,128,160,0.2) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
}
div[data-testid="stMetric"] label {
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    font-size: 1.9rem !important;
}

/* === EXPANDERS/CARTES === */
[data-testid="stExpander"] {
    background: var(--secondary-background-color) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(128,128,160,0.2) !important;
    margin-bottom: 0.8rem !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.03) !important;
}

.main-title {
    background: linear-gradient(90deg, #5b6cff, #9b5bff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 2.2rem;
    margin-bottom: 0.2rem;
}

.subtitle {
    opacity: 0.75;
    font-size: 1rem;
    margin-bottom: 1rem;
}

/* === BADGES STATUTS === */
.badge {
    padding: 0.35rem 0.75rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-block;
}
.badge-nouveau   { background: rgba(99,102,241,0.2); color: #818cf8; }
.badge-envoye    { background: rgba(245,158,11,0.2); color: #f59e0b; }
.badge-repondu   { background: rgba(16,185,129,0.2); color: #10b981; }
.badge-interesse { background: rgba(59,130,246,0.2); color: #3b82f6; }
.badge-client    { background: rgba(34,197,94,0.25); color: #22c55e; }
.badge-abandonne { background: rgba(128,128,140,0.2); color: #9ca3af; }

/* === BARRES DE PROGRESSION === */
.progress-bar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin: 0.75rem 0;
}
.progress-label { font-size: 0.9rem; font-weight: 500; }
.progress-container {
    flex: 1;
    height: 8px;
    background: rgba(128,128,160,0.2);
    border-radius: 4px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #5b6cff, #7b5bff);
    transition: width 0.3s;
}
.progress-value { font-size: 0.85rem; font-weight: 600; opacity: 0.8; }

/* === ALERTES === */
[data-testid="stAlert"] {
    border-radius: 12px !important;
}

.relance-box {
    background: rgba(245,158,11,0.12);
    border: 1px solid rgba(245,158,11,0.4);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.8rem;
}
</style>""", unsafe_allow_html=True)

# ============================================================
# UTILITIES
# ============================================================

def duree_depuis(date_str):
    """Calcule la durée lisible depuis une date ISO."""
    if not date_str:
        return ""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        jours = (datetime.now() - d).days
        if jours == 0:
            return "aujourd'hui"
        elif jours == 1:
            return "hier"
        else:
            return f"il y a {jours}j"
    except ValueError:
        return ""


def badge_statut(statut):
    """Retourne un badge HTML pour le statut."""
    cls = {
        "nouveau": "nouveau",
        "envoyé": "envoye",
        "a répondu": "repondu",
        "intéressé": "interesse",
        "client": "client",
        "abandonné": "abandonne"
    }.get(statut, "nouveau")
    return f'<span class="badge badge-{cls}">{statut}</span>'


def barre_progress(label, nb, max_v, couleur):
    """Retourne une barre de progression HTML."""
    pct = int(100 * nb / max_v) if max_v else 0
    return f"""<div class="progress-bar">
        <span class="progress-label">{label}</span>
        <div class="progress-container">
            <div class="progress-fill" style="width: {pct}%; background: {couleur};"></div>
        </div>
        <span class="progress-value">{nb}</span>
    </div>"""


def etoiles(note) -> str:
    """✅ FIX TypeError : convertit toute note (4.5, '4.5', None...) en int sûr."""
    try:
        return "★" * int(float(note or 0))
    except (ValueError, TypeError):
        return ""


def lire_avis(p: dict) -> list:
    """
    ✅ FIX BUG AFFICHAGE AVIS :
    Relit le JSON des avis stocké dans la colonne notes.
    Gère les 2 formats possibles :
      - une liste d'avis directe : [{...}, {...}]
      - un dict englobant : {"avis": [...], ...}
    Ne plante jamais (retourne [] en cas de doute).
    """
    raw = p.get("notes")
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("avis") or data.get("reviews") or []
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def liens_contact(p, message_accroche: str = ""):
    """Retourne les liens d'action directe de contact."""
    liens = []

    # 1. WhatsApp avec message pré-rempli
    tel = p.get("telephone")
    if tel:
        num_clean = "".join(c for c in tel if c.isdigit() or c == "+").lstrip("+").lstrip("0")
        if len(num_clean) == 9 and num_clean.startswith("3"):
            num_clean = "261" + num_clean
        wa_url = f"https://wa.me/{num_clean}"
        if message_accroche:
            wa_url += f"?text={quote(message_accroche)}"
        liens.append(("💬 WhatsApp Direct", wa_url))

    # 2. Email avec objet et corps pré-remplis
    email = p.get("email")
    if email:
        mailto_url = f"mailto:{email}"
        if message_accroche:
            subject = f"Question concernant {p.get('nom', 'votre établissement')}"
            mailto_url += f"?subject={quote(subject)}&body={quote(message_accroche)}"
        liens.append(("✉️ Email Direct", mailto_url))

    # 2bis. Appel direct
    if tel:
        liens.append(("📞 Appeler", f"tel:{''.join(c for c in tel if c.isdigit())}"))

    # 3. Site web
    if p.get("website"):
        liens.append(("🌐 Site Web", p["website"]))

    # 4. Réseaux
    if p.get("instagram"):
        liens.append(("📸 Instagram", p["instagram"]))
    if p.get("facebook"):
        liens.append(("📘 Facebook", p["facebook"]))

    # 5. Google Maps
    nom_maps = quote(f"{p.get('nom', '')} {p.get('adresse', '')}".strip())
    liens.append(("📍 Google Maps", f"https://www.google.com/maps/search/?api=1&query={nom_maps}"))

    return liens


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown("## 🎯 PROSPECTION PRO")
    st.caption("CRM & IA Tout-en-Un · v4.5")
    st.markdown("---")

    # Alerte relances
    relances = crm.relances_du_jour()
    if relances:
        st.warning(f"🔔 **{len(relances)} relances à faire !**")

    page = st.radio(
        "Navigation",
        [
            "📊 Dashboard & Pipeline",
            "🎯 Prospection Active",
            "🔭 Scanner & Collecte",
            "📋 Base Prospects & Export",
            "⚙️ Diagnostics IA & Outils",
        ],
        label_visibility="collapsed",
        key="main_nav"
    )

    st.markdown("---")
    headless_mode = st.toggle("🌐 Scraping Invisible (Headless)", value=True)
    st.caption("Activé = Playwright tourne en arrière-plan sans fenêtre visible.")

# ============================================================
# 📊 PAGE 1: DASHBOARD & PIPELINE
# ============================================================

if page == "📊 Dashboard & Pipeline":
    st.markdown('<p class="main-title">📊 Dashboard & Pipeline</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Vue d\'ensemble et pilotage de vos opportunités commerciales</p>', unsafe_allow_html=True)

    stats = crm.stats_dashboard()
    ps = stats["par_statut"]

    # KPIs
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("📁 Prospects", stats["total"])
    col2.metric("🔥 Chauds", stats["chauds"])
    contactes = sum(ps.get(s, 0) for s in ["envoyé", "a répondu", "intéressé", "client"])
    col3.metric("✉️ Contactés", contactes)
    reponses = ps.get("a répondu", 0) + ps.get("intéressé", 0) + ps.get("client", 0)
    col4.metric("💬 Réponses", reponses)
    col5.metric("🤝 Clients", ps.get("client", 0))
    taux = f"{(reponses / contactes * 100):.1f}%" if contactes else "0%"
    col6.metric("📈 Taux Réponse", taux)

    st.markdown("---")

    # === ALERTE RELANCES DU JOUR ===
    if relances:
        st.markdown(f"### 🚨 Relances Prioritaires ({len(relances)} prospects sans réponse depuis ≥ 3j)")
        for r in relances[:5]:
            with st.container():
                st.markdown(
                    f"""<div class="relance-box">
                        <b>{r.get('temperature', '?')} {r['nom']}</b> — {r.get('niche', '—')} @ {r.get('ville', '—')}
                        <br><small>✉️ Dernier contact : {duree_depuis(r.get('date_envoi'))} via {r.get('canal_envoi', 'canal non spécifié')} · Note : {r.get('note', '?')}★</small>
                    </div>""",
                    unsafe_allow_html=True
                )
        st.markdown("---")

    # === PIPELINE KANBAN INTERACTIF ===
    st.markdown("### 🗂️ Pipeline de Vente")
    colonnes_kanban = [
        ("🆕 Nouveau", "nouveau", "#6b7280"),
        ("✉️ Envoyé", "envoyé", "#f59e0b"),
        ("💬 A Répondu", "a répondu", "#10b981"),
        ("⭐ Intéressé", "intéressé", "#3b82f6"),
        ("🤝 Client", "client", "#22c55e"),
    ]

    cols = st.columns(len(colonnes_kanban))
    for i, (titre_k, code_statut, couleur) in enumerate(colonnes_kanban):
        with cols[i]:
            nb = ps.get(code_statut, 0)
            st.markdown(f"#### {titre_k} ({nb})")
            prospects_col = crm.tous(statut=code_statut, ordre="score")
            if prospects_col:
                for p in prospects_col[:6]:
                    st.markdown(
                        f"""<div style="background:var(--secondary-background-color);padding:8px;border-radius:8px;border:1px solid rgba(128,128,160,0.2);margin-bottom:6px;font-size:13px">
                            <b>{p['nom']}</b><br>
                            <span style="opacity:0.75">{p.get('temperature', '')} · {p['score']}pts · {p.get('note', '?')}★</span>
                        </div>""",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("Aucun prospect")

    st.markdown("---")

    # Répartition Niches
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        st.markdown("### 🏷️ Répartition par Niche")
        par_niche = stats.get("par_niche", {})
        if par_niche:
            max_v = max(par_niche.values()) if par_niche else 1
            for niche_nom, nb in sorted(par_niche.items(), key=lambda x: -x[1])[:8]:
                label = niche_nom if niche_nom else "Non classé"
                st.markdown(barre_progress(label, nb, max_v, "#5b6cff"), unsafe_allow_html=True)
        else:
            st.info("Aucune donnée de niche.")

    with col_n2:
        st.markdown("### 🌡️ Répartition par Température")
        chauds = stats.get("chauds", 0)
        total = stats.get("total", 0)
        tous_p = crm.tous()
        tiedes = sum(1 for p in tous_p if "TIÈDE" in p.get("temperature", ""))
        froids = sum(1 for p in tous_p if "FROID" in p.get("temperature", ""))
        if total:
            st.markdown(barre_progress("🔥 Chauds (Score ≥ 70)", chauds, total, "#ef4444"), unsafe_allow_html=True)
            st.markdown(barre_progress("🌡️ Tièdes (Score 40-69)", tiedes, total, "#f59e0b"), unsafe_allow_html=True)
            st.markdown(barre_progress("❄️ Froids (Score < 40)", froids, total, "#3b82f6"), unsafe_allow_html=True)


# ============================================================
# 🎯 PAGE 2: PROSPECTION ACTIVE
# ============================================================

elif page == "🎯 Prospection Active":
    st.markdown('<p class="main-title">🎯 Prospection Active</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Qualification, deep analyse, outreach direct et gestion des réponses</p>', unsafe_allow_html=True)

    # Filtres de recherche
    col_s, col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([2, 1, 1, 1, 1, 1])
    recherche = col_s.text_input("🔍 Recherche", "", placeholder="Nom, ville, tél, email...", key="filtre_search")

    niches = crm.get_niches()
    filtre_niche = col_f1.selectbox("Niche", ["toutes"] + niches, key="p_filtre_niche")

    villes = crm.get_villes()
    filtre_ville = col_f2.selectbox("Ville", ["toutes"] + villes, key="p_filtre_ville")

    statuts = ["nouveau", "envoyé", "a répondu", "intéressé", "client", "abandonné"]
    filtre_statut = col_f3.selectbox("Statut", ["tous"] + statuts, key="p_filtre_statut")

    filtre_temp = col_f4.selectbox("Chaleur", ["toutes", "CHAUD", "TIÈDE", "FROID"], key="p_filtre_temp")
    ordre = col_f5.selectbox("Trier par", ["score", "temperature", "date", "nom"], key="p_filtre_ordre")

    liste = crm.tous(
        statut=filtre_statut,
        niche=filtre_niche,
        ville=filtre_ville,
        temperature=filtre_temp,
        search=recherche,
        ordre=ordre
    )

    st.markdown(f"**{len(liste)} prospects trouvés**")

    if not liste:
        st.info("Aucun prospect ne correspond à vos filtres actuels. Modifiez les critères ou lancez un scan.")

    # Liste des prospects
    for p in liste:
        pid = p["id"]
        canal_info = f" via {p.get('canal_envoi', '?')}" if p.get("date_envoi") else ""
        badge_envoi = f" · ✉️ {duree_depuis(p.get('date_envoi'))}{canal_info}" if p.get("date_envoi") else ""
        if p.get("date_reponse"):
            badge_envoi += f" · 💬 {duree_depuis(p.get('date_reponse'))}"

        # ✅ lecture robuste des avis (une seule fois par prospect)
        avis_data = lire_avis(p)
        nb_avis_locaux = len(avis_data)

        # ✅ coordonnées visibles directement dans le titre
        contact_rapide = f" · 📞 {p['telephone']}" if p.get("telephone") else ""
        contact_rapide += f" · ✉️ {p['email']}" if p.get("email") else ""

        score_val = p.get('score', 0)
        titre = f"{p.get('temperature', '?')} **{p['nom']}** — {score_val} pts · {p.get('note', '?')}★ ({nb_avis_locaux} avis){contact_rapide}{badge_envoi}"

        # ✅ FIX : l'expander reste ouvert après un scrape de ce prospect
        with st.expander(titre, expanded=(st.session_state.get("dernier_scrape") == pid)):
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.caption(f"📍 {p.get('adresse', 'Adresse non renseignée')} | 🏷️ {p.get('niche', '—')} @ {p.get('ville', '—')}")
            with col_h2:
                st.markdown(badge_statut(p["statut"]), unsafe_allow_html=True)

            if p.get("raisons"):
                st.info(f"💡 **Raison du score:** {p.get('raisons')}")

            # --- COORDONNÉES ÉDITABLES ---
            st.markdown("##### 📞 Coordonnées")
            c1, c2, c3, c4 = st.columns(4)
            tel_val = c1.text_input("Téléphone", p.get("telephone") or "", key=f"t_{pid}")
            mail_val = c2.text_input("Email", p.get("email") or "", key=f"m_{pid}")
            insta_val = c3.text_input("Instagram", p.get("instagram") or "", key=f"i_{pid}")
            web_val = c4.text_input("Site Web", p.get("website") or "", key=f"w_{pid}")

            if any([
                tel_val != (p.get("telephone") or ""),
                mail_val != (p.get("email") or ""),
                insta_val != (p.get("instagram") or ""),
                web_val != (p.get("website") or "")
            ]):
                crm.update_field(pid, "telephone", tel_val)
                crm.update_field(pid, "email", mail_val)
                crm.update_field(pid, "instagram", insta_val)
                crm.update_field(pid, "website", web_val)
                st.success("✅ Coordonnées mises à jour")
                st.rerun()

            # --- LIENS D'ACTION DIRECTE ---
            accroche_actuelle = st.session_state.get(f"acc_{pid}", "")
            links = liens_contact(p, message_accroche=accroche_actuelle)
            if links:
                st.markdown("##### 🔗 Actions Directes")
                cols_l = st.columns(min(len(links), 5))
                for idx, (lab, url_act) in enumerate(links[:5]):
                    cols_l[idx].link_button(lab, url_act, use_container_width=True)

            st.markdown("---")

            # --- SCRAPING & DEEP ANALYSE IA ---
            st.markdown("##### 🧠 Intelligence Artificielle & Scraping")
            col_sc1, col_sc2 = st.columns(2)

            with col_sc1:
                if st.button("🕸️ Scraper Avis & Contacts Web", key=f"btn_scrap_{pid}", use_container_width=True):
                    with st.spinner("Scraping Google Maps & crawl du site web en cours..."):
                        try:
                            res = scrape_google_maps(p["nom"], p.get("adresse") or "", headless=headless_mode)
                            avis_scrapes = res.get("avis") or []
                            crm.update_field(pid, "notes", json.dumps(avis_scrapes, ensure_ascii=False))
                            crm.update_field(pid, "nb_avis", len(avis_scrapes) or p.get("nb_avis") or 0)

                            # ✅ Stockage tolérant aux différents noms de clés du scraper
                            tel_trouve = res.get("telephone") or res.get("phone") or res.get("tel")
                            web_trouve = res.get("website") or res.get("site_web") or res.get("site")
                            mail_trouve = res.get("email") or res.get("mail")
                            insta_trouve = res.get("instagram") or res.get("insta")
                            fb_trouve = res.get("facebook") or res.get("fb")

                            if tel_trouve:
                                crm.update_field(pid, "telephone", tel_trouve)
                            if mail_trouve:
                                crm.update_field(pid, "email", mail_trouve)
                            if web_trouve:
                                crm.update_field(pid, "website", web_trouve)
                            if insta_trouve:
                                crm.update_field(pid, "instagram", insta_trouve)
                            if fb_trouve:
                                crm.update_field(pid, "facebook", fb_trouve)

                            st.success(f"✅ {len(avis_scrapes)} avis et contacts synchronisés !")
                            # ✅ Récap des coordonnées extraites
                            st.markdown("**📇 Contacts extraits :**")
                            c_r1, c_r2 = st.columns(2)
                            c_r1.write(f"📞 {tel_trouve or '_non trouvé_'}")
                            c_r1.write(f"✉️ {mail_trouve or '_non trouvé_'}")
                            c_r2.write(f"🌐 {web_trouve or '_non trouvé_'}")
                            c_r2.write(f"📸 {insta_trouve or '_non trouvé_'} | 📘 {fb_trouve or '_non trouvé_'}")

                            # ✅ garder l'expander ouvert après le scrape
                            st.session_state["dernier_scrape"] = pid
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur scraping: {e}")

            with col_sc2:
                btn_txt = f"🧠 Deep Analyse IA ({nb_avis_locaux} avis)" if nb_avis_locaux else "🧠 Deep Analyse IA (Scrapez d'abord)"
                if st.button(btn_txt, key=f"btn_ai_{pid}", use_container_width=True, disabled=(nb_avis_locaux == 0)):
                    with st.spinner("🤖 Deep analyse IA en cours (Gemini avec fallback Groq)..."):
                        try:
                            res_ai = analyser_avis(p["nom"], avis_data)
                            crm.update_analyse(pid, res_ai)
                            st.success("✅ Analyse complétée avec succès !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur analyse: {e}")

            # Résultats de l'analyse
            try:
                analyse_data = json.loads(p.get("analyse_ia") or "{}")
            except (json.JSONDecodeError, TypeError):
                analyse_data = {}
            if analyse_data:
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.info(f"🎯 **Signal d'or :** {analyse_data.get('signal_or', '—')}")
                with col_res2:
                    st.success(f"⚖️ **Verdict :** {analyse_data.get('verdict', '—')}")
                if analyse_data.get("douleurs"):
                    st.caption(f"📌 **Douleurs récurrentes :** {', '.join(analyse_data.get('douleurs', []))}")

            st.markdown("---")

            # --- AFFICHAGE DES AVIS EXTRAITS (10 derniers, notes décimales gérées) ---
            st.markdown("##### 💬 Avis Extraits")
            if not avis_data:
                st.info("Aucun avis stocké pour ce prospect — lancez le scraping ci-dessus.")
            else:
                nb_reponses = sum(1 for a in avis_data if a.get("reponse_gerant") or a.get("reponse"))
                s1, s2, s3 = st.columns(3)
                s1.metric("Avis", nb_avis_locaux)
                s2.metric("Réponses gérant", f"{nb_reponses}/{nb_avis_locaux}")
                s3.metric("Sans réponse", f"{nb_avis_locaux - nb_reponses}/{nb_avis_locaux}")

                notes_dist = [a.get("note") for a in avis_data if a.get("note")]
                if notes_dist:
                    chart_data = {f"{n}★": notes_dist.count(n) for n in range(5, 0, -1)}
                    st.bar_chart(chart_data)

                st.caption(f"Affichage des {min(10, nb_avis_locaux)} derniers avis sur {nb_avis_locaux} extraits.")
                for a in avis_data[:10]:
                    icone = "🟢" if (a.get("reponse_gerant") or a.get("reponse")) else "🔴"
                    with st.expander(f"{icone} {etoiles(a.get('note'))} — {a.get('auteur', 'Anonyme')} ({a.get('date', a.get('date_relative', ''))})"):
                        st.write(a.get("texte") or a.get("contenu") or "_(avis sans texte)_")
                        rep = a.get("reponse_gerant") or a.get("reponse")
                        if rep:
                            st.caption(f"↩️ **Réponse du gérant :** {rep}")

            st.markdown("---")

            # --- OUTREACH & ACCROCHE IA ---
            st.markdown("##### ✍️ Message d'Accroche Personnalisé")
            col_out1, col_out2 = st.columns([2, 1])

            with col_out1:
                if st.button("✍️ Générer Accroche IA", key=f"btn_acc_{pid}", use_container_width=True):
                    with st.spinner("Rédaction de l'accroche ultra-ciblée..."):
                        p_full = {**p, "avis": avis_data}
                        if analyse_data:
                            p_full["angle_accroche"] = analyse_data.get("angle_accroche")
                        msg_gen = generer_accroche(p_full)
                        st.session_state[f"acc_{pid}"] = msg_gen
                        st.rerun()

            with col_out2:
                canal_choisi = st.selectbox("Canal d'envoi", ["WhatsApp", "Email", "Instagram", "Facebook", "Appel"], key=f"sel_can_{pid}")
                if st.button("✅ Marquer Envoyé", key=f"btn_send_{pid}", use_container_width=True):
                    crm.marquer_envoye(pid, canal_choisi)
                    st.success(f"✅ Prospect marqué envoyé via {canal_choisi}")
                    st.rerun()

            # Message éditable
            if st.session_state.get(f"acc_{pid}"):
                nouveau_msg = st.text_area("Message prêt à envoyer (éditable) :", st.session_state[f"acc_{pid}"], height=110, key=f"area_msg_{pid}")
                st.session_state[f"acc_{pid}"] = nouveau_msg

            # --- RETOURS GÉRANT & GESTION DES OBJECTIONS ---
            st.markdown("##### 💬 Réponse / Objection du Gérant")
            col_rep1, col_rep2 = st.columns([3, 1])
            with col_rep1:
                msg_client = st.text_input("Message reçu du gérant", placeholder="Ex: C'est combien vos prestations ?", key=f"in_rep_{pid}")
            with col_rep2:
                if st.button("🤖 Proposer Réponse", key=f"btn_prop_{pid}", use_container_width=True, disabled=not msg_client):
                    with st.spinner("Génération de la réponse adaptée..."):
                        reponse_ia = proposer_reponse(p, msg_client)
                        st.session_state[f"prop_{pid}"] = reponse_ia
                        crm.marquer_reponse(pid)
                        st.rerun()

            if st.session_state.get(f"prop_{pid}"):
                st.success("💡 **Suggestion de réponse IA :**")
                st.info(st.session_state[f"prop_{pid}"])

            st.markdown("---")

            # --- STATUT & SUPPRESSION ---
            col_bot1, col_bot2 = st.columns([3, 1])
            with col_bot1:
                idx_statut = statuts.index(p["statut"]) if p["statut"] in statuts else 0
                nouveau_statut = st.selectbox("Modifier le statut CRM", statuts, index=idx_statut, key=f"maj_statut_{pid}")
                if nouveau_statut != p["statut"]:
                    crm.update_field(pid, "statut", nouveau_statut)
                    st.success(f"Statut changé en '{nouveau_statut}'")
                    st.rerun()
            with col_bot2:
                if st.button("🗑️ Supprimer", key=f"del_{pid}", use_container_width=True):
                    crm.supprimer_prospect(pid)
                    st.warning(f"Prospect '{p['nom']}' supprimé.")
                    st.rerun()

# ============================================================
# 🔭 PAGE 3: SCANNER & COLLECTE
# ============================================================

elif page == "🔭 Scanner & Collecte":
    st.markdown('<p class="main-title">🔭 Scanner & Collecte Google Places</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Scannez des marchés locaux, extrayez les fiches et qualifiez vos cibles</p>', unsafe_allow_html=True)

    col_scan1, col_scan2 = st.columns([2, 1])

    with col_scan1:
        st.markdown("### 🎯 Configuration de la Recherche")
        niche_input = st.text_input("Type de commerce / Niche", "restaurant", placeholder="ex: restaurant, hôtel, salon de coiffure, clinique")
        ville_input = st.text_input("Ville ou Localité", "Antananarivo", placeholder="ex: Antananarivo, Paris, Bordeaux")
        nb_max = st.slider("Nombre maximum de résultats", min_value=3, max_value=20, value=10)

        if st.button("🚀 Lancer la Collecte & le Scoring", type="primary", use_container_width=True):
            if not PLACES_API_KEY:
                st.error("❌ PLACES_API_KEY n'est pas configurée dans le fichier .env !")
            else:
                with st.spinner(f"Recherche de '{niche_input}' à '{ville_input}' en cours..."):
                    try:
                        barre = st.progress(0)
                        commerces_trouves = chercher_commerces(niche_input, ville_input, max_resultats=nb_max)
                        total_trouves = len(commerces_trouves)
                        st.info(f"🔎 {total_trouves} commerces détectés sur Google Places.")

                        ajoutes = 0
                        for i, c in enumerate(commerces_trouves):
                            try:
                                fiche = recuperer_avis(c["id_place"])
                            except Exception:
                                fiche = {"nom": c["nom"], "avis": []}

                            fiche["nb_avis"] = fiche.get("nb_avis") or c.get("nb_avis", 0)
                            fiche["adresse"] = c.get("adresse", "")
                            fiche["id_place"] = c["id_place"]
                            fiche["nom"] = c["nom"]
                            fiche["niche"] = niche_input
                            fiche["ville"] = ville_input
                            fiche.update(scorer(fiche))
                            crm.upsert(fiche)
                            ajoutes += 1
                            barre.progress((i + 1) / max(total_trouves, 1))

                        crm.enregistrer_scan(niche_input, ville_input, ajoutes)
                        st.success(f"✅ {ajoutes} prospects qualifiés et enregistrés dans le CRM !")
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ Erreur lors du scan : {e}")

    with col_scan2:
        st.markdown("### 🕘 Derniers Scans Réalisés")
        scans = crm.historique_scans()
        if scans:
            for s in scans[:8]:
                st.markdown(
                    f"""<div style="background:var(--secondary-background-color);padding:8px 12px;border-radius:8px;margin-bottom:6px;border:1px solid rgba(128,128,160,0.15)">
                        <b>{s['niche']}</b> @ {s['ville']}<br>
                        <small>{s['nb_resultats']} résultats · {duree_depuis(s['date_scan'])}</small>
                    </div>""",
                    unsafe_allow_html=True
                )
        else:
            st.caption("Aucun scan enregistré pour l'instant.")


# ============================================================
# 📋 PAGE 4: BASE PROSPECTS & EXPORT
# ============================================================

elif page == "📋 Base Prospects & Export":
    st.markdown('<p class="main-title">📋 Base Prospects & Export</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Consultez l\'ensemble de vos prospects, exportez en CSV ou ajoutez des fiches manuelles</p>', unsafe_allow_html=True)

    tous_p = crm.tous(ordre="date")
    st.markdown(f"**Total en base : {len(tous_p)} prospects**")

    # Export CSV
    if tous_p:
        df_export = pd.DataFrame(tous_p)
        cols_drop = [c for c in ["notes", "analyse_ia"] if c in df_export.columns]
        df_clean = df_export.drop(columns=cols_drop)
        csv_data = df_clean.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

        st.download_button(
            label="📥 Télécharger la base en CSV (Compatible Excel)",
            data=csv_data,
            file_name=f"prospects_pro_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Tableau
        colonnes_affichees = [c for c in ["id", "nom", "niche", "ville", "score", "temperature", "statut", "note", "nb_avis", "telephone", "email", "website"] if c in df_clean.columns]
        st.dataframe(df_clean[colonnes_affichees], use_container_width=True, hide_index=True)

    # Formulaire ajout manuel
    with st.expander("➕ Ajouter un prospect manuellement"):
        with st.form("form_nouveau_prospect"):
            col_m1, col_m2 = st.columns(2)
            n_nom = col_m1.text_input("Nom du commerce *")
            n_ville = col_m1.text_input("Ville", "Antananarivo")
            n_niche = col_m1.text_input("Niche", "restaurant")
            n_adresse = col_m1.text_input("Adresse")

            n_tel = col_m2.text_input("Téléphone")
            n_mail = col_m2.text_input("Email")
            n_web = col_m2.text_input("Site Web")
            n_note = col_m2.number_input("Note Google (★)", min_value=0.0, max_value=5.0, value=4.2, step=0.1)

            submitted = st.form_submit_button("Ajouter à la base")
            if submitted:
                if not n_nom.strip():
                    st.error("Le nom du commerce est obligatoire !")
                else:
                    nouvelle_fiche = {
                        "nom": n_nom.strip(),
                        "ville": n_ville.strip(),
                        "niche": n_niche.strip(),
                        "adresse": n_adresse.strip(),
                        "telephone": n_tel.strip(),
                        "email": n_mail.strip(),
                        "website": n_web.strip(),
                        "note": n_note,
                        "nb_avis": 10,
                        "score": 50,
                        "temperature": "🌡️ TIÈDE",
                        "statut": "nouveau"
                    }
                    new_id = crm.ajouter_manuel(nouvelle_fiche)
                    st.success(f"✅ Prospect #{new_id} '{n_nom}' ajouté avec succès !")
                    st.rerun()


# ============================================================
# ⚙️ PAGE 5: DIAGNOSTICS IA & OUTILS
# ============================================================

else:
    st.markdown('<p class="main-title">⚙️ Diagnostics IA & Outils Système</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Vérifiez vos connexions API, les modèles actifs et l\'état du système</p>', unsafe_allow_html=True)

    ia = get_ia_client()

    st.markdown("### 🤖 Tests de Connectivité IA")
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown(f"#### Gemini (`{GEMINI_MODEL}`)")
        st.caption("Modèle d'analyse et de rédaction principal.")
        if st.button("🔌 Tester Gemini en direct", key="test_gemini_btn", use_container_width=True):
            with st.spinner("Test Gemini en cours..."):
                succes, msg = ia.test_gemini()
                if succes:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

    with col_t2:
        st.markdown(f"#### Groq Fallback (`{GROQ_MODEL}`)")
        st.caption("Modèle de secours à ultra-haute vitesse en cas de panne ou quota Gemini.")
        if st.button("⚡ Tester Groq en direct", key="test_groq_btn", use_container_width=True):
            with st.spinner("Test Groq en cours..."):
                succes, msg = ia.test_groq()
                if succes:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

    st.markdown("---")

    # Clés configurées
    st.markdown("### 🔑 Clés & Configuration")
    col_k1, col_k2, col_k3 = st.columns(3)

    def masquer_cle(k):
        if not k:
            return "❌ Non configurée"
        return f"✅ {k[:6]}...{k[-4:]}"

    col_k1.metric("Google Places API", "Configurée" if PLACES_API_KEY else "Manquante", masquer_cle(PLACES_API_KEY))
    col_k2.metric("Gemini API", "Configurée" if GEMINI_API_KEY else "Manquante", masquer_cle(GEMINI_API_KEY))
    col_k3.metric("Groq API (Fallback)", "Configurée" if GROQ_API_KEY else "Manquante", masquer_cle(GROQ_API_KEY))

    st.markdown("---")
    st.markdown("### 💾 Base de Données SQLite")
    stats = crm.stats_dashboard()
    col_db1, col_db2 = st.columns(2)
    col_db1.metric("Total fiches prospects", stats["total"])
    taille_db = f"{os.path.getsize(DB_PATH) / 1024:.1f} Ko" if os.path.exists(DB_PATH) else "Non trouvée"
    col_db2.metric("Taille du fichier base", taille_db, DB_PATH)
