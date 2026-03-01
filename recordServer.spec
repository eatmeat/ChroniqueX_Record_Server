# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['recordServer.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('templates', 'templates'),
        ('LICENSE', '.'),
        ('LICENSE_RU', '.'),
        ('img', 'img'),
    ],
    hiddenimports=[
        'win32event',
        'win32api',
        'winerror',
        'pyaudiowpatch',
        'pystray',
        'PIL',
        'flask',
        'werkzeug.serving',
        'dotenv',
        'requests',
        'sounddevice',
        'numpy',
        'pydub',
        'tkinter',
    ],
    collect_submodules=[],
    collect_binaries=[],
    collect_data_files=[],
    collect_dynamic_libs=[],
    hooks=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ChroniqueX Record Server',
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
    icon=None,
)
