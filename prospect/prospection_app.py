"""
CRM Prospection - Interface Pro v4.0
Dashboard CRM complet avec gestion par niche, filtrage avancé, et prospection optimisée.
Lancement : streamlit run prospection_app.py
"""
import json
import sqlite3
from datetime import datetime

import streamlit as st

from prospect import crm
from prospect.collecte import chercher_commerces, recuperer_avis
from prospect.scoring import scorer
from prospect.scraper_maps import scrape_google_maps
from prospect.accroches import generer_accroche
from prospect.analyse import analyser_avis
from prospect.config import get_logger

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
# 🎨 THEME CSS PROFESSIONNEL
# ============================================================

st.markdown("""<style>
/* === VARIABLES === */
:root {
    --primary: #5b6cff;
    --primary-dark: #4a5acc;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --text-primary: #1f2937;
    --text-secondary: #6b7280;
    --bg-light: #f9fafb;
    --border: #e5e7eb;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e1e3f 0%, #16213e 100%) !important;
}
[data-testid="stSidebar"] * { color: #e0e0ef !important; }
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #cfcfe8 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    width: 100% !important;
    text-align: left !important;
    padding: 0.7rem 1rem !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(91,107,255,0.15) !important;
    border-color: #5b6cff !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #5b6cff, #7b5bff) !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(91,107,255,.4) !important;
}

/* === MÉTRIQUES === */
div[data-testid="stMetric"] {
    background: white !important;
    border-radius: 12px !important;
    padding: 1.5rem !important;
    border: 1px solid var(--border) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}
div[data-testid="stMetric"] label {
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    font-size: 2rem !important;
}

/* === EXPANDERS/CARTES === */
[data-testid="stExpander"] {
    background: white !important;
    border-radius: 12px !important;
    border: 1px solid var(--border) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

/* === TITRES === */
h1, h2, h3 {
    color: var(--text-primary) !important;
}

.main-title {
    background: linear-gradient(90deg, #5b6cff, #9b5bff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 2.2rem;
    margin-bottom: 0.5rem;
}

.subtitle {
    color: var(--text-secondary);
    font-size: 1rem;
}

/* === BADGES === */
.badge {
    padding: 0.35rem 0.75rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-block;
}
.badge-nouveau   { background: rgba(99,102,241,0.15); color: #818cf8; }
.badge-envoye    { background: rgba(245,158,11,0.15); color: #f59e0b; }
.badge-repondu   { background: rgba(16,185,129,0.15); color: #10b981; }
.badge-interesse { background: rgba(59,130,246,0.15); color: #3b82f6; }
.badge-client    { background: rgba(34,197,94,0.15);  color: #22c55e; }
.badge-abandonne { background: rgba(128,128,140,0.15); color: #6b7280; }

/* === BARRES DE PROGRESSION === */
.progress-bar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin: 0.75rem 0;
}
.progress-label { font-size: 0.9rem; font-weight: 500; color: var(--text-primary); }
.progress-container {
    flex: 1;
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #5b6cff, #7b5bff);
    transition: width 0.3s;
}
.progress-value { font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); }

/* === ALERTES === */
[data-testid="stAlert"] {
    border-radius: 12px !important;
}

/* === SECTIONS === */
.section-header {
    padding: 1rem 0 0.5rem 0;
    border-bottom: 2px solid var(--border);
    margin-bottom: 1rem;
}

.prospect-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: all 0.2s;
}
.prospect-card:hover {
    box-shadow: 0 4px 12px rgba(91,107,255,0.1);
    border-color: #5b6cff;
}

</style>""", unsafe_allow_html=True)

# ============================================================
# UTILITIES
# ============================================================

def duree_depuis(date_str):
    """Calcule la durée depuis une date."""
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


