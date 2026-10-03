"""Interpréteur sémantique par LLM (Claude, API Anthropic) — OPTIONNEL.

Activé uniquement si un client est fourni ou si des identifiants Anthropic sont disponibles.
Le LLM interprète ; il ne prouve rien : chaque clause qu'il renvoie passe par verify.Verifier
(citation retrouvée, nombres ancrés, page/article recalculés). Une citation introuvable =>
REJECTED_UNSUPPORTED. Les sorties sont contraintes par un schéma JSON (structured outputs).

Statut de test : la mécanique (schéma, conversion, vérification, rejet) est testée avec un client
simulé. Aucun appel réel n'a été exécuté dans l'environnement de développement (pas de clé d'API).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .candidates import Candidate
from .document import StructuredDocument
from .schema import LLM_OUTPUT_SCHEMA, Amount, Clause, Evidence, Percentage

MODEL = os.environ.get("DU_LLM_MODEL", "claude-opus-5-5")

SYSTEM_PROMPT = """Tu analyses des clauses de marchés publics français pour le TITULAIRE (fournisseur).
Pour la section fournie, liste chaque clause qui crée, conditionne ou fait perdre un droit financier du titulaire.

Règles impératives :
- `quotes` : recopie MOT POUR MOT un ou plusieurs passages de la section qui justifient la clause. Aucune reformulation.
  Une citation qui n'existe pas dans le texte sera rejetée automatiquement.
- N'invente aucune valeur absente du texte. Si une information manque, laisse le champ vide et explique dans `notes`.
- `actor` : la partie qui doit agir, y compris quand la phrase est à la voix passive, au futur, ou avec un pronom
  (« il lui appartient », « la demande devra parvenir »). Si c'est une déduction, mets uncertainty=MEDIUM ou HIGH.
- Chaque montant et chaque pourcentage a un rôle obligatoire. Un plafond (CAP) n'est pas un seuil de déclenchement
  (THRESHOLD). Un maximum de bons de commande n'est pas la valeur annuelle du marché.
- `consequence_if_no_action` : ce qui arrive si la partie concernée n'agit pas. Distingue « anciens prix reconduits
  faute de demande » (PRICE_KEPT, défavorable au titulaire) de « nouveaux prix appliqués » (PRICE_APPLIED) et de
  « acceptation réputée » (DEEMED_ACCEPTED : défavorable si c'est le titulaire qui est réputé accepter, favorable si
  c'est l'acheteur).
- Les mots « révision » ou « prix » peuvent être absents : « ajustement tarifaire », « actualisation »,
  « évolution des tarifs », « indexation », « nouveaux prix »… relèvent du même événement.
- Ne déduis rien du CCAG ou du Code non cité dans la section : signale le renvoi dans `notes`.
"""


def _default_client():
    try:
        import anthropic  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Le paquet `anthropic` n'est pas installé (pip install anthropic).") from exc
    return anthropic.Anthropic()


class LLMInterpreter:
    name = "LLM"

    def __init__(self, sd: StructuredDocument, client: Any = None, model: str = MODEL, max_sections: int = 60):
        self.sd = sd
        self.client = client
        self.model = model
        self.max_sections = max_sections
        self.log: list[dict] = []

    def _section_payload(self, sid: str) -> str:
        sec = self.sd.section(sid)
        lines = [f"[Article {sec.number or '-'} — {sec.title} — pages {sec.page_start}-{sec.page_end}]"]
        lines.append(self.sd.clean_text[sec.start:sec.end])
        return "\n".join(lines)

    def _call(self, payload: str) -> dict:
        client = self.client or _default_client()
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": payload}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": LLM_OUTPUT_SCHEMA}},
        )
        if self.client is None:
            # client réel : repli serveur en cas de refus (paramètre recommandé pour ce modèle)
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
        if getattr(resp, "stop_reason", None) == "refusal":
            raise RuntimeError("refus du modèle")
        text = next(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return json.loads(text)

    def interpret(self, candidates: list[Candidate]) -> list[Clause]:
        sids = []
        for c in candidates:
            if c.section not in sids:
                sids.append(c.section)
        clauses: list[Clause] = []
        for sid in sids[: self.max_sections]:
            payload = self._section_payload(sid)
            try:
                data = self._call(payload)
            except Exception as exc:  # erreur réseau, refus, JSON invalide : tracée, jamais masquée
                self.log.append({"section": sid, "error": f"{exc.__class__.__name__}: {exc}"})
                continue
            self.log.append({"section": sid, "clauses": len(data.get("clauses", []))})
            sec = self.sd.section(sid)
            for item in data.get("clauses", []):
                clauses.append(self.to_clause(item, sec.sid, sec.number))
        return clauses

    def to_clause(self, item: dict, sid: Optional[str], article: Optional[str]) -> Clause:
        dl = item.get("deadline_rule") or {}
        dl = None if dl.get("amount") in (None, 0) and dl.get("anchor") in (None, "NONE") else dl
        cn = item.get("consequence_if_no_action") or {}
        cn = None if cn.get("type") in (None, "NONE") else cn
        unc = item.get("uncertainty", "HIGH")
        c = Clause(
            event_type=item["event_type"], actor=item.get("actor", "UNKNOWN"), actor_basis="LLM",
            action_required=item.get("action_required", ""), trigger=item.get("trigger", ""),
            deadline_rule=dl, deadline_basis=item.get("deadline_basis", ""),
            consequence_if_action=item.get("consequence_if_action", ""), consequence_if_no_action=cn,
            amounts=[Amount(value=a["value"], unit=a.get("unit", ""), role=a["role"]) for a in item.get("amounts", [])],
            percentages=[Percentage(value=p["value"], role=p["role"], subrole=p.get("subrole", "OTHER")) for p in item.get("percentages", [])],
            evidence=[Evidence(document=self.sd.name, page=None, page_end=None, article=None, quote=q) for q in item.get("quotes", [])],
            section_id=sid, source_article=article, source_quote=(item.get("quotes") or [""])[0], interpreter=self.name,
            confidence={"LOW": 0.85, "MEDIUM": 0.7, "HIGH": 0.5}.get(unc, 0.5),
        )
        if item.get("notes"):
            c.attributes["llm_notes"] = item["notes"]
        if unc != "LOW":
            c.review_reasons.append(f"Incertitude déclarée par le LLM : {unc}.")
        return c
