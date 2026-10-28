# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for compiling Studio into a standalone Windows executable."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

datas = [
    ('web', 'web'),
    ('prompts', 'prompts'),
    ('assets', 'assets'),
]

binaries = []
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.lifespans',
    'uvicorn.lifespans.on',
    'uvicorn.lifespans.off',
    'src.app',
    'src.scraper',
    'src.profile_summary',
    'src.update_sheet',
    'src.design',
    'src.pipeline_common',
    'src.r2_storage',
    'src.d1_client',
]

# Collect dynamic dependencies
packages_to_collect = [
    'fastapi',
    'starlette',
    'playwright',
    'pydantic',
    'boto3',
    'gspread',
    'google.auth',
    'PIL',
]

for pkg in packages_to_collect:
    try:
        p_datas, p_bins, p_hidden = collect_all(pkg)
        datas += p_datas
        binaries += p_bins
        hiddenimports += p_hidden
    except Exception:
        pass

a = Analysis(
    ['entrypoint.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Single-file executable (Method 1: Uses system Edge/Chrome, keeping output compact)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True if you want a visible debug terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/studio.ico' if Path('assets/studio.ico').is_file() else None,
)
