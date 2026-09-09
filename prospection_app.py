"""
CRM Prospection - Edition Design (style dashboard pro, theme-adaptatif)
Lancement : ./lance.sh
"""
import json
import sqlite3
from datetime import datetime

import streamlit as st

from prospect import crm
from prospect.collecte import chercher_commerces, recuperer_avis
from prospect.scoring import scorer

st.set_page_config(page_title="CRM Prospection", page_icon="🎯", layout="wide")
crm.init()

# ============================================================
# 🎨 THEME CSS
# ============================================================

st.markdown("""<style>
/* --- Sidebar dégradée --- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e1e3f 0%, #16213e 100%);
}
[data-testid="stSidebar"] * { color: #e0e0ef !important; }
[data-testid="stSidebar"] .stButton > button {
    background: transparent; color: #cfcfe8 !important;
    border: none; border-radius: 10px; width: 100%;
    text-align: left; padding: 0.6rem 1rem; font-weight: 500;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.08);
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #5b6cff, #7b5bff);
    color: white !important; box-shadow: 0 4px 14px rgba(91,107,255,.4);
}

/* --- Cartes KPI --- */
div[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    border-radius: 16px; padding: 1.2rem 1.4rem;
    border: 1px solid rgba(128,128,160,0.18);
    box-shadow: 0 2px 10px rgba(30,30,63,0.08);
}
div[data-testid="stMetric"] label {
    color: var(--text-color) !important; opacity: 0.6; font-weight: 600;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-weight: 800; color: var(--text-color);
}

/* --- Expanders = cartes --- */
[data-testid="stExpander"] {
    background: var(--secondary-background-color);
    border-radius: 14px;
    border: 1px solid rgba(128,128,160,0.18);
}

/* --- Titre principal --- */
.main-title {
    background: linear-gradient(90deg, #5b6cff, #9b5bff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-weight: 800; font-size: 2rem; margin-bottom: 0;
}
.subtitle { opacity: 0.6; font-size: 0.95rem; }

/* --- Badges statuts --- */
.badge { padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.badge-nouveau   { background:rgba(99,102,241,0.15);  color:#818cf8; }
.badge-envoye    { background:rgba(245,158,11,0.15);  color:#f59e0b; }
.badge-repondu   { background:rgba(16,185,129,0.15);  color:#10b981; }
.badge-interesse { background:rgba(59,130,246,0.15);  color:#3b82f6; }
.badge-client    { background:rgba(34,197,94,0.18);   color:#22c55e; }
.badge-abandonne { background:rgba(128,128,140,0.15); color:var(--text-color); opacity:0.6; }

/* --- Alerts --- */
[data-testid="stAlert"] { border-radius: 12px; }
</style>""", unsafe_allow_html=True)


# ============================================================
# OUTILS
# ============================================================

def avis_de_prospect(pid):
    with sqlite3.connect(crm.DB) as con:
        raw = con.execute("SELECT notes FROM prospects WHERE id=?", (pid,)).fetchone()
    if raw and raw[0]:
        try:
            return json.loads(raw[0])
        except json.JSONDecodeError:
            return []
    return []


def sauver_avis(pid, avis):
    with sqlite3.connect(crm.DB) as con:
        con.execute("UPDATE prospects SET notes=? WHERE id=?",
                    (json.dumps(avis, ensure_ascii=False), pid))


def maj_coordonnees(pid, data: dict):
    with sqlite3.connect(crm.DB) as con:
        con.execute("""UPDATE prospects SET 
            telephone=?, website=?, email=?, instagram=?, facebook=?
            WHERE id=?""",
            (data.get("telephone"), data.get("website"), data.get("email"),
             data.get("instagram"), data.get("facebook"), pid))


def set_field(pid, champ, valeur):
    with sqlite3.connect(crm.DB) as con:
        con.execute(f"UPDATE prospects SET {champ}=? WHERE id=?", (valeur, pid))


def duree_depuis(date_str):
    if not date_str:
        return ""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return f"il y a {(datetime.now() - d).days} j"
    except ValueError:
        return ""


def badge_statut(statut):
    cls = {"nouveau": "nouveau", "envoyé": "envoye", "a répondu": "repondu",
           "intéressé": "interesse", "client": "client",
           "abandonné": "abandonne"}.get(statut, "nouveau")
    return f'<span class="badge badge-{cls}">{statut}</span>'


def barre_html(label, nb, max_v, couleur):
    pct = int(100 * nb / max_v) if max_v else 0
    return f"""<div style="margin:6px 0">
      <div style="display:flex;justify-content:space-between;
           font-size:13px;margin-bottom:2px">
      <span>{label}</span><b>{nb}</b></div>
      <div style="background:rgba(128,128,160,0.2);border-radius:6px;height:10px">
      <div style="background:{couleur};width:{pct}%;height:10px;
           border-radius:6px"></div></div></div>"""


