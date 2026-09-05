"""Chuyen nickname Tieng Trung -> am Han-Viet (offline).

Du lieu: engine/data/hanviet.json  {chu: {"hv": am, "vi": nghia?}}
  - am: tu Unihan kVietnamese (8306 chu) + 5 chu bo sung tay (脆 thúy,
    玥 nguyệt, 桐 đồng, 兴 hưng, 堡 bảo — am Han-Viet chuan).
  - nghia: tu bo HSK 768 chu (CC BY 4.0, binhbuithithanh/hanzi-sino-vietnamese).
Chu khong co trong tu dien thi giu nguyen (tra ve kem co unknown=true).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_DATA = Path(__file__).resolve().parents[2] / "data" / "hanviet.json"


@lru_cache(maxsize=1)
def _table() -> Dict[str, dict]:
    try:
        return json.loads(_DATA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def hanviet_name(text: str) -> dict:
    """Tra ve {"original","hanviet","unknown"}; hanviet = am doc cach nhau bang space."""
    t = _table()
    parts: List[str] = []
    unknown: List[str] = []
    for ch in (text or ""):
        e = t.get(ch)
        if e and e.get("hv"):
            parts.append(e["hv"])
        elif "\u4e00" <= ch <= "\u9fff":
            parts.append(ch)
            if ch not in unknown:
                unknown.append(ch)
        else:
            parts.append(ch)
    hv = " ".join(p for p in parts if p).replace("  ", " ").strip()
    # Viet hoa dau chu cho ten: "thuy nhuoc bao bao" -> "Thuy Nhuoc Bao Bao"
    hv = " ".join(w[:1].upper() + w[1:] for w in hv.split(" "))
    return {"original": text or "", "hanviet": hv, "unknown": unknown}


def char_meaning(ch: str) -> str:
    e = _table().get(ch) or {}
    return str(e.get("vi") or "")