def liens_contact(p):
    """Retourne les liens de contact."""
    liens = []
    if p.get("telephone"):
        num = "".join(c for c in p["telephone"] if c.isdigit() or c == "+")
        liens.append(("💬 WhatsApp", f"https://wa.me/{num.lstrip('0')}"))
    if p.get("email"):
        liens.append(("✉️ Email", f"mailto:{p['email']}"))
    if p.get("website"):
        liens.append(("🌐 Site", p["website"]))
    if p.get("instagram"):
        liens.append(("📸 Instagram", p["instagram"]))
    if p.get("facebook"):
        liens.append(("📘 Facebook", p["facebook"]))
    return liens


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown("## 🎯 PROSPECTION PRO")
    st.caption("CRM Automatisé v4.0")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["📊 Dashboard", "🎯 Prospection", "📋 Prospects", "🕘 Historique"],
        label_visibility="collapsed",
        key="main_nav"
    )

    st.markdown("---")
    st.markdown("### 🔭 Nouveau Scan")

    scan_niche = st.text_input("Niche", "restaurant", label_visibility="collapsed", key="scan_niche")
    scan_ville = st.text_input("Ville", "Antananarivo", label_visibility="collapsed", key="scan_ville")

    if st.button("🚀 Lancer le Scan", type="primary", use_container_width=True):
        with st.spinner("📡 Scan en cours..."):
            try:
                n = 0
                progress_bar = st.progress(0)
                for i, c in enumerate(chercher_commerces(scan_niche, scan_ville)):
                    fiche = recuperer_avis(c["id_place"])
                    fiche["nb_avis"] = fiche.get("nb_avis") or c["nb_avis"]
                    fiche["adresse"] = c.get("adresse", "")
                    fiche["id_place"] = c["id_place"]
                    fiche["nom"] = c["nom"]
                    fiche["niche"] = scan_niche
                    fiche["ville"] = scan_ville
                    fiche.update(scorer(fiche))
                    crm.upsert(fiche)
                    n += 1
                    progress_bar.progress((i + 1) / 10)  # Max 10 results
                crm.enregistrer_scan(scan_niche, scan_ville, n)
                st.success(f"✅ {n} prospects scorés et sauvegardés!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur scan: {e}")
                logger.error(f"Scan error: {e}")

    st.markdown("---")
    headless_mode = st.toggle("🌐 Mode invisible (Scraping)", value=True)
    st.caption("Activé = pas de fenêtre navigateur visible")

# ============================================================
# 📊 PAGE DASHBOARD
# ============================================================

if page == "📊 Dashboard":
    st.markdown('<p class="main-title">📊 Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Vue d\'ensemble de votre prospection</p>', unsafe_allow_html=True)

    stats = crm.stats_dashboard()
    ps = stats["par_statut"]

    # Métriques principales
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("📁 Prospects", stats["total"])
    col2.metric("🔥 Chauds", stats["chauds"])
    envoyes = sum(ps.get(s, 0) for s in ["envoyé", "a répondu", "intéressé", "client"])
    col3.metric("✉️ Contactés", envoyes)
    col4.metric("💬 Réponses", ps.get("a répondu", 0))
    col5.metric("🤝 Clients", ps.get("client", 0))

    st.markdown("---")

    # Pipeline et Niches
    col_pipeline, col_niches = st.columns(2)

    with col_pipeline:
        st.markdown("### 📊 Pipeline Général")
        if stats["total"]:
            max_v = max(ps.values()) if ps else 1
            couleurs = {
                "nouveau": "#6b7280",
                "envoyé": "#f59e0b",
                "a répondu": "#10b981",
                "intéressé": "#3b82f6",
                "client": "#16a34a",
                "abandonné": "#9ca3af"
            }
            for statut, nb in sorted(ps.items(), key=lambda x: -x[1]):
                st.markdown(
                    barre_progress(statut, nb, max_v, couleurs.get(statut, "#5b6cff")),
                    unsafe_allow_html=True
                )
        else:
            st.info("Aucun prospect encore. Lancez un scan!")

    with col_niches:
        st.markdown("### 🏷️ Top Niches")
        par_niche = stats.get("par_niche", {})
        if par_niche:
            max_v = max(par_niche.values()) if par_niche else 1
            for niche, nb in sorted(par_niche.items(), key=lambda x: -x[1])[:5]:
                st.markdown(
                    barre_progress(niche, nb, max_v, "#5b6cff"),
                    unsafe_allow_html=True
                )
        else:
            st.info("Aucune niche scanée encore")

# ============================================================
# 🎯 PAGE PROSPECTION
# ============================================================