def liens_contact(p):
    liens = []
    if p.get("telephone"):
        num = "".join(c for c in p["telephone"] if c.isdigit() or c == "+")
        liens.append(("💬 WhatsApp", f"https://wa.me/{num.lstrip('0')}"))
    if p.get("email"):
        liens.append(("✉️ Email", f"mailto:{p['email']}"))
    if p.get("website"):
        liens.append(("🌐 Site", p["website"]))
    if p.get("instagram"):
        liens.append(("📸 Insta", p["instagram"]))
    if p.get("facebook"):
        liens.append(("📘 FB", p["facebook"]))
    return liens


# ============================================================
# 🔻 SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("## 🎯 Prospection")
    st.caption("CRM Automatisé v3.0")

    page = st.radio("Navigation",
                    ["📊 Dashboard", "📋 Prospects", "🕘 Historique"],
                    label_visibility="collapsed")

    st.markdown("---")
    st.markdown("##### 🔭 Nouveau scan")
    req_niche = st.text_input("Niche", "restaurant", label_visibility="collapsed")
    req_ville = st.text_input("Ville", "Antananarivo", label_visibility="collapsed")
    
    if st.button("🚀 Lancer le scan", type="primary", use_container_width=True):
        with st.spinner("Scan en cours..."):
            n = 0
            for c in chercher_commerces(req_niche, req_ville):
                fiche = recuperer_avis(c["id_place"])
                fiche["nb_avis"] = fiche.get("nb_avis") or c["nb_avis"]
                fiche["adresse"] = c.get("adresse", "")
                fiche["id_place"] = c["id_place"]
                fiche["nom"] = c["nom"]
                fiche.update(scorer(fiche))
                crm.upsert(fiche)
                n += 1
            crm.enregistrer_scan(req_niche, req_ville, n)
        st.success(f"{n} prospects scorés ✅")
        st.rerun()

    st.markdown("---")
    headless = st.toggle("Mode invisible (Scraping)", value=True)
    st.caption("Activé = pas de fenêtre navigateur")

# ============================================================
# EN-TÊTE PRINCIPAL
# ============================================================

st.markdown(f'<p class="main-title">{page}</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Gestion de ta machine de vente</p>', unsafe_allow_html=True)

# ============================================================
# 📊 PAGE DASHBOARD
# ============================================================

