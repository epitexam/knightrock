# knightrock.spec
from pathlib import Path


spec_path = Path(SPECPATH).resolve()
project_root = spec_path if spec_path.is_dir() else spec_path.parent

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(project_root / "assets"), "assets")],
    hiddenimports=["pytmx", "pygame"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="knightrock",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="knightrock",
    strip=False,
    upx=False,
)