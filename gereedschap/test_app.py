# -*- coding: utf-8 -*-
"""Nep-Streamlit-harnas: laadt overhoring_web.py als module `m`, zodat de pure logica
(zonder UI) getest kan worden. Gebruik in een test: exec de hele inhoud van dit bestand.
"""
import sys, os, types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _SessionState(dict):
    """Gedraagt zich als st.session_state: zowel dict- als attribuuttoegang."""
    def __getattr__(self, naam):
        try:
            return self[naam]
        except KeyError:
            return None

    def __setattr__(self, naam, waarde):
        self[naam] = waarde

    def __delattr__(self, naam):
        self.pop(naam, None)


def _niets(*a, **k):
    return None


class _Ctx:
    """Container die als context manager én als kolom/tab werkt."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, naam):
        return _widget


def _widget(*a, **k):
    """Elke widget geeft iets neutraals terug (of de meegegeven default)."""
    if "value" in k:
        return k["value"]
    if "index" in k and k["index"] is None:
        return None
    if len(a) >= 2 and isinstance(a[1], (list, tuple)):
        opts = list(a[1])
        if k.get("index", 0) is None:
            return None
        idx = k.get("index", 0) or 0
        return opts[idx] if opts and idx < len(opts) else None
    return None


class _St(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = _SessionState()

    # --- caching: pass-through, met en zonder argumenten ---
    def cache_data(self, func=None, **k):
        if func is None:
            return lambda f: f
        return func

    def cache_resource(self, func=None, **k):
        if func is None:
            return lambda f: f
        return func

    # --- layout ---
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx() for _ in range(n)]

    def tabs(self, labels, **k):
        return [_Ctx() for _ in labels]

    def expander(self, *a, **k):
        return _Ctx()

    def form(self, *a, **k):
        return _Ctx()

    def container(self, *a, **k):
        return _Ctx()

    def connection(self, *a, **k):
        return _Ctx()

    def __getattr__(self, naam):
        # set_page_config, markdown, write, button, radio, slider, progress, toast, ...
        return _widget


st_stub = _St()
sys.modules["streamlit"] = st_stub

_components = types.ModuleType("streamlit.components")
_v1 = types.ModuleType("streamlit.components.v1")
_v1.html = _niets
_v1.iframe = _niets
_components.v1 = _v1
sys.modules["streamlit.components"] = _components
sys.modules["streamlit.components.v1"] = _v1
st_stub.components = _components
st_stub.sidebar = _Ctx()

_gs = types.ModuleType("streamlit_gsheets")
_gs.GSheetsConnection = object
sys.modules["streamlit_gsheets"] = _gs

# De app leest zijn JSON-bestanden met relatieve paden.
os.chdir(REPO)
sys.path.insert(0, REPO)

import importlib.util

import uitvoer

# Vóór de eerste print: anders valt Grieks of Hebreeuws om zodra de uitvoer
# naar een bestand of een pijp gaat in plaats van naar het scherm.
uitvoer.zet_utf8()
_spec = importlib.util.spec_from_file_location("overhoring_web", os.path.join(REPO, "overhoring_web.py"))
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
