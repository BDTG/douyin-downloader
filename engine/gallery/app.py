"""Gallery xem video/anh da tai theo user. Doc ./downloads + aliases.json + manifest."""
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

DL = Path(os.environ.get("DL_DIR", "/downloads"))
ALIAS_PATH = Path(os.environ.get("ALIAS_PATH", "/aliases.json"))
SUBJ_PATH = Path(os.environ.get("SUBJECTS_PATH", str(DL.parent / "subjects.json")))
VIDEO_EXT = {".mp4", ".flv", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_AID_RE = re.compile(r"(\d{10,})")

app = FastAPI(title="douyin-gallery")

# He thong tier: 1 diem/file + 1 diem/50MB. Tat ca bat dau tu F.
# Qua SSSSS cu +100 diem lai them 1 chu S (vo han).
TIERS = [
    ("F", 0), ("E", 5), ("D", 10), ("C", 20), ("B", 35), ("A", 55),
    ("S", 80), ("SS", 110), ("SSS", 150), ("SSSS", 200), ("SSSSS", 250),
]
EXTRA_S_EVERY = 100


def rank_for(score):
    tier = TIERS[0][0]
    nxt = None
    for i, (name, need) in enumerate(TIERS):
        if score >= need:
            tier = name
            nxt = TIERS[i + 1] if i + 1 < len(TIERS) else None
        else:
            nxt = (name, need)
            break
    if nxt is None:
        # vuot SSSSS: moi EXTRA_S_EVERY diem +1 S
        extra = (score - TIERS[-1][1]) // EXTRA_S_EVERY
        tier = "S" * (5 + extra)
        nxt = ("S" * (6 + extra), TIERS[-1][1] + (extra + 1) * EXTRA_S_EVERY)
    return {"tier": tier, "score": score, "next_tier": nxt[0],
            "next_at": nxt[1], "to_next": nxt[1] - score}


def score_of(items):
    n = len(items)
    mb = sum(it.get("size", 0) for it in items) / 1048576
    return n + int(mb // 50)


def _manifest_index():
    """aweme_id -> {desc, date, media_type}. Khop bang ID trong ten file (folder doi ten van khop)."""
    idx = {}
    try:
        for line in (DL / "download_manifest.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            aid = str(d.get("aweme_id") or "")
            if aid and aid not in idx:
                tags = d.get("tags") or []
                idx[aid] = {
                    "desc": str(d.get("desc") or ""),
                    "date": str(d.get("date") or ""),
                    "media_type": str(d.get("media_type") or ""),
                    "tags": [str(x) for x in tags if x][:10],
                }
    except Exception:
        pass
    return idx


def scan(subj):
    meta = _manifest_index()
    users = {}
    if DL.exists():
        for f in sorted(DL.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            if f.suffix.lower() not in VIDEO_EXT | IMAGE_EXT:
                continue
            rel = f.relative_to(DL)
            user = rel.parts[0] if len(rel.parts) > 1 else "(goc)"
            m = _AID_RE.search(f.name)
            aid = m.group(1) if m else ""
            info = meta.get(aid, {}) if aid else {}
            st = f.stat()
            # chinh chu: gan tung file > mac dinh theo acc > "" (chua gan)
            subject = (subj["files"].get(aid) or subj["defaults"].get(user) or "") if aid else (subj["defaults"].get(user) or "")
            users.setdefault(user, []).append({
                "path": rel.as_posix(),
                "name": f.name,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "kind": "video" if f.suffix.lower() in VIDEO_EXT else "image",
                "aweme_id": aid,
                "title": info.get("desc") or f.stem,
                "date": info.get("date") or "",
                "tags": info.get("tags") or [],
                "subject": subject,
            })
    return users


def author_info():
    """sec_uid -> nickname, doc tu download_manifest.jsonl (on dinh hon SQLite)."""
    info = {}
    try:
        for line in (DL / "download_manifest.jsonl").read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            sid = d.get("author_sec_uid")
            if sid and sid not in info:
                info[sid] = d.get("author_name", "")
    except Exception:
        pass
    return info


def load_aliases():
    try:
        a = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
        return a if isinstance(a, dict) else {}
    except Exception:
        return {}


def load_subjects():
    """{"defaults": {folder: subject}, "files": {aweme_id: subject}}"""
    try:
        d = json.loads(SUBJ_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return {"defaults": {}, "files": {}}
        return {"defaults": d.get("defaults") or {}, "files": d.get("files") or {}}
    except Exception:
        return {"defaults": {}, "files": {}}


def save_subjects(s):
    SUBJ_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


@app.get("/api/files")
def files():
    subj = load_subjects()
    users = scan(subj)
    nicks = author_info()
    aliases = load_aliases()
    display = {}
    ranks = {}
    subj_groups = {}  # chinh chu hieu dung -> items (chua gan thi tinh cho nguoi dang)
    for folder, items in users.items():
        code = aliases.get(folder, "")
        nick = nicks.get(folder, "")
        label = code or nick or folder
        display[folder] = {"code": label, "nick": nick,
                           "default_subject": subj["defaults"].get(folder, "")}
        ranks[folder] = rank_for(score_of(items))
        for it in items:
            key = it["subject"] or f"@{label}"
            subj_groups.setdefault(key, []).append(it)
    subj_ranks = {k: rank_for(score_of(v)) for k, v in subj_groups.items()}
    return {"users": users, "display": display, "ranks": ranks,
            "subj_ranks": subj_ranks,
            "subjects": sorted({s for s in subj["files"].values()} | set(subj["defaults"].values())),
            "count": sum(len(v) for v in users.values())}


@app.post("/api/subject")
def set_subject(aweme_id: str, subject: str = ""):
    """Gan chinh chu cho 1 file (subject rong = xoa)."""
    s = load_subjects()
    subject = (subject or "").strip()
    if subject:
        s["files"][aweme_id] = subject
    else:
        s["files"].pop(aweme_id, None)
    save_subjects(s)
    return {"ok": True, "aweme_id": aweme_id, "subject": subject}


@app.post("/api/subject_default")
def set_subject_default(folder: str, subject: str = ""):
    """Chinh chu mac dinh cho ca acc (kieu fangirl chi dang 1 idol). Rong = xoa."""
    s = load_subjects()
    subject = (subject or "").strip()
    if subject:
        s["defaults"][folder] = subject
    else:
        s["defaults"].pop(folder, None)
    save_subjects(s)
    return {"ok": True, "folder": folder, "subject": subject}


@app.get("/api/file")
def onefile(path: str):
    try:
        rp = (DL / path).resolve()
        rp.relative_to(DL.resolve())
    except Exception:
        raise HTTPException(400, "bad path")
    if not rp.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(rp)


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "gallery.html").read_text(encoding="utf-8")