if page == "📊 Dashboard":
    st_ds = crm.stats_dashboard()
    ps = st_ds["par_statut"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📁 Prospects", st_ds["total"])
    c2.metric("🔥 Chauds", st_ds["chauds"])
    envoyes = sum(ps.get(s, 0) for s in ["envoyé", "a répondu", "intéressé", "client"])
    c3.metric("✉️ Contactés", envoyes)
    c4.metric("💬 Réponses", ps.get("a répondu", 0))
    c5.metric("🤝 Clients", ps.get("client", 0))

    st.markdown("---")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### 📊 Pipeline")
        if st_ds["total"]:
            max_v = max(ps.values()) if ps else 1
            couleurs = {"nouveau": "#6b7280", "envoyé": "#f59e0b", "a répondu": "#10b981", "intéressé": "#3b82f6", "client": "#16a34a", "abandonné": "#9ca3af"}
            for statut, nb in sorted(ps.items(), key=lambda x: -x[1]):
                st.markdown(barre_html(statut, nb, max_v, couleurs.get(statut, "#5b6cff")), unsafe_allow_html=True)
    with g2:
        st.markdown("##### 🗺️ Top Niches")
        scans = crm.historique_scans()
        if scans:
            par_n = {}
            for s in scans: par_n[s["niche"]] = par_n.get(s["niche"], 0) + s["nb_resultats"]
            mv = max(par_n.values()) if par_n else 1
            for n, nb in sorted(par_n.items(), key=lambda x: -x[1])[:5]:
                st.markdown(barre_html(n, nb, mv, "#5b6cff"), unsafe_allow_html=True)

# ============================================================
# 📋 PAGE PROSPECTS
# ============================================================

elif page == "📋 Prospects":
    statuts = ["nouveau", "envoyé", "a répondu", "intéressé", "client", "abandonné"]
    col_f1, col_f2 = st.columns([2, 1])
    filtre_statut = col_f1.selectbox("Filtrer par statut", ["tous"] + statuts)
    
    liste = crm.tous(None if filtre_statut == "tous" else filtre_statut)

    if filtre_statut == "nouveau" and liste:
        if col_f2.button("🕸️ Tout extraire (Batch)", use_container_width=True):
            bar = st.progress(0)
            from prospect.collecte_web import extraire_avis
            for i, p in enumerate(liste):
                with st.status(f"Extraction {p['nom']}..."):
                    res = extraire_avis(p["nom"], p.get("adresse") or "", headless=headless)
                    sauver_avis(p["id"], res["avis"])
                    maj_coordonnees(p["id"], res)
                bar.progress((i + 1) / len(liste))
            st.success("Batch terminé ! ✅")
            st.rerun()

    if not liste:
        st.info("Aucun prospect. Lance un scan !")

    for p in liste:
        pid = p["id"]
        canal_info = f" via {p['canal_envoi']}" if p.get('canal_envoi') else ""
        badge_envoi = f" · ✉️ {duree_depuis(p['date_envoi'])}{canal_info}" if p.get("date_envoi") else ""
        if p.get("date_reponse"): badge_envoi += f" · 💬 {duree_depuis(p['date_reponse'])}"

        titre = f"{p['temperature']} **{p['nom']}** — {p['score']} pts · {p['note']}★{badge_envoi}"

        with st.expander(titre):
            st.caption(f"📍 {p.get('adresse') or '—'} | **Score :** {p['raisons'] or '—'}")
            st.markdown(badge_statut(p["statut"]), unsafe_allow_html=True)

            # Coordonnées
            c_coord = st.columns([1, 1, 1, 1])
            tel = c_coord[0].text_input("📞 Tél", p.get("telephone") or "", key=f"tel{pid}")
            mail = c_coord[1].text_input("✉️ Email", p.get("email") or "", key=f"mail{pid}")
            insta = c_coord[2].text_input("📸 Insta", p.get("instagram") or "", key=f"ins{pid}")
            web = c_coord[3].text_input("🌐 Web", p.get("website") or "", key=f"web_in{pid}")
            
            if any([tel != (p.get("telephone") or ""), mail != (p.get("email") or ""), 
                    insta != (p.get("instagram") or ""), web != (p.get("website") or "")]):
                maj_coordonnees(pid, {"telephone": tel, "email": mail, "instagram": insta, "website": web, "facebook": p.get("facebook")})
                st.rerun()

            # Actions rapides
            links = liens_contact(p)
            if links:
                cols_l = st.columns(len(links))
                for i, (lab, link) in enumerate(links):
                    cols_l[i].link_button(lab, link, use_container_width=True)

            # Analyse & Scraping
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🕸️ Extraire Avis/Web", key=f"scrap{pid}", use_container_width=True):
                    from prospect.collecte_web import extraire_avis
                    with st.spinner("Scraping..."):
                        res = extraire_avis(p["nom"], p.get("adresse") or "", headless=headless)
                        sauver_avis(pid, res["avis"])
                        maj_coordonnees(pid, res)
                    st.rerun()
            with col2:
                avis = avis_de_prospect(pid)
                if st.button("🧠 Deep Analyse IA", key=f"ai{pid}", use_container_width=True, disabled=not avis):
                    from prospect.analyse import analyser_avis
                    with st.spinner("Analyse IA..."):
                        res_ai = analyser_avis(p["nom"], avis)
                        crm.update_analyse(pid, res_ai)
                    st.rerun()

            # Affichage Analyse
            analyse_data = json.loads(p["analyse_ia"]) if p.get("analyse_ia") else None
            if analyse_data:
                st.info(f"**Signal OR :** {analyse_data.get('signal_or')}")
                st.markdown(f"**Verdict :** {analyse_data.get('verdict')}")
                st.caption(f"Douleurs : {', '.join(analyse_data.get('douleurs', []))}")

            # Prospection
            st.markdown("---")
            p_col1, p_col2 = st.columns([2, 1])
            with p_col1:
                if st.button("✍️ Générer Accroche", key=f"acc{pid}", use_container_width=True):
                    from prospect.accroches import generer_accroche
                    p_full = {**p, "avis": avis}
                    if analyse_data: p_full["angle_accroche"] = analyse_data.get("angle_accroche")
                    st.session_state[f"acc_{pid}"] = generer_accroche(p_full)
            
            with p_col2:
                canal = st.selectbox("Canal d'envoi", ["WhatsApp", "Email", "Instagram", "Facebook", "Appel"], key=f"can{pid}")
                if st.button("✅ Marquer Envoyé", key=f"send{pid}", use_container_width=True):
                    crm.marquer_envoye(pid, canal)
                    st.rerun()

            if st.session_state.get(f"acc_{pid}"):
                msg = st.text_area("Message à copier", st.session_state[f"acc_{pid}"], height=150, key=f"msg{pid}")
                st.code(msg, language=None)

            # Réponses
            if p["statut"] == "a répondu":
                st.markdown("---")
                msg_r = st.text_area("Réponse du gérant :", key=f"re_ge{pid}")
                if st.button("🤖 Proposer réponse", key=f"prop_ai{pid}"):
                    from prospect.reponses import proposer_reponse
                    st.session_state[f"p_{pid}"] = proposer_reponse(p, msg_r)
                if st.session_state.get(f"p_{pid}"):
                    st.success("Proposition :")
                    st.write(st.session_state[f"p_{pid}"])

# ============================================================
# 🕘 PAGE HISTORIQUE
# ============================================================

else:
    st.markdown("##### 🕘 Historique des scans")
    for s in crm.historique_scans():
        st.markdown(f"- **{s['niche']}** à {s['ville']} : {s['nb_resultats']} prospects ({s['date_scan']})")
    
    st.markdown("---")
    st.markdown("##### 📅 Journal des contacts")
    for p in [p for p in crm.tous() if p.get("date_envoi")]:
        st.markdown(f"- {p['nom']} ({p['temperature']}) : envoyé via **{p['canal_envoi'] or '?'}** le {p['date_envoi']}")
