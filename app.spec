# -*- mode: python -*-
# Build: .venv/Scripts/pyinstaller.exe app.spec --noconfirm
# Ra: dist/DouyinDownloader/ (chạy DouyinDownloader.exe)

block_cipher = None

a = Analysis(
    ["app/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[("DESIGN.md", ".")],
    hiddenimports=[],
    hookspath=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DouyinDownloader",
    debug=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    name="DouyinDownloader",
)
