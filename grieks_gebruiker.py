# -*- coding: utf-8 -*-
"""Gebruikerssessie: inloggen, voortgang inlezen en opslaan.

Zit tussen grieks_opslag.py (de Sheet) en de schil (grieks_app.py) in, en houdt zich
aan dezelfde afspraken als overhoring_web.py:
  * de gebruikersnaam is 'naam_code' — die combinatie is je sleutel;
  * scores worden op de woordenlijst gezet met dezelfde velden;
  * opslaan gebeurt na elke beurt, in een aparte thread.
"""
import threading
from datetime import date, datetime, timedelta

import grieks_motor as motor
import grieks_opslag as opslag
import hebreeuws

# Na elke beurt opslaan. Dat kan hier, anders dan in Streamlit: het schrijven draait
# in een aparte thread terwijl de gebruiker de feedback leest, dus het wachten valt
# in tijd die toch al voorbijgaat. Loopt er al een opslag, dan slaan we deze over —
# de volgende beurt neemt alles alsnog mee, want we schrijven telkens de hele staat.
OPSLAG_INTERVAL = 1
STAT_SLEUTELS = [s for s, _ in opslag.SPECS]

# Dagdoel: dezelfde sleutels en standaardwaarden als de Streamlit-app, zodat een doel dat
# je daar instelt hier gewoon geldt (het staat in dezelfde 'dagdoel'-dict in de Sheet).
# 'hebreeuws' staat er alleen bij ons: het Hebreeuws oefen je in de mobiele app. De
# Streamlit-app kent die sleutel niet, maar draagt hem wel door — samenvoegen laat staan
# wat het niet kent.
DAGDOEL_STANDAARD = {"woorden": 10, "verwar": 3, "knelpunt": 5, "actief": 5, "stam": 5,
                     "struct": 5, "verzen": 2, "klank": 5, "hebreeuws": 10}


def vandaag():
    return datetime.now().strftime("%Y-%m-%d")


