"""Ten Han-Viet offline (tu viet, doc engine/data/hanviet.json)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List


@lru_cache(maxsize=1)
def _table(data_path: str) -> Dict[str, str]:
    try:
        raw = json.loads(Path(data_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    table: Dict[str, str] = {}
    if isinstance(raw, dict):
        for ch, v in raw.items():
            if isinstance(v, dict):
                hv = str(v.get("hv") or v.get("hanviet") or "")
            else:
                hv = str(v or "")
            if hv:
                table[ch] = hv.split(",")[0].strip()
    return table


def hanviet_name(name: str, data_path: str) -> tuple[str, List[str]]:
    """Tra (ten_hanviet, unknown_chars). Chu la tinh giu nguyen."""
    table = _table(data_path)
    out: List[str] = []
    unknown: List[str] = []
    for ch in (name or ""):
        if "一" <= ch <= "鿿":
            hv = table.get(ch, "")
            if hv:
                out.append(hv.capitalize() if not out else hv)
            else:
                out.append(ch)
                unknown.append(ch)
        else:
            out.append(ch)
    text = "".join(out)
    text = " ".join(text.split())
    return text, sorted(set(unknown))
