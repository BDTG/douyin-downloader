"""Luu file tai + manifest (tu viet, tuong thich gallery cu)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

SAFE_RE = re.compile(r"[\\/:*?\"<>|]")
AID_RE = re.compile(r"(\d{10,})")
MEDIA_SUFFIXES = {".mp4", ".jpg", ".jpeg", ".png", ".webp", ".gif"}
SIDECAR_TAILS = ("_cover", "_avatar", "_music")


def safe_name(s: str, limit: int = 60) -> str:
    s = SAFE_RE.sub("_", (s or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:limit] or "douyin").strip() or "douyin"


def item_dir(downloads: Path, sec_uid: str, date: str, desc: str,
             aweme_id: str) -> Path:
    folder = sec_uid or "unknown"
    leaf = f"{date or 'nodate'}_{safe_name(desc, 40)}_{aweme_id}"
    p = downloads / folder / leaf
    p.mkdir(parents=True, exist_ok=True)
    return p


def append_manifest(downloads: Path, row: Dict[str, Any]) -> None:
    mp = downloads / "download_manifest.jsonl"
    row = dict(row)
    row.setdefault("recorded_at", int(time.time()))
    try:
        with open(mp, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def manifest_lookup(downloads: Path) -> Dict[str, Dict[str, Any]]:
    """aweme_id -> thong tin co ban (de download_images tim lai)."""
    idx: Dict[str, Dict[str, Any]] = {}
    try:
        for line in (downloads / "download_manifest.jsonl").read_text(
                encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            aid = str(d.get("aweme_id") or "")
            if aid and aid not in idx:
                idx[aid] = d
    except Exception:
        pass
    return idx


def local_aweme_ids(downloads: Path) -> set:
    """Quet ten file local tim aweme_id da co media chinh (>0 byte).

    Bo qua sidecar (_cover/_avatar/_music) vi co cover khong co nghia co video.
    """
    found: set = set()
    try:
        if not downloads.exists():
            return found
        for p in downloads.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in MEDIA_SUFFIXES:
                continue
            if p.stem.lower().endswith(SIDECAR_TAILS):
                continue
            try:
                if p.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            m = AID_RE.search(p.name)
            if m:
                found.add(m.group(1))
    except Exception:
        pass
    return found


def aweme_downloaded(downloads: Path, aweme_id: str) -> bool:
    """True neu aweme_id da co file chinh local."""
    if not aweme_id:
        return False
    return aweme_id in local_aweme_ids(downloads)
