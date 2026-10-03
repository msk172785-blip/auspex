"""DÛ — interface locale (Streamlit).

Lancement : streamlit run app.py
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from du_engine import calculations as calc  # noqa: E402
from du_engine.corpus import analyze_case, load_case  # noqa: E402
from du_engine.pdf_reader import read_pdf  # noqa: E402
from du_engine.pipeline import analyze_pdfs  # noqa: E402
from du_engine.storage import (list_uploads, load_validations, save_analysis, save_upload,  # noqa: E402
                               save_validation)

SIM_DIR = ROOT / "data" / "simulated"
SIM_BANNER = "Exemple simulé — aucune somme réelle n'est réclamée."
PAGES = ["1 · Analyser un marché", "2 · Vue d'ensemble", "3 · Alertes DÛ", "4 · Preuves", "Exemples simulés", "Évaluation"]
SEV = {"critical": ("CRITICAL", "#b42318", "#fef3f2"), "high": ("HIGH", "#b54708", "#fffaeb"),
       "medium": ("MEDIUM", "#175cd3", "#eff8ff"), "info": ("INFO", "#475467", "#f9fafb")}
STATUS_FR = {"AUTO_EXTRACTED": "Extraction automatique (non validée)", "REVIEW_REQUIRED": "REVUE REQUISE",
             "NOT_FOUND": "Non trouvé", "USER_INPUT": "Saisie utilisateur", "VALIDATED": "VALIDÉ par un humain"}
FIELD_FR = {
    "contract_id": "N° de marché", "buyer": "Acheteur", "supplier": "Fournisseur / titulaire", "contract_title": "Objet",
    "contract_start_date": "Date de début", "contract_end_date": "Date de fin (calculée)", "annual_amount": "Montant annuel",
    "contract_duration": "Durée", "price_type": "Type de prix", "revision_exists": "Révision prévue",
    "revision_type": "Type de révision", "revision_formula": "Formule de révision", "revision_index": "Indice(s)",
    "base_index": "Indice de base", "revision_frequency": "Fréquence de révision", "revision_trigger": "Déclencheur",
    "supplier_action_required": "Action du fournisseur requise", "supplier_action_description": "Action à mener",
    "deadline_rule": "Règle de délai", "calculated_deadline": "Échéance calculée", "forfeiture_exists": "Forclusion",
    "forfeiture_consequence": "Conséquence en cas d'oubli", "cap_exists": "Plafond", "cap_value": "Valeur du plafond",
    "threshold_exists": "Seuil", "threshold_value": "Valeur du seuil", "purchase_orders_exist": "Bons de commande",
    "variable_services_exist": "Prestations variables", "amendments_exist": "Avenants fournis",
    "retention_exists": "Retenue de garantie", "retention_rate": "Taux de retenue", "retention_release_rule": "Règle de libération",
    "payment_terms": "Délai de paiement", "late_payment_interest": "Intérêts moratoires", "advance_payment": "Avance",
    "guarantee_period_months": "Délai de garantie (mois)", "final_balance_rule": "Solde / décompte final",
}

st.set_page_config(page_title="DÛ — Revenue Assurance marchés publics", page_icon="⚖️", layout="wide")
ss = st.session_state
ss.setdefault("page", PAGES[0])
ss.setdefault("analysis", None)
ss.setdefault("pdf_paths", [])
ss.setdefault("folder", None)
ss.setdefault("selected_event", 0)


def goto(page: str, event_idx: int | None = None):
    # appliqué au prochain run, avant l'instanciation du widget de navigation
    ss["_next_page"] = page
    if event_idx is not None:
        ss.selected_event = event_idx


@st.cache_data(show_spinner=False)
def page_texts(paths: tuple[str, ...]) -> dict:
    out = {}
    for p in paths:
        d = read_pdf(p)
        for pg in d.pages:
            out[(d.name, pg.page)] = pg.text
    return out


def fmt_value(name, v):
    if v is None:
        return "—"
    if name == "annual_amount":
        try:
            return calc.fmt_eur(v)
        except Exception:
            return str(v)
    if isinstance(v, bool):
        return "Oui" if v else "Non"
    if name in ("contract_start_date", "contract_end_date", "calculated_deadline"):
        try:
            return date.fromisoformat(str(v)).strftime("%d/%m/%Y")
        except ValueError:
            return str(v)
    if name == "contract_duration" and isinstance(v, dict):
        s = f"{v.get('initial_months')} mois"
        if v.get("renewals"):
            s += f", reconductible {v['renewals']} fois (max {v.get('max_months')} mois)"
        return s
    if name == "revision_index" and isinstance(v, dict):
        return ", ".join(v.get("names", []) + [f"id {i}" for i in v.get("identifiers", [])])
    if name == "deadline_rule" and isinstance(v, dict):
        return v.get("text", str(v))
    if name == "payment_terms" and isinstance(v, dict):
        return f"{v.get('days')} jours"
    if name == "threshold_value" and isinstance(v, dict):
        return f"{v.get('pct')} % ({v.get('kind')})"
    if name == "forfeiture_consequence" and isinstance(v, dict):
        return v.get("text", "")
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def source_label(ev: dict) -> str:
    parts = [ev["document"]]
    if ev.get("article"):
        parts.append(f"article {ev['article']}")
    parts.append(f"page {ev['page']}")
    return " — ".join(parts)


def run_analysis(pdf_paths, user_inputs, recon, ref_date, folder=None, simulated=False, key="contract"):
    a = analyze_pdfs(pdf_paths, user_inputs=user_inputs, recon=recon, reference_date=ref_date, simulated=simulated,
                     contract_key=key)
    d = a.to_dict()
    if folder:
        save_analysis(folder, d)
    ss.analysis = d
    ss.pdf_paths = [str(p) for p in pdf_paths]
    ss.folder = str(folder) if folder else None
    ss.selected_event = 0


def sim_banner():
    a = ss.analysis
    if a and a.get("SIMULATED_EXAMPLE"):
        st.markdown(f"<div style='background:#fef0c7;border:2px solid #dc6803;padding:10px 14px;border-radius:8px;"
                    f"font-weight:700;color:#7a2e0e;margin-bottom:12px'>EXEMPLE SIMULÉ — aucune somme réelle n'est réclamée.</div>",
                    unsafe_allow_html=True)


def need_analysis() -> bool:
    if not ss.analysis:
        st.info("Aucune analyse en cours. Déposez un PDF (page 1) ou chargez un exemple simulé.")
        return False
    return True


def effective_status(key: str, status: str) -> str:
    if ss.folder:
        v = load_validations(Path(ss.folder)).get(key)
        if v:
            return "VALIDATED" if v["decision"] == "VALIDATED" else f"REJETÉ par un humain ({v.get('comment', '')})"
    return status


# ------------------------------------------------------------------ navigation
if "_next_page" in ss:
    ss.page = ss.pop("_next_page")
with st.sidebar:
    st.markdown("## DÛ")
    st.caption("Revenue Assurance pour fournisseurs de marchés publics — prototype v0 local")
    st.radio("Navigation", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    prev = list_uploads()
    if prev:
        choice = st.selectbox("Analyses enregistrées", ["—"] + [p.name for p in prev])
        if choice != "—" and st.button("Recharger cette analyse"):
            folder = next(p for p in prev if p.name == choice)
            case = load_case(folder)
            run_analysis(case["pdfs"], case["meta"].get("user_inputs", {}), case["recon"], date.today(), folder,
                         key=folder.name)
            goto(PAGES[1])
            st.rerun()
    st.caption("Aucune donnée n'est envoyée hors de cette machine. Aucun modèle de langage n'est utilisé.")

page = ss.page

# ------------------------------------------------------------------ PAGE 1
if page == PAGES[0]:
    st.title("Analysez votre marché public")
    st.write("Déposez le CCAP (et éventuellement acte d'engagement, CCP, avenants). DÛ extrait les clauses financières, "
             "cite la page et l'extrait exact, et calcule les échéances de façon déterministe.")
    files = st.file_uploader("Documents PDF du marché", type=["pdf"], accept_multiple_files=True)
    st.subheader("Informations facultatives")
    st.caption("Laissez vide ce que vous ne savez pas : DÛ ne devine jamais une donnée manquante, il la signale.")
    c1, c2 = st.columns(2)
    title = c1.text_input("Nom du marché")
    buyer = c2.text_input("Acheteur")
    supplier = c1.text_input("Fournisseur (titulaire)")
    amount_s = c2.text_input("Montant annuel HT (€)", placeholder="ex. 220000")
    start = c1.date_input("Date de début du contrat (ou de notification)", value=None, format="DD/MM/YYYY")
    ref_date = c2.date_input("Date de référence du calcul", value=date.today(), format="DD/MM/YYYY")
    with st.expander("Révision : coefficient ou valeurs d'indices (facultatif)"):
        st.caption("DÛ ne télécharge pas les indices INSEE. Saisissez soit le coefficient, soit I0 et In.")
        k1, k2, k3 = st.columns(3)
        coef_s = k1.text_input("Coefficient de révision", placeholder="ex. 1,03")
        i0_s = k2.text_input("Indice de base I0")
        in_s = k3.text_input("Dernier indice In")
    with st.expander("Rapprochement factures / bons de commande / retenue (P2, JSON facultatif)"):
        st.caption("Formats : voir README, section Données de rapprochement.")
        inv_f = st.file_uploader("invoices.json", type=["json"], key="inv")
        po_f = st.file_uploader("purchase_orders.json", type=["json"], key="po")
        rt_f = st.file_uploader("retention.json", type=["json"], key="rt")

    if st.button("Analyser", type="primary", disabled=not files):
        def num(s):
            return calc.to_decimal_or_none(s) if s else None
        errors = []
        user = {"contract_title": title or None, "buyer": buyer or None, "supplier": supplier or None,
                "contract_start_date": start.isoformat() if start else None}
        for key, s in [("annual_amount", amount_s), ("revision_coefficient", coef_s), ("index_base", i0_s), ("index_new", in_s)]:
            if s:
                v = num(s)
                if v is None:
                    errors.append(f"Valeur numérique invalide : {s}")
                else:
                    user[key] = float(v)
        recon = {}
        try:
            if inv_f:
                recon["invoices"] = json.load(inv_f)["invoices"]
            if po_f:
                recon["purchase_orders"] = json.load(po_f)["purchase_orders"]
            if rt_f:
                recon["retention"] = json.load(rt_f)
        except (json.JSONDecodeError, KeyError) as exc:
            errors.append(f"Fichier JSON invalide : {exc}")
        if errors:
            for e in errors:
                st.error(e)
        else:
            folder = save_upload([(f.name, f.getvalue()) for f in files],
                                 {"contract_title": title, "user_inputs": {k: v for k, v in user.items() if v is not None}})
            for name, obj in [("invoices.json", {"invoices": recon.get("invoices")}),
                              ("purchase_orders.json", {"purchase_orders": recon.get("purchase_orders")}),
                              ("retention.json", recon.get("retention"))]:
                if obj and any(v for v in (obj.values() if isinstance(obj, dict) else [obj])):
                    (folder / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            with st.spinner("Lecture et extraction…"):
                run_analysis(sorted(folder.glob("*.pdf")), user, recon, ref_date, folder, key=folder.name)
            st.success(f"Analyse terminée. Documents conservés dans {folder.relative_to(ROOT)}")
            goto(PAGES[2])
            st.rerun()

# ------------------------------------------------------------------ PAGE 2
elif page == PAGES[1]:
    st.title("Vue d'ensemble du marché")
    if need_analysis():
        sim_banner()
        a = ss.analysis
        F = a["fields"]
        for w in a["warnings"]:
            st.warning(w)
        c = st.columns(3)
        c[0].metric("Acheteur", fmt_value("buyer", F["buyer"]["value"]))
        c[1].metric("Durée", fmt_value("contract_duration", F["contract_duration"]["value"]))
        c[2].metric("Montant annuel", fmt_value("annual_amount", F["annual_amount"]["value"]))
        c = st.columns(3)
        c[0].metric("Type de prix", fmt_value("price_type", F["price_type"]["value"]))
        c[1].metric("Événements financiers détectés", len(a["events"]))
        c[2].metric("À revoir (REVIEW_REQUIRED)", sum(1 for e in a["events"] if e["status"] == "REVIEW_REQUIRED"))
        st.markdown(f"**Objet :** {html.escape(fmt_value('contract_title', F['contract_title']['value']))}")
        st.caption(f"Documents : {', '.join(a['documents'])} — date de référence des calculs : "
                   f"{date.fromisoformat(a['reference_date']).strftime('%d/%m/%Y')}")
        st.subheader("Données extraites")
        st.caption("Nature : FACT = lu dans le document · CALCULATION = calcul DÛ · USER_INPUT = saisi · MISSING = absent")
        rows = []
        for k, f in F.items():
            ev = f["evidence"][0] if f["evidence"] else None
            rows.append({"Champ": FIELD_FR.get(k, k), "Valeur": fmt_value(k, f["value"]), "Nature": f["kind"],
                         "Statut": STATUS_FR.get(effective_status(f"field:{k}", f["status"]), effective_status(f"field:{k}", f["status"])),
                         "Confiance": f["confidence"], "Source": source_label(ev) if ev else "—",
                         "Manquant": ", ".join(f["missing_information"])})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.download_button("Télécharger le JSON complet", json.dumps(a, ensure_ascii=False, indent=2, default=str),
                           file_name=f"{a['contract_key']}_du.json", mime="application/json")

# ------------------------------------------------------------------ PAGE 3
elif page == PAGES[2]:
    st.title("Alertes DÛ")
    if need_analysis():
        sim_banner()
        a = ss.analysis
        if not a["events"]:
            st.info("Aucun événement financier détecté. Cela ne prouve pas l'absence de clause : "
                    "vérifiez les avertissements et les champs « Non trouvé » dans la vue d'ensemble.")
        for i, e in enumerate(a["events"]):
            label, color, bg = SEV.get(e["severity"], SEV["info"])
            status = effective_status(f"event:{i}", e["status"])
            ev = e["evidence"][0] if e["evidence"] else None
            amount = e.get("potential_amount")
            lines = [f"<span style='background:{color};color:white;padding:2px 8px;border-radius:4px;font-weight:700'>[{label}]</span>"
                     f" <span style='font-size:0.8em;color:#475467'>{e['financial_event_type']}</span>",
                     f"<div style='font-size:1.25em;font-weight:700;margin-top:6px'>{html.escape(e['title'])}</div>"]
            if e.get("calculated_deadline"):
                lines.append(f"<b>Deadline :</b> {date.fromisoformat(e['calculated_deadline']).strftime('%d/%m/%Y')}")
            elif e["financial_event_type"] in ("PRICE_REVISION_DEADLINE", "PRICE_REVISION_FORFEITURE", "RETENTION_RELEASE"):
                lines.append("<b>Deadline :</b> non calculable (information manquante)")
            if amount:
                suffix = " / an" if e["financial_event_type"].startswith("PRICE_REVISION") else ""
                lines.append(f"<b>Impact potentiel :</b> +{calc.fmt_eur(amount)}{suffix}"
                             + (" <i>(simulé)</i>" if e.get("SIMULATED_EXAMPLE") else ""))
            if e.get("action"):
                lines.append(f"<b>Action :</b> {html.escape(e['action'])}")
            if ev:
                lines.append(f"<b>Source :</b> {html.escape(source_label(ev))}")
            lines.append(f"<b>Statut :</b> {html.escape(STATUS_FR.get(status, status))} · confiance {e['confidence']}")
            if e["missing_information"]:
                lines.append(f"<b style='color:#b42318'>Manquant :</b> {html.escape(', '.join(e['missing_information']))}")
            st.markdown(f"<div style='border-left:6px solid {color};background:{bg};padding:12px 16px;border-radius:6px;"
                        f"margin:6px 0;line-height:1.7'>{'<br>'.join(lines)}</div>", unsafe_allow_html=True)
            st.button("Voir la preuve", key=f"proof_{i}", on_click=goto, args=(PAGES[3], i))

# ------------------------------------------------------------------ PAGE 4
elif page == PAGES[3]:
    st.title("Preuves")
    if need_analysis():
        sim_banner()
        a = ss.analysis
        if not a["events"]:
            st.info("Aucun événement.")
        else:
            opts = [f"{i + 1}. [{e['severity'].upper()}] {e['title']}" for i, e in enumerate(a["events"])]
            idx = st.selectbox("Événement", range(len(opts)), format_func=lambda i: opts[i],
                               index=min(ss.selected_event, len(opts) - 1))
            e = a["events"][idx]
            status = effective_status(f"event:{idx}", e["status"])
            st.markdown(f"**Type :** `{e['financial_event_type']}` · **Confiance :** {e['confidence']} · "
                        f"**Statut :** {STATUS_FR.get(status, status)}")
            texts = page_texts(tuple(ss.pdf_paths))
            st.subheader("A. Faits contractuels — extraits exacts")
            if not e["evidence"]:
                st.warning("Aucun extrait de contrat : cet événement provient uniquement de données de rapprochement.")
            for ev in e["evidence"]:
                verified = "extrait retrouvé littéralement dans la page" if ev["quote_verified"] else "EXTRAIT NON RETROUVÉ — à vérifier"
                st.markdown(f"**{html.escape(source_label(ev))}** · {verified}")
                st.markdown(f"> {html.escape(ev['quote'])}")
                full = texts.get((ev["document"], ev["page"]))
                if full:
                    with st.expander(f"Texte complet de la page {ev['page']} (extrait surligné)"):
                        q = ev["quote"].replace(" […]", "")
                        flat = " ".join(full.split())
                        pos = flat.find(" ".join(q.split()))
                        if pos >= 0:
                            n = len(" ".join(q.split()))
                            body = (html.escape(flat[:pos]) + "<mark>" + html.escape(flat[pos:pos + n]) + "</mark>"
                                    + html.escape(flat[pos + n:]))
                        else:
                            body = html.escape(flat)
                        st.markdown(f"<div style='font-size:0.9em;line-height:1.6'>{body}</div>", unsafe_allow_html=True)
            st.markdown("**Données extraites**")
            st.json(e["contractual_fact"])
            st.subheader("B. Calcul déterministe")
            fc = e.get("financial_calculation")
            if fc and fc.get("steps"):
                for s in fc["steps"]:
                    st.markdown(f"- {s}")
                with st.expander("Valeurs calculées (JSON)"):
                    st.json({k: v for k, v in fc.items() if k != "steps"})
            else:
                st.caption("Aucun calcul pour cet événement.")
            st.subheader("C. Hypothèses et informations manquantes")
            if e["assumptions"]:
                for s in e["assumptions"]:
                    st.markdown(f"- Hypothèse : {s}")
            if e["missing_information"]:
                st.error("Informations manquantes : " + ", ".join(e["missing_information"]))
            if not e["assumptions"] and not e["missing_information"]:
                st.caption("Aucune hypothèse déclarée, aucune information manquante détectée.")
            st.divider()
            st.subheader("Validation humaine")
            if ss.folder:
                comment = st.text_input("Commentaire", key=f"cm_{idx}")
                b1, b2 = st.columns(2)
                if b1.button("Je valide cet événement après lecture du contrat", key=f"ok_{idx}"):
                    save_validation(Path(ss.folder), f"event:{idx}", "VALIDATED", comment)
                    st.rerun()
                if b2.button("Je rejette cet événement", key=f"ko_{idx}"):
                    save_validation(Path(ss.folder), f"event:{idx}", "REJECTED", comment)
                    st.rerun()
                st.caption("Le statut VALIDATED n'est jamais attribué automatiquement. Les validations sont enregistrées "
                           "dans validations.json du dossier de l'analyse.")
            else:
                st.caption("Validation désactivée pour les exemples simulés.")

# ------------------------------------------------------------------ Exemples simulés
elif page == PAGES[4]:
    st.title("Exemples simulés")
    st.markdown(f"<div style='background:#fef0c7;border:2px solid #dc6803;padding:10px 14px;border-radius:8px;"
                f"font-weight:700;color:#7a2e0e'>{SIM_BANNER} Acheteurs, fournisseurs, montants et identifiants "
                f"d'indices sont fictifs.</div>", unsafe_allow_html=True)
    if not SIM_DIR.exists() or not any(SIM_DIR.glob("case_*")):
        st.error("Exemples absents. Lancez : python scripts/generate_demo_pdfs.py")
    for case_dir in sorted(SIM_DIR.glob("case_*")):
        meta = json.loads((case_dir / "meta.json").read_text(encoding="utf-8"))
        with st.container(border=True):
            st.markdown(f"**{meta.get('title', case_dir.name)}**")
            st.caption("Documents : " + ", ".join(p.name for p in sorted(case_dir.iterdir()) if p.is_file()) +
                       f" — date de référence figée : {meta.get('reference_date')}")
            if st.button("Charger cet exemple", key=f"sim_{case_dir.name}"):
                case = load_case(case_dir)
                run_analysis(case["pdfs"], case["meta"].get("user_inputs", {}), case["recon"],
                             date.fromisoformat(meta["reference_date"]), None, simulated=True, key=case_dir.name)
                goto(PAGES[2])
                st.rerun()

# ------------------------------------------------------------------ Évaluation
elif page == PAGES[5]:
    st.title("Évaluation sur vérité terrain")
    st.caption("Équivalent de : python run_evaluation.py")
    if st.button("Lancer l'évaluation", type="primary"):
        from du_engine.evaluation import aggregate, error_list, evaluate_contract
        gt_dir, c_dir = ROOT / "data" / "ground_truth", ROOT / "data" / "contracts"
        results = []
        for p in sorted(gt_dir.glob("*.json")):
            if p.name.startswith("_"):
                continue
            gt = json.loads(p.read_text(encoding="utf-8"))
            case = c_dir / gt["contract_id"]
            if gt.get("validated") and case.exists():
                results.append(evaluate_contract(analyze_case(case), gt))
        agg = aggregate(results)
        if agg["simulated_contracts"]:
            st.warning(f"{agg['simulated_contracts']}/{agg['contracts']} contrats sont simulés et rédigés par l'auteur des "
                       "règles : ces scores ne mesurent pas la performance sur de vrais contrats.")
        c = st.columns(4)
        c[0].metric("Contrats", agg["contracts"])
        c[1].metric("Attendus / détectés", f"{agg['expected_events']} / {agg['detected_events']}")
        c[2].metric("Recall", "n/a" if agg["recall"] is None else f"{agg['recall'] * 100:.1f} %")
        c[3].metric("Precision", "n/a" if agg["precision"] is None else f"{agg['precision'] * 100:.1f} %")
        st.write(f"TP {agg['true_positives']} · FP {agg['false_positives']} · FN {agg['false_negatives']} "
                 f"(dont critiques : {agg['critical_false_negatives']})")
        st.dataframe([{"Champ": k, **v} for k, v in agg["fields"].items()], hide_index=True)
        st.subheader("Erreurs")
        for e in error_list(results):
            st.markdown(f"- {e}")
