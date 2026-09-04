"""QSS sinh từ DESIGN.md — DESIGN.md là luật duy nhất, file này chỉ dịch.

Không hardcode màu trong .py UI: mọi màu lấy từ tokens DESIGN.md
(front matter YAML, parse tay cho khỏi thêm dependency).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict
import sys

DESIGN_PATH = Path(__file__).resolve().parents[1] / "DESIGN.md"


def design_path() -> Path:
    cands = [DESIGN_PATH]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cands.append(Path(meipass) / "DESIGN.md")
    for c in cands:
        if c.is_file():
            return c
    return cands[0]


def load_tokens(path: str | Path | None = None) -> Dict[str, Dict[str, str]]:
    text = Path(path or design_path()).read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("thieu front matter")
    front = text.split("---", 2)[1]
    out: Dict[str, Dict[str, str]] = {}
    section = ""
    for line in front.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            section = line.strip()[:-1]
            out[section] = {}
            continue
        if ":" in line and section:
            k, _, v = line.strip().partition(":")
            v = v.strip().strip("\"'")
            # nested (typography h1: fontFamily...) — gộp key cha.con
            if v == "":
                section = section  # giữ section, key con xử ở dòng sau
                out.setdefault(section + "." + k.strip(), {})
                continue
            # dòng con của typography (thụt đầu dòng + parent vừa gặp)? -> bỏ qua chi tiết
            out[section][k.strip()] = v
    return out


def flat_colors(tokens: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    return dict(tokens.get("colors", {}))


def build_qss(tokens: Dict[str, Dict[str, str]] | None = None) -> str:
    t = tokens or load_tokens()
    c = flat_colors(t)
    g = lambda k, d="": c.get(k, d)
    return f"""
* {{ font-family: "Segoe UI"; font-size: 14px; color: {g('text', '#E8E8E8')}; }}
QMainWindow, QWidget#page {{ background: {g('bg', '#101010')}; }}
QWidget#card {{
  background: {g('surface', '#161616')};
  border: 1px solid {g('border', '#2B2B2B')};
  border-radius: 12px;
}}
QWidget#tile {{
  background: {g('surface2', '#1D1D1D')};
  border: 1px solid {g('border', '#2B2B2B')};
  border-radius: 12px;
}}
QLabel#muted {{ color: {g('muted', '#9A9A9A')}; }}
QLabel#mono {{ font-family: "Consolas"; font-size: 12px; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QPushButton#primary {{
  background: {g('accent', '#2E75B6')}; color: {g('on-accent', '#FFFFFF')};
  border: none; border-radius: 6px; padding: 6px 14px;
}}
QPushButton#primary:hover {{ background: {g('accent-hover', '#1F5C8C')}; }}
QPushButton#ghost {{
  background: {g('surface', '#161616')}; color: {g('text', '#E8E8E8')};
  border: 1px solid {g('border', '#2B2B2B')}; border-radius: 6px; padding: 6px 14px;
}}
QPushButton#ghost:hover {{ border-color: {g('accent', '#2E75B6')}; }}
QLineEdit, QTextEdit, QComboBox {{
  background: {g('well', '#0E0E0E')}; color: {g('text', '#E8E8E8')};
  border: 1px solid {g('border', '#2B2B2B')}; border-radius: 6px; padding: 6px 10px;
}}
QListWidget#sidebar {{
  background: {g('surface', '#161616')}; border: none; outline: none;
}}
QListWidget#sidebar::item {{ padding: 10px 14px; border-radius: 8px; }}
QListWidget#sidebar::item:selected {{
  background: {g('accent', '#2E75B6')}; color: {g('on-accent', '#FFFFFF')};
}}
QProgressBar {{ border: none; background: {g('surface2', '#1D1D1D')};
  border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {g('accent', '#2E75B6')}; border-radius: 3px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox#switch {{ spacing: 0; }}
QCheckBox#switch::indicator {{ width: 40px; height: 22px; border-radius: 11px;
  background: #3A3A3A; border: 1px solid {g('border', '#2B2B2B')}; }}
QCheckBox#switch::indicator:checked {{ background: {g('accent', '#2E75B6')}; }}
QCheckBox#switch::indicator:unchecked:hover {{ border-color: {g('accent', '#2E75B6')}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #55575F; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {g('surface2', '#1D1D1D')}; color: {g('text', '#E8E8E8')};
  border: 1px solid {g('border', '#2B2B2B')}; }}
"""