class Gebruiker:
    """Alles wat één ingelogde student in het geheugen heeft."""

    def __init__(self, naam, code, interval=OPSLAG_INTERVAL):
        self.naam = str(naam).strip()
        self.code = str(code).strip()
        self.sleutel = f"{self.naam}_{self.code}"
        self.woorden = []
        # De Hebreeuwse lijst staat er los naast, met dezelfde velden (streak, score_goed,
        # score_fout, laatst_geoefend). Daardoor werkt alles wat op een woord rekent — de
        # fasen, het uitkiezen, het scoren — voor allebei de talen zonder aanpassing.
        self.hebreeuws = []
        self.stats = {s: {} for s in STAT_SLEUTELS}
        # Na hoeveel beurten er naar de Sheet wordt geschreven. Elke beurt is het
        # prettigst (je raakt nooit iets kwijt), maar op een trage server wacht je dan
        # elke keer op twee netwerkrondjes: eerst lezen om samen te voegen, dan
        # schrijven. Aan het einde van een ronde wordt sowieso geforceerd bewaard.
        self.interval = max(1, int(interval))
        self.sinds_opslag = 0
        self.laatste_fout = None
        self._slot = threading.Lock()

    # ---------------------------------------------------------------- laden
    def laad(self):
        """Woordenlijst inlezen en de opgeslagen scores erop zetten."""
        self.woorden = motor.laad_vocab_db()
        if not self.woorden:
            raise opslag.OpslagFout("De woordenlijst kon niet worden geladen.")
        self.stats = opslag.laad(self.sleutel)
        self._pas_scores_toe()
        self._laad_hebreeuws()
        return self

    def _pas_scores_toe(self):
        """Zelfde toewijzing als laad_gebruiker_data() in overhoring_web.py,
        inclusief de oude m1..m4-telling van vóór het streak-systeem."""
        vocab = self.stats.get("vocab_stats") or {}
        for r in self.woorden:
            s = vocab.get(r["grieks"], {})
            if "m4" in s or "m1" in s:
                r["streak"] = s.get("m2", 0) * 1 + s.get("m3", 0) * 2 + s.get("m4", 0) * 4
            else:
                r["streak"] = s.get("streak", 0)
            r["score_goed"] = s.get("g", 0)
            r["score_fout"] = s.get("f", 0)
            r["laatst_geoefend"] = s.get("laatst_geoefend", "")
            r["laatst_fout"] = s.get("lf", "")
            if not r.get("lexeem_info"):
                r["lexeem_info"] = r.get("grieks_info", "")

    def _laad_hebreeuws(self):
        """De Hebreeuwse woordenlijst met de opgeslagen scores erop.

        Ontbreekt hebreeuws_woorden.json, dan blijft de lijst leeg en laat de app die taal
        gewoon niet zien — de Griekse kant merkt er niets van. De sleutel is het woord
        zonder klinkertekens: die staan in de cursuslijst niet altijd hetzelfde genoteerd,
        en dan zou je voortgang bij een nieuwe uitgave van de lijst kwijt zijn."""
        self.hebreeuws = [dict(w) for w in hebreeuws.laad_woorden()]
        scores = self.stats.get("hebr_stats") or {}
        for w in self.hebreeuws:
            s = scores.get(hebreeuws.medeklinkers(w.get("hebreeuws", ""))) or {}
            w["streak"] = int(s.get("streak", 0))
            w["score_goed"] = int(s.get("g", 0))
            w["score_fout"] = int(s.get("f", 0))
            w["laatst_geoefend"] = s.get("laatst_geoefend", "")
            w["laatst_fout"] = s.get("lf", "")

    def _verzamel_hebreeuws(self):
        """Andersom: de lijst terug naar het compacte opslagformaat."""
        uit = {}
        for w in self.hebreeuws:
            s = int(w.get("streak", 0)); g = int(w.get("score_goed", 0))
            f = int(w.get("score_fout", 0)); l = w.get("laatst_geoefend", "")
            if s or g or f or l:
                e = {"streak": s, "g": g, "f": f}
                if l:
                    e["laatst_geoefend"] = l
                if w.get("laatst_fout"):
                    e["lf"] = w["laatst_fout"]
                uit[hebreeuws.medeklinkers(w.get("hebreeuws", ""))] = e
        return uit

    # ---------------------------------------------------------------- scoren
    def tel_dag(self, woord=None):
        """Eén beoordeelde beurt meetellen voor het oefenritme. Goed of fout maakt niet uit:
        de kalender en de dagstreak gaan over hoevéél je oefent. Zelfde teller als
        registreer_oefening() in de Streamlit-app, en dus dezelfde 'dag_stats'."""
        dag = self.stats.setdefault("dag_stats", {})
        vd = vandaag()
        dag[vd] = int(dag.get(vd, 0)) + 1
        if woord is not None:
            woord["laatst_geoefend"] = vd
            # Het aantal verschillende woorden van vandaag meteen wegschrijven, zodat de
            # kalender het later ook voor voorbije dagen kan tonen — laatst_geoefend
            # bewaart per woord maar één datum.
            self.daglog(vd)["woorden_uniek"] = self.woorden_vandaag()
        self.sinds_opslag += 1

    def noteer(self, woord, goed, punten=1, straf=None, scoor=True):
        """Eén beurt op een woord verwerken. Geeft terug of er is opgeslagen.

        De oefening bepaalt de weging, net als in de Streamlit-app:
          * `punten` — wat een goed antwoord aan streak oplevert. Typen telt zwaarder
            dan aanwijzen, want zelf produceren is moeilijker dan herkennen.
          * `straf` — wat een misser van de streak afhaalt. None laat de streak staan;
            dat is de eerste misser, waarna je het nog een keer mag proberen.
          * `scoor` — False als deze beurt niet meetelt voor goed/fout, bijvoorbeeld
            omdat je het antwoord al had gezien. Voor je oefenritme telt hij wel mee.
        """
        if goed:
            if scoor:
                woord["score_goed"] = int(woord.get("score_goed", 0)) + 1
                woord["streak"] = int(woord.get("streak", 0)) + int(punten)
        else:
            if scoor:
                woord["score_fout"] = int(woord.get("score_fout", 0)) + 1
                woord["laatst_fout"] = vandaag()
            if straf is not None:
                woord["streak"] = max(0, int(woord.get("streak", 0)) - int(straf))
        # Voor het dagdoel telt 'woorden' het aantal VERSCHILLENDE woorden van vandaag; dat
        # zet tel_dag() erbij, samen met de datumstempel op dit woord.
        self.tel_dag(woord)
        if self.sinds_opslag >= self.interval:
            return self.bewaar()
        return False

    # ---------------------------------------------------------------- dagdoel
    def dagdoel(self):
        """De ingestelde doelen, aangevuld met de standaardwaarden."""
        cfg = (self.stats.get("dagdoel") or {}).get("config") or {}
        return {k: int(cfg.get(k, v)) for k, v in DAGDOEL_STANDAARD.items()}

    def zet_dagdoel(self, nieuw):
        """Alleen de meegegeven doelen wijzigen. De Streamlit-app kent er een paar meer
        (knelpunten, klankwetten); die blijven staan zoals je ze daar hebt gezet."""
        cfg = self.dagdoel()
        cfg.update({k: int(v) for k, v in nieuw.items() if k in DAGDOEL_STANDAARD})
        self.stats.setdefault("dagdoel", {})["config"] = cfg

    def daglog(self, dag=None):
        """Wat je vandaag per onderdeel goed had — de bron voor de stipjes in de kalender."""
        d = self.stats.setdefault("dagdoel", {})
        return d.setdefault("log", {}).setdefault(dag or vandaag(), {})

    def dagdoel_plus(self, soort, n=1):
        """Eén goed antwoord bijschrijven op het dagdoel van dit onderdeel."""
        lg = self.daglog()
        lg[soort] = int(lg.get(soort, 0)) + int(n)

    def woorden_vandaag(self):
        """Hoeveel verschillende woorden je vandaag hebt gehad. Hetzelfde woord twee keer
        overhoren telt één keer; afgeleid uit laatst_geoefend, dus ook na opnieuw inloggen."""
        vd = vandaag()
        return sum(1 for w in self.woorden if str(w.get("laatst_geoefend", "")) == vd)

    def dagstreak(self):
        """Aantal dagen op rij dat je iets hebt geoefend. Heb je vandaag nog niets gedaan,
        dan blijft de reeks t/m gisteren staan — die kun je vandaag nog voortzetten."""
        dagen = self.stats.get("dag_stats") or {}
        gedaan = {d for d, n in dagen.items() if int(n or 0) > 0}
        dag = date.today()
        if dag.strftime("%Y-%m-%d") not in gedaan:
            dag -= timedelta(days=1)
        streak = 0
        while dag.strftime("%Y-%m-%d") in gedaan:
            streak += 1
            dag -= timedelta(days=1)
        return streak

    # ---------------------------------------------------------------- verwarparen
    def registreer_verwarring(self, getoond, verward):
        """Vastleggen dat je deze twee woorden door elkaar haalde. Zelfde vorm als in de
        Streamlit-app, zodat 'Mijn verwarwoorden' in beide apps dezelfde paren toont."""
        if not getoond or not verward or getoond == verward:
            return
        vs = self.stats.setdefault("verwar_stats", {})
        rec = vs.setdefault(getoond, {}).setdefault(verward, {"n": 0, "laatst": ""})
        rec["n"] = int(rec.get("n", 0)) + 1
        rec["laatst"] = vandaag()

    def verzwak_verwarring(self, getoond):
        """Een goed antwoord dempt de verwarringen van dit woord; op nul verdwijnt het paar.
        Zo verlaat een woord vanzelf de lijst zodra het weer goed gaat."""
        vs = self.stats.get("verwar_stats")
        if not isinstance(vs, dict) or getoond not in vs:
            return
        entry = vs[getoond]
        for ander in list(entry):
            entry[ander]["n"] = int(entry[ander].get("n", 0)) - 1
            if entry[ander]["n"] <= 0:
                del entry[ander]
                # cumulatieve teller voor de 'Ontward'-badge (opgeloste verwarringen)
                bd = self.stats.setdefault("badges", {})
                bd["_verwar_opgelost"] = int(bd.get("_verwar_opgelost", 0)) + 1
        if not entry:
            del vs[getoond]

    # ---------------------------------------------------------------- opslaan
    def _verzamel_vocab(self):
        """Woordenlijst terug naar het compacte opslagformaat. Woorden waar nog
        niets mee gebeurd is blijven weg, net als in de Streamlit-app."""
        uit = {}
        for w in self.woorden:
            s = int(w.get("streak", 0)); g = int(w.get("score_goed", 0))
            f = int(w.get("score_fout", 0)); l = w.get("laatst_geoefend", "")
            if s or g or f or l:
                e = {"streak": s, "g": g, "f": f}
                if l:
                    e["laatst_geoefend"] = l
                if w.get("laatst_fout"):
                    e["lf"] = w["laatst_fout"]
                uit[w["grieks"]] = e
        return uit

    def bewaar(self, forceer=False):
        """Wegschrijven naar de Sheet. Bij een fout blijft alles in het geheugen staan
        en wordt het bij de volgende poging opnieuw geprobeerd."""
        if not forceer and self.sinds_opslag == 0:
            return False
        if not self._slot.acquire(blocking=forceer):
            return False          # er loopt er al een; die schrijft de nieuwste staat weg
        try:
            self.stats["vocab_stats"] = self._verzamel_vocab()
            if self.hebreeuws:
                self.stats["hebr_stats"] = self._verzamel_hebreeuws()
            try:
                opslag.bewaar(self.sleutel, self.stats)
                self.sinds_opslag = 0
                self.laatste_fout = None
                return True
            except opslag.OpslagFout as e:
                self.laatste_fout = str(e)
                return False
        finally:
            self._slot.release()

    # ---------------------------------------------------------------- overzicht
    def samenvatting(self):
        v = self.stats.get("vocab_stats") or {}
        goed = sum(int(e.get("g", 0)) for e in v.values())
        fout = sum(int(e.get("f", 0)) for e in v.values())
        return {
            "geoefend": len(v),
            "beheerst": sum(1 for e in v.values() if int(e.get("streak", 0)) >= 16),
            "goed": goed,
            "fout": fout,
            "accuratesse": round(100 * goed / (goed + fout)) if goed + fout else 0,
            "dagen": len(self.stats.get("dag_stats") or {}),
            "vandaag": int((self.stats.get("dag_stats") or {}).get(vandaag(), 0)),
        }


