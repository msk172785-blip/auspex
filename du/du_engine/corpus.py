"""Chargement d'un dossier de contrat (corpus ou exemple simulé).

Structure attendue d'un dossier :
  *.pdf                 documents du marché (CCAP, AE, CCP, avenants…)
  meta.json             facultatif : {"user_inputs": {...}, "reference_date": "AAAA-MM-JJ", "SIMULATED_EXAMPLE": bool}
  invoices.json         facultatif : {"invoices": [...]}
  purchase_orders.json  facultatif : {"purchase_orders": [...]}
  retention.json        facultatif : {"reception_date": ..., "retained": [...], "payments": [...]}
Un PDF isolé (data/contracts/contract_001.pdf) est aussi accepté.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from .models import ContractAnalysis
from .pipeline import analyze_pdfs


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_case(path: Path) -> dict:
    path = Path(path)
    if path.is_file():
        return {"key": path.stem, "pdfs": [path], "meta": {}, "recon": {}}
    meta = _read(path / "meta.json")
    recon = {}
    inv = _read(path / "invoices.json")
    if inv:
        recon["invoices"] = inv.get("invoices", [])
    po = _read(path / "purchase_orders.json")
    if po:
        recon["purchase_orders"] = po.get("purchase_orders", [])
    rt = _read(path / "retention.json")
    if rt:
        recon["retention"] = rt
    simulated = bool(meta.get("SIMULATED_EXAMPLE") or inv.get("SIMULATED_EXAMPLE") or po.get("SIMULATED_EXAMPLE")
                     or rt.get("SIMULATED_EXAMPLE"))
    meta["SIMULATED_EXAMPLE"] = simulated
    return {"key": path.name, "pdfs": sorted(path.glob("*.pdf")), "meta": meta, "recon": recon}


def analyze_case(path: Path, reference_date: Optional[date] = None) -> ContractAnalysis:
    case = load_case(path)
    meta = case["meta"]
    ref = reference_date or (date.fromisoformat(meta["reference_date"]) if meta.get("reference_date") else None)
    return analyze_pdfs(case["pdfs"], user_inputs=meta.get("user_inputs", {}), recon=case["recon"],
                        reference_date=ref, simulated=bool(meta.get("SIMULATED_EXAMPLE")), contract_key=case["key"])


def list_cases(root: Path) -> list[Path]:
    root = Path(root)
    out = [p for p in sorted(root.iterdir()) if (p.is_dir() and any(p.glob("*.pdf"))) or p.suffix.lower() == ".pdf"]
    return out
