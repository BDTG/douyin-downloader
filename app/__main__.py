"""Cho phép: python -m app --stack-dir <dir>"""
from app.main import _fatal_guard

raise SystemExit(_fatal_guard(None))
