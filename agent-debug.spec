# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['agent.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw', 'PIL.ImageFont', 'PIL._tkinter_finder', 'mss', 'mss.windows', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.simpledialog', 'tkinter.filedialog', 'tkinter.font', 'input_inject', 'process_mgr', 'file_mgr', 'url_opener', 'notifier', 'viewer', 'webbrowser', 'psutil', 'pyautogui', 'pyautogui._pyautogui_win', 'pyscreeze', 'pytweening', 'pymsgbox', 'mouseinfo', 'pynput', 'pynput.mouse', 'pynput.keyboard', 'pynput.mouse._win32', 'pynput.keyboard._win32'],
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
    name='agent-debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
