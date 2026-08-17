# -*- coding: utf-8 -*-
"""Genereert grieks_motor.py: de framework-onafhankelijke kern van de app.

Neemt de functies en constanten die niets met Streamlit te maken hebben over in de
oorspronkelijke volgorde, en vervangt de twee cache-decorators door een eigen
implementatie met dezelfde semantiek.
"""
import ast, io, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BRON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overhoring_web.py")
DOEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "grieks_motor.py")

src = open(BRON, encoding="utf-8").read()
regels = src.split("\n")
boom = ast.parse(src)

top_fn, top_var = {}, {}
imports = []
for k in boom.body:
    if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_fn[k.name] = k
    elif isinstance(k, ast.Assign):
        for t in k.targets:
            if isinstance(t, ast.Name):
                top_var[t.id] = k
    elif isinstance(k, (ast.Import, ast.ImportFrom)):
        imports.append(k)


def namen_in(knoop):
    uit = set()
    for n in ast.walk(knoop):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            uit.add(n.id)
        elif isinstance(n, ast.Attribute):
            b = n
            while isinstance(b, ast.Attribute):
                b = b.value
            if isinstance(b, ast.Name):
                uit.add(b.id)
    return uit


def bron_van(knoop):
    """Brontekst inclusief decorators."""
    start = min([d.lineno for d in getattr(knoop, "decorator_list", [])] + [knoop.lineno])
    return "\n".join(regels[start - 1:knoop.end_lineno])


def raakt_st(knoop, negeer_decorator=True):
    tekst = "\n".join(regels[knoop.lineno - 1:knoop.end_lineno]) if negeer_decorator else bron_van(knoop)
    # conn. = de Google Sheets-verbinding: dat is opslag, geen motor.
    return bool(re.search(r"\bst\.|components\.|\bconn\.", tekst))


# --- welke functies kunnen mee? (transitief) ---
kandidaat = {n for n, k in top_fn.items() if not raakt_st(k)}
roept = {n: (namen_in(k) & set(top_fn)) for n, k in top_fn.items()}
zuiver = set(kandidaat)
while True:
    weg = {n for n in zuiver if roept[n] - zuiver}
    if not weg:
        break
    zuiver -= weg

# --- welke constanten hebben ze nodig? (transitief) ---
# Taalkundige tabellen die de schil gebruikt maar geen enkele motor-functie aanroept,
# zoals _VOORZETSEL_INFO voor de woordopbouw. Die horen bij de taalkennis, niet bij de UI.
EXTRA_VAR = {"_VOORZETSEL_INFO", "_OPB_VOORVOEGSELS", "_ETA_CONTRACTA"}
nodig_var = {v for v in EXTRA_VAR if v in top_var}
for n in zuiver:
    nodig_var |= namen_in(top_fn[n]) & set(top_var)
for _ in range(8):
    extra = set()
    for v in list(nodig_var):
        extra |= (namen_in(top_var[v]) & set(top_var)) - nodig_var
    if not extra:
        break
    nodig_var |= extra

# --- imports die de motor nodig heeft ---
gebruikt = set()
for n in zuiver:
    gebruikt |= namen_in(top_fn[n])
for v in nodig_var:
    gebruikt |= namen_in(top_var[v])

import_regels = []
for k in imports:
    for a in k.names:
        naam = (a.asname or a.name).split(".")[0]
        if naam in gebruikt and naam != "st":
            if isinstance(k, ast.Import):
                import_regels.append(f"import {a.name}" + (f" as {a.asname}" if a.asname else ""))
            else:
                import_regels.append(f"from {k.module} import {a.name}" +
                                     (f" as {a.asname}" if a.asname else ""))

KOP = '''# -*- coding: utf-8 -*-
"""De Griekse motor: ontleding, klankwetten, stamtijden, woordkeuze en voortgang.

Dit bestand kent geen UI-framework. Het is losgemaakt uit overhoring_web.py zodat
dezelfde logica onder Streamlit én onder een andere schil (NiceGUI) kan draaien.
Automatisch gegenereerd door scratchpad/bouw_motor.py — pas de bron aan, niet dit bestand.
"""
'''

PREAMBULE = '''

# --- omgeving ------------------------------------------------------------
# Deze twee staan in de bron in een try-blok (optionele afhankelijkheden) en
# worden daarom apart meegegeven in plaats van uit de broncode gekopieerd.
try:
    from zoneinfo import ZoneInfo
    _TIJDZONE = ZoneInfo("Europe/Amsterdam")
except Exception:
    _TIJDZONE = None

try:
    import fitz  # PyMuPDF: rendert de grammatica-slides
    FITZ_BESCHIKBAAR = True
except Exception:
    fitz = None
    FITZ_BESCHIKBAAR = False
'''

CACHE = '''

# --- cache ---------------------------------------------------------------
# Vervangt @st.cache_data en @st.cache_resource met dezelfde semantiek:
#  * argumenten waarvan de naam met _ begint tellen niet mee in de sleutel
#    (zo kunnen grote, niet-hashbare structuren worden doorgegeven);
#  * cache_data geeft een kopie terug, cache_resource het gedeelde object;
#  * .clear() maakt de cache leeg.
def _sleutel(fn, args, kwargs):
    namen = fn.__code__.co_varnames[:fn.__code__.co_argcount]
    deel = [a for n, a in zip(namen, args) if not n.startswith("_")]
    deel += [(k, v) for k, v in sorted(kwargs.items()) if not k.startswith("_")]
    return tuple(deel)


def _maak_cache(kopieer):
    def decorator(*dargs, **_dkw):
        def wrap(fn):
            opslag = {}

            @functools.wraps(fn)
            def binnen(*a, **k):
                try:
                    s = _sleutel(fn, a, k)
                except TypeError:
                    return fn(*a, **k)
                if s not in opslag:
                    opslag[s] = fn(*a, **k)
                r = opslag[s]
                return copy.deepcopy(r) if kopieer else r

            binnen.clear = opslag.clear
            binnen.__wrapped__ = fn
            return binnen

        if len(dargs) == 1 and callable(dargs[0]) and not _dkw:
            return wrap(dargs[0])
        return wrap
    return decorator


cache_data = _maak_cache(kopieer=True)
cache_resource = _maak_cache(kopieer=False)
# -------------------------------------------------------------------------

'''

# --- in bronvolgorde uitschrijven ---
stukken = []
for k in boom.body:
    if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k.name in zuiver:
        tekst = bron_van(k)
        tekst = re.sub(r"@st\.cache_data", "@cache_data", tekst)
        tekst = re.sub(r"@st\.cache_resource", "@cache_resource", tekst)
        stukken.append(tekst)
    elif isinstance(k, ast.Assign):
        doelen = [t.id for t in k.targets if isinstance(t, ast.Name)]
        if any(d in nodig_var for d in doelen):
            stukken.append("\n".join(regels[k.lineno - 1:k.end_lineno]))

uit = (KOP + "import copy\nimport functools\n" +
       "\n".join(sorted(set(import_regels))) + "\n" + PREAMBULE + CACHE +
       "\n\n\n".join(stukken) + "\n")

open(DOEL, "w", encoding="utf-8").write(uit)
ast.parse(uit)
print(f"grieks_motor.py geschreven: {uit.count(chr(10))} regels, "
      f"{len(zuiver)} functies, {len(nodig_var)} constanten")
print("imports:", ", ".join(sorted(set(import_regels))))
resterend = sorted(kandidaat - zuiver)
print(f"niet meegenomen ({len(resterend)}): {', '.join(resterend)}")
