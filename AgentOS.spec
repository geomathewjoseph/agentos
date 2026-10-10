# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py', 'api.py', 'graph.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('config', 'config'), ('agents', 'agents'), ('tools', 'tools'), ('router', 'router')],
    hiddenimports=['langgraph', 'langgraph.graph', 'langchain', 'langchain_groq', 'langchain_openai', 'dotenv', 'rich', 'tiktoken', 'tenacity', 'uvicorn', 'fastapi', 'pydantic', 'pydantic_core', 'yaml', 'json', 'sqlite3', 'threading', 'asyncio', 'concurrent.futures', 'pathlib', 'typing', 'dataclasses', 'enum', 'functools', 'itertools', 'operator', 're', 'string', 'textwrap', 'unicodedata', 'html', 'urllib', 'http', 'socket', 'ssl', 'selectors', 'contextvars', 'inspect', 'importlib', 'pkgutil', 'runpy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'tensorflow', 'sklearn', 'scipy', 'pandas', 'numpy', 'matplotlib', 'cv2', 'PIL', 'jupyter', 'IPython', 'notebook', 'pytest', 'unittest', 'doctest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgentOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AgentOS',
)
