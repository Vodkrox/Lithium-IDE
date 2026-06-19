
from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = []
hiddenimports = []

try:
    binaries += collect_dynamic_libs("llama_cpp")
    hiddenimports += ["llama_cpp", "llama_cpp.llama_cpp"]
except Exception:
    pass

a = Analysis(
    ['base.py'],
    pathex=[],
    binaries=binaries,
    datas=[('src/assets', 'src/assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Lithium',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/assets/lithium_icon.ico'
)