elif page == "🎯 Prospection":
    st.markdown('<p class="main-title">🎯 Prospection</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Gérez vos prospects par niche et statut</p>', unsafe_allow_html=True)

    # Filtres avancés
    col_f1, col_f2, col_f3 = st.columns(3)

    niches = crm.get_niches()
    filtre_niche = col_f1.selectbox("Niche", ["toutes"] + niches, key="filter_niche")

    statuts = ["nouveau", "envoyé", "a répondu", "intéressé", "client", "abandonné"]
    filtre_statut = col_f2.selectbox("Statut", ["tous"] + statuts, key="filter_statut")

    ordre = col_f3.selectbox("Trier par", ["score", "temperature", "date"], key="filter_order")

    # Récupérer les prospects
    niche_param = None if filtre_niche == "toutes" else filtre_niche
    statut_param = None if filtre_statut == "tous" else filtre_statut
    liste = crm.tous(statut=statut_param, niche=niche_param, ordre=ordre)

    # Stats de la sélection
    if liste:
        st.markdown(f"**{len(liste)} prospects trouvés**")
    else:
        st.info("Aucun prospect ne correspond à ces critères.")

    # Affichage des prospects
    for p in liste:
        pid = p["id"]
        canal_info = f" via {p.get('canal_envoi', '?')}" if p.get("date_envoi") else ""
        badge_envoi = f" · ✉️ {duree_depuis(p.get('date_envoi'))}{canal_info}" if p.get("date_envoi") else ""
        if p.get("date_reponse"):
            badge_envoi += f" · 💬 {duree_depuis(p.get('date_reponse'))}"

        titre = f"{p.get('temperature', '?')} **{p['nom']}** — {p['score']}pts · {p.get('note', '?')}★{badge_envoi}"

        with st.expander(titre, expanded=False):
            col_header = st.columns([3, 1])
            with col_header[0]:
                st.caption(f"📍 {p.get('adresse', '—')} | 🏷️ {p.get('niche', '—')} @ {p.get('ville', '—')}")
            with col_header[1]:
                st.markdown(badge_statut(p["statut"]), unsafe_allow_html=True)

            st.markdown(f"**Raison du score:** {p.get('raisons', '—')}")

            # === COORDONNEES ===
            st.markdown("#### 📞 Coordonnées")
            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            tel = col_c1.text_input("Tél", p.get("telephone") or "", key=f"tel{pid}")
            mail = col_c2.text_input("Email", p.get("email") or "", key=f"mail{pid}")
            insta = col_c3.text_input("Instagram", p.get("instagram") or "", key=f"ins{pid}")
            web = col_c4.text_input("Site web", p.get("website") or "", key=f"web{pid}")

            if any([
                tel != (p.get("telephone") or ""),
                mail != (p.get("email") or ""),
                insta != (p.get("instagram") or ""),
                web != (p.get("website") or "")
            ]):
                crm.update_field(pid, "telephone", tel)
                crm.update_field(pid, "email", mail)
                crm.update_field(pid, "instagram", insta)
                crm.update_field(pid, "website", web)
                st.success("✅ Coordonnées mises à jour")
                st.rerun()

            # === LIENS DE CONTACT ===
            links = liens_contact(p)
            if links:
                st.markdown("#### 🔗 Canaux de contact")
                cols_l = st.columns(len(links))
                for i, (lab, link) in enumerate(links):
                    cols_l[i].link_button(lab, link, use_container_width=True)

            # === SCRAPING & ANALYSE ===
            st.markdown("#### 🧠 Analyse & Scraping")
            col_scrap1, col_scrap2 = st.columns(2)

            with col_scrap1:
                if st.button("🕸️ Scraper Avis/Web", key=f"scrap{pid}", use_container_width=True):
                    with st.spinner("🔄 Scraping en cours..."):
                        try:
                            res = scrape_google_maps(p["nom"], p.get("adresse") or "", headless=headless_mode)
                            crm.update_field(pid, "notes", json.dumps(res.get("avis", [])))
                            crm.update_field(pid, "telephone", res.get("telephone") or p.get("telephone"))
                            crm.update_field(pid, "email", res.get("email") or p.get("email"))
                            crm.update_field(pid, "website", res.get("website") or p.get("website"))
                            crm.update_field(pid, "instagram", res.get("instagram") or p.get("instagram"))
                            crm.update_field(pid, "facebook", res.get("facebook") or p.get("facebook"))
                            st.success(f"✅ {len(res.get('avis', []))} avis scrapés")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur scraping: {e}")

            with col_scrap2:
                avis = json.loads(p.get("notes") or "[]")
                if st.button("🧠 Deep Analyse IA", key=f"ai{pid}", use_container_width=True, disabled=not avis):
                    with st.spinner("🤖 Analyse IA en cours..."):
                        try:
                            res_ai = analyser_avis(p["nom"], avis)
                            crm.update_analyse(pid, res_ai)
                            st.success("✅ Analyse complétée")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur analyse: {e}")

            # === AFFICHAGE ANALYSE ===
            analyse_data = json.loads(p.get("analyse_ia") or "{}")
            if analyse_data:
                st.markdown("#### 📊 Résultats Analyse")
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    st.info(f"🎯 **Signal OR:** {analyse_data.get('signal_or', 'N/A')}")
                with col_a2:
                    st.success(f"✅ **Verdict:** {analyse_data.get('verdict', 'N/A')}")
                
                if analyse_data.get("douleurs"):
                    st.caption(f"📌 Douleurs: {', '.join(analyse_data.get('douleurs', []))}")

            # === PROSPECTION ===
            st.markdown("#### ✍️ Prospection")
            col_p1, col_p2 = st.columns([2, 1])

            with col_p1:
                if st.button("✍️ Générer Accroche", key=f"acc{pid}", use_container_width=True):
                    p_full = {**p, "avis": avis}
                    if analyse_data:
                        p_full["angle_accroche"] = analyse_data.get("angle_accroche")
                    st.session_state[f"acc_{pid}"] = generer_accroche(p_full)
                    st.rerun()

            with col_p2:
                canal = st.selectbox(
                    "Canal",
                    ["WhatsApp", "Email", "Instagram", "Facebook", "Appel"],
                    key=f"can{pid}"
                )
                if st.button("✅ Marquer Envoyé", key=f"send{pid}", use_container_width=True):
                    crm.marquer_envoye(pid, canal)
                    st.success("✅ Marqué comme envoyé")
                    st.rerun()

            # === MESSAGE ===
            if st.session_state.get(f"acc_{pid}"):
                msg = st.text_area(
                    "Message à copier",
                    st.session_state[f"acc_{pid}"],
                    height=120,
                    key=f"msg{pid}"
                )
                st.code(msg, language=None)

            # === REPONSES ===
            if p["statut"] in ["a répondu", "intéressé"]:
                st.markdown("#### 💬 Réponse du gérant")
                msg_r = st.text_area("Message reçu", key=f"msg_r{pid}", height=80)
                if msg_r and st.button("🤖 Proposer réponse IA", key=f"prop_ai{pid}"):
                    from prospect.reponses import proposer_reponse
                    with st.spinner("🤖 Génération réponse..."):
                        try:
                            st_session_key = f"p_{pid}"
                            st.session_state[st_session_key] = proposer_reponse(p, msg_r)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur: {e}")

                if st.session_state.get(f"p_{pid}"):
                    st.success("💡 Proposition IA:")
                    st.info(st.session_state[f"p_{pid}"])

