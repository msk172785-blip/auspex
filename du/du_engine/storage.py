"""Stockage local (fichiers) des documents déposés, des analyses et des validations humaines.

data/uploads/<analysis_id>/
    *.pdf             copies des documents déposés
    meta.json         saisies utilisateur + date d'analyse
    analysis.json     dernier résultat du moteur
    validations.json  validations / rejets humains par champ ou événement
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "data" / "uploads"


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_")
    return s[:40] or "marche"


def save_upload(files: list[tuple[str, bytes]], meta: dict) -> Path:
    h = hashlib.sha256()
    for name, data in sorted(files):
        h.update(name.encode())
        h.update(data)
    label = meta.get("contract_title") or (files[0][0].rsplit(".", 1)[0] if files else "marche")
    folder = UPLOADS / f"{_slug(label)}_{h.hexdigest()[:10]}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files:
        safe = Path(name).name
        (folder / safe).write_bytes(data)
    meta = {**meta, "saved_at": datetime.now().isoformat(timespec="seconds"), "SIMULATED_EXAMPLE": False}
    (folder / "meta.json").write_text(json.dumps({"user_inputs": meta.get("user_inputs", {}), **meta},
                                                 ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return folder


def save_analysis(folder: Path, analysis_dict: dict) -> None:
    (Path(folder) / "analysis.json").write_text(json.dumps(analysis_dict, ensure_ascii=False, indent=2, default=str),
                                                encoding="utf-8")


def list_uploads() -> list[Path]:
    if not UPLOADS.exists():
        return []
    return sorted([p for p in UPLOADS.iterdir() if p.is_dir() and any(p.glob("*.pdf"))],
                  key=lambda p: p.stat().st_mtime, reverse=True)


def load_validations(folder: Path) -> dict:
    p = Path(folder) / "validations.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_validation(folder: Path, key: str, decision: str, comment: str = "") -> None:
    """decision : VALIDATED | REJECTED. Seule voie vers le statut VALIDATED."""
    v = load_validations(folder)
    v[key] = {"decision": decision, "comment": comment, "at": datetime.now().isoformat(timespec="seconds")}
    (Path(folder) / "validations.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