def fase_van(streak):
    """Dezelfde vier fasen als de Streamlit-app."""
    s = int(streak or 0)
    if s == 0:
        return "Nieuw"
    if s <= 15:
        return "In training"
    if s <= 29:
        return "Beheerst"
    return "Mastery"


def woord_opbouw(lemma, woordenlijst):
    """Voorzetsel-voorvoegsel + grondwoord, maar alleen als dat grondwoord zélf ook in
    de lijst staat (bv. εἰσέρχομαι = εἰς + ἔρχομαι). Zo verzint de app geen etymologie.

    Zelfde logica als woord_opbouw() in overhoring_web.py; die kon niet mee naar de
    motor omdat hij de woordenlijst uit st.session_state haalde. Hier is het een
    gewone parameter.
    """
    lk = motor._opb_kaal(lemma)
    if len(lk) < 5:
        return None
    idx = {}
    for w in woordenlijst:
        g = str(w.get("grieks", "") or "")
        if g:
            idx.setdefault(motor._opb_kaal(g), g)
    for p in sorted(motor._VOORZETSEL_INFO, key=len, reverse=True):
        if not lk.startswith(p) or len(lk) - len(p) < 3:
            continue
        grond = idx.get(lk[len(p):])
        if grond and motor._opb_kaal(grond) != lk:
            weer, bet = motor._VOORZETSEL_INFO[p]
            return {"voorzetsel": weer, "betekenis": bet, "grondwoord": grond}
    return None


def inloggen(naam, code, interval=OPSLAG_INTERVAL):
    """Geeft een geladen Gebruiker, of werpt OpslagFout met een leesbare melding."""
    if not str(naam).strip() or not str(code).strip():
        raise opslag.OpslagFout("Vul allebei de velden in.")
    return Gebruiker(naam, code, interval).laad()