# ============================================================
# 📋 PAGE PROSPECTS
# ============================================================

elif page == "📋 Prospects":
    st.markdown('<p class="main-title">📋 Vue Prospects</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Gestion complète de votre base</p>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🔥 Chauds", "🌡️ Tous", "📊 Stats"])

    with tab1:
        chauds = [p for p in crm.tous() if "CHAUD" in p.get("temperature", "")]
        if chauds:
            st.markdown(f"**{len(chauds)} prospects chauds** 🔥")
            for p in chauds[:20]:
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**{p['nom']}** • {p['score']}pts • {p.get('niche', '?')} @ {p.get('ville', '?')}")
                with col_b:
                    st.caption(badge_statut(p["statut"]))
        else:
            st.info("Aucun prospect chaud pour l'instant")

    with tab2:
        tous_prospects = crm.tous()
        st.markdown(f"**{len(tous_prospects)} prospects au total**")
        if tous_prospects:
            # Afficher en tableau
            data = [
                {
                    "Nom": p["nom"],
                    "Score": p["score"],
                    "Niche": p.get("niche", "—"),
                    "Ville": p.get("ville", "—"),
                    "Statut": p["statut"],
                    "Note": f"{p.get('note', '?')}★",
                }
                for p in tous_prospects[:50]
            ]
            st.dataframe(data, use_container_width=True, hide_index=True)

    with tab3:
        stats = crm.stats_dashboard()
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric("Total", stats["total"])
            st.metric("Chauds", stats["chauds"])
        with col_s2:
            st.metric("Envoyés", sum(stats["par_statut"].get(s, 0) for s in ["envoyé", "a répondu", "intéressé", "client"]))
            st.metric("Clients", stats["par_statut"].get("client", 0))

# ============================================================
# 🕘 PAGE HISTORIQUE
# ============================================================

else:
    st.markdown('<p class="main-title">🕘 Historique</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Traces de vos scans et contacts</p>', unsafe_allow_html=True)

    tab_scans, tab_contacts = st.tabs(["📊 Scans", "📧 Contacts"])

    with tab_scans:
        st.markdown("#### Historique des scans")
        scans = crm.historique_scans()
        if scans:
            for s in scans[:20]:
                st.markdown(
                    f"🔍 **{s['niche']}** @ {s['ville']} — "
                    f"{s['nb_resultats']} prospects — {duree_depuis(s['date_scan'])}"
                )
        else:
            st.info("Aucun scan effectué")

    with tab_contacts:
        st.markdown("#### Journal des contacts")
        contacts = [p for p in crm.tous() if p.get("date_envoi")]
        if contacts:
            for p in contacts[:50]:
                st.markdown(
                    f"📧 **{p['nom']}** ({p.get('temperature', '?')}) — "
                    f"Envoyé via **{p.get('canal_envoi', '?')}** {duree_depuis(p.get('date_envoi'))}"
                )
        else:
            st.info("Aucun contact envoyé pour l'instant")
