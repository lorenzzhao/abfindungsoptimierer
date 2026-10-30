# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Data model for the personal input file (namespace urn:abfindung:persoenlich:v1).

The model covers the complete schema so that a file can be read, modified and
written back (round trip). Every value carries its ``herkunft`` (origin).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date

from lxml import etree

NS_URI = "urn:abfindung:persoenlich:v1"
NS = {"p": NS_URI}

UNCERTAIN = ("annahme",)
HERKUNFT_LABEL = {
    "angabe": "Angabe", "abgeleitet": "abgeleitet",
    "annahme": "Annahme", "planung": "Planung", "illustrativ": "illustrativ", "berechnet": "berechnet",
}


@dataclass
class Val:
    value: object
    herkunft: str
    hinweis: str | None = None
    jahr: int | None = None

    @property
    def uncertain(self) -> bool:
        return self.herkunft in UNCERTAIN


@dataclass
class Alternative:
    id: str
    art: str
    ende: date
    herkunft: str
    freistellung_ab: date | None = None


@dataclass
class Auszahlungsfenster:
    fruehestens: tuple[int, int]   # (year, month)
    spaetestens_monate: int        # latest payment = exit month + this many months
    herkunft: str


@dataclass
class Veranlagungswahl:
    jahr: int
    art: str                       # auto | zusammen | einzel
    sonderausgaben_haelftig: bool = False


@dataclass
class Person:
    id: str
    rolle: str
    geburtsdatum: date
    steuerklasse: str
    bz_jahre: Val
    kfrist_monate: Val
    gehaelter: list[Val]
    geplantes_ende: Val
    alternativen: list[Alternative]
    rv_pflichtig: Val
    abfindung: Val
    fuenftel_ok: Val
    kv_status: Val
    kv_beitrag_freiwillig: Val
    alg_monat: Val
    alg_satz: Val
    sperrzeit_erwartet: Val
    auszahlungsfenster: Auszahlungsfenster | None = None

    def gehalt(self, year: int) -> Val | None:
        for g in self.gehaelter:
            if g.jahr == year:
                return g
        return None


@dataclass
class Child:
    id: str
    geburtsjahr: int
    kindergeld: bool


@dataclass
class Household:
    familienstand: str
    veranlagung: str
    kirchensteuer: Val
    bundesland: Val
    finanzamt: Val | None
    kinder: list[Child]
    betreuungskosten: list[Val]


@dataclass
class PersonVal:
    person: str
    val: Val


@dataclass
class Vermietung:
    anzahl: int
    einkuenfte: list[PersonVal]
    angeschafft3j: Val | None


@dataclass
class MParam:
    name: str
    value: float
    einheit: str
    herkunft: str
    hinweis: str | None = None
    jahr: int | None = None


@dataclass
class Massnahme:
    id: str
    art: str
    jahr: int
    bezeichnung: str
    params: list[MParam]
    person: str | None = None
    afa_art: str | None = None

    def get(self, name: str, default=None):
        for p in self.params:
            if p.name == name:
                return p.value
        return default


@dataclass
class Annahme:
    id: str
    value: str
    einheit: str
    herkunft: str
    hinweis: str | None = None


@dataclass
class PersonalData:
    version: str = "1.0"
    beschreibung: str = ""
    stand: date = field(default_factory=date.today)
    meta_hinweise: list[str] = field(default_factory=list)
    household: Household | None = None
    persons: list[Person] = field(default_factory=list)
    vermietung: Vermietung | None = None
    kapital: list[PersonVal] = field(default_factory=list)
    massnahmen: list[Massnahme] = field(default_factory=list)
    annahmen: list[Annahme] = field(default_factory=list)
    veranlagungswahl: list[Veranlagungswahl] = field(default_factory=list)
    path: str = ""
    migration_notes: list = field(default_factory=list)  # changes made when reading an older file

    def person(self, pid: str) -> Person:
        for p in self.persons:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def annahme(self, aid: str) -> Annahme | None:
        for a in self.annahmen:
            if a.id == aid:
                return a
        return None

    def annahme_float(self, aid: str, default: float | None = None) -> float | None:
        a = self.annahme(aid)
        if a is None:
            return default
        try:
            return float(a.value)
        except ValueError:
            return default

    def set_annahme(self, aid: str, value: str, einheit: str = "keine", herkunft: str = "planung",
                    hinweis: str | None = None) -> None:
        a = self.annahme(aid)
        if a is None:
            self.annahmen.append(Annahme(aid, value, einheit, herkunft, hinweis))
        else:
            if a.value != value:
                a.herkunft = herkunft
            a.value, a.einheit = value, einheit
            if hinweis is not None:
                a.hinweis = hinweis

    def massnahme(self, art: str) -> Massnahme | None:
        for m in self.massnahmen:
            if m.art == art:
                return m
        return None

    def clone(self) -> "PersonalData":
        return copy.deepcopy(self)


# -- parsing -----------------------------------------------------------------

def _t(el, path):
    v = el.findtext(path, namespaces=NS)
    return v.strip() if v is not None else None


def _bool(s) -> bool:
    return (s or "").strip().lower() in ("true", "1")


def _num(s: str) -> float:
    return float(s.strip())


def _val(el, kind: str = "num") -> Val | None:
    if el is None:
        return None
    raw = (el.text or "").strip()
    if kind == "num":
        v = _num(raw)
    elif kind == "bool":
        v = _bool(raw)
    elif kind == "date":
        v = date.fromisoformat(raw)
    else:
        v = raw
    jahr = el.get("jahr")
    return Val(v, el.get("herkunft"), el.get("hinweis"), int(jahr) if jahr else None)


def _f(el, tag):
    return el.find(f"p:{tag}", NS)


def _gym(s: str) -> tuple[int, int]:
    y, m = s.split("-")[:2]
    return int(y), int(m)


def _fenster(el) -> Auszahlungsfenster | None:
    if el is None:
        return None
    return Auszahlungsfenster(_gym(el.get("fruehestens")), int(el.get("spaetestensMonateNachAustritt")),
                              el.get("herkunft"))


def parse_personal(root: etree._Element) -> PersonalData:
    d = PersonalData(version=root.get("version", "1.0"))
    meta = _f(root, "Metadaten")
    d.beschreibung = _t(meta, "p:Beschreibung") or ""
    d.stand = date.fromisoformat(_t(meta, "p:Stand"))
    d.meta_hinweise = [(h.text or "").strip() for h in meta.findall("p:Hinweis", NS)]

    h = _f(root, "Haushalt")
    d.household = Household(
        familienstand=_t(h, "p:Familienstand"), veranlagung=_t(h, "p:Veranlagungsart"),
        kirchensteuer=_val(_f(h, "Kirchensteuerpflichtig"), "bool"),
        bundesland=_val(_f(h, "Bundesland"), "text"), finanzamt=_val(_f(h, "Finanzamt"), "text"),
        kinder=[Child(k.get("id"), int(_t(k, "p:Geburtsjahr")[:4]), _bool(_t(k, "p:Kindergeldbezug")))
                for k in h.findall("p:Kinder/p:Kind", NS)],
        betreuungskosten=[_val(b) for b in h.findall("p:Kinderbetreuungskosten", NS)],
    )

    for pe in root.findall("p:Personen/p:Person", NS):
        b = _f(pe, "Beschaeftigung")
        a = _f(pe, "Abfindung")
        kv = _f(pe, "Krankenversicherung")
        alg = _f(pe, "Arbeitslosengeld")
        alts = []
        for al in b.findall("p:Alternative", NS):
            fa = al.get("freistellungAb")
            alts.append(Alternative(al.get("id"), al.get("art"), date.fromisoformat(al.get("ende")),
                                    al.get("herkunft"), date.fromisoformat(fa) if fa else None))
        d.persons.append(Person(
            id=pe.get("id"), rolle=pe.get("rolle"),
            geburtsdatum=date.fromisoformat(_t(pe, "p:Geburtsdatum")), steuerklasse=_t(pe, "p:Steuerklasse"),
            bz_jahre=_val(_f(b, "BetriebszugehoerigkeitJahre")),
            kfrist_monate=_val(_f(b, "KuendigungsfristArbeitgeberMonate")),
            gehaelter=[_val(g) for g in b.findall("p:Bruttogehalt", NS)],
            geplantes_ende=_val(_f(b, "GeplantesEnde"), "date"), alternativen=alts,
            rv_pflichtig=_val(_f(b, "Rentenversicherungspflichtig"), "bool"),
            abfindung=_val(_f(a, "Betrag")), fuenftel_ok=_val(_f(a, "FuenftelregelungVoraussetzungen"), "bool"),
            kv_status=_val(_f(kv, "Status"), "text"), kv_beitrag_freiwillig=_val(_f(kv, "BeitragFreiwilligMonat")),
            alg_monat=_val(_f(alg, "BetragMonat")), alg_satz=_val(_f(alg, "Leistungssatz")),
            sperrzeit_erwartet=_val(_f(alg, "SperrzeitErwartet"), "bool"),
            auszahlungsfenster=_fenster(_f(pe, "Auszahlungsfenster")),
        ))

    v = _f(root, "Vermietung")
    d.vermietung = Vermietung(
        anzahl=int(_t(v, "p:AnzahlObjekte")),
        einkuenfte=[PersonVal(e.get("person"), _val(e)) for e in v.findall("p:Einkuenfte", NS)],
        angeschafft3j=_val(_f(v, "ObjekteAngeschafftInLetzten3Jahren"), "bool"),
    )
    d.kapital = [PersonVal(e.get("person"), _val(e)) for e in root.findall("p:Kapitalertraege/p:Ertrag", NS)]

    pl = _f(root, "Planung")
    for m in pl.findall("p:Massnahmen/p:Massnahme", NS):
        params = []
        for pa in m.findall("p:Parameter", NS):
            j = pa.get("jahr")
            params.append(MParam(pa.get("name"), _num(pa.text), pa.get("einheit"), pa.get("herkunft"),
                                 pa.get("hinweis"), int(j) if j else None))
        d.massnahmen.append(Massnahme(m.get("id"), m.get("art"), int(m.get("jahr")[:4]),
                                      _t(m, "p:Bezeichnung") or "", params, m.get("person"), m.get("afaArt")))
    for an in pl.findall("p:Annahmen/p:Annahme", NS):
        d.annahmen.append(Annahme(an.get("id"), (an.text or "").strip(), an.get("einheit"),
                                  an.get("herkunft"), an.get("hinweis")))

    for vw in pl.findall("p:Veranlagungswahl", NS):
        d.veranlagungswahl.append(Veranlagungswahl(int(vw.get("jahr")[:4]), vw.get("art"),
                                                   _bool(vw.get("sonderausgabenHaelftig", "false"))))

    return d


# -- serialisation -----------------------------------------------------------

def _q(tag: str) -> str:
    return f"{{{NS_URI}}}{tag}"


def _fmt_num(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        f = float(v)
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        return f"{f:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _sub(parent, tag: str, text=None, **attrs):
    el = etree.SubElement(parent, _q(tag))
    for k, v in attrs.items():
        if v is not None:
            el.set(k, _fmt_num(v) if not isinstance(v, str) else v)
    if text is not None:
        el.text = _fmt_num(text)
    return el


def _sub_val(parent, tag: str, val: Val, **extra):
    attrs = {"herkunft": val.herkunft}
    if val.jahr is not None:
        attrs["jahr"] = str(val.jahr)
    attrs.update(extra)
    if val.hinweis:
        attrs["hinweis"] = val.hinweis
    return _sub(parent, tag, val.value, **attrs)


def to_xml(d: PersonalData) -> etree._ElementTree:
    root = etree.Element(_q("PersoenlicheDaten"), nsmap={None: NS_URI})
    root.set("version", d.version)
    meta = _sub(root, "Metadaten")
    _sub(meta, "Beschreibung", d.beschreibung)
    _sub(meta, "Stand", d.stand)
    _sub(meta, "Waehrung", "EUR")
    for hi in d.meta_hinweise:
        _sub(meta, "Hinweis", hi)

    h = d.household
    he = _sub(root, "Haushalt")
    _sub(he, "Familienstand", h.familienstand)
    _sub(he, "Veranlagungsart", h.veranlagung)
    _sub_val(he, "Kirchensteuerpflichtig", h.kirchensteuer)
    _sub(he, "Bundesland", h.bundesland.value, herkunft=h.bundesland.herkunft)
    if h.finanzamt is not None:
        _sub(he, "Finanzamt", h.finanzamt.value, herkunft=h.finanzamt.herkunft)
    ke = _sub(he, "Kinder")
    for k in h.kinder:
        kel = _sub(ke, "Kind", id=k.id)
        _sub(kel, "Geburtsjahr", str(k.geburtsjahr))
        _sub(kel, "Kindergeldbezug", k.kindergeld)
    for b in h.betreuungskosten:
        _sub_val(he, "Kinderbetreuungskosten", b)

    pse = _sub(root, "Personen")
    for p in d.persons:
        pe = _sub(pse, "Person", id=p.id, rolle=p.rolle)
        _sub(pe, "Geburtsdatum", p.geburtsdatum)
        _sub(pe, "Steuerklasse", p.steuerklasse)
        b = _sub(pe, "Beschaeftigung")
        _sub_val(b, "BetriebszugehoerigkeitJahre", p.bz_jahre)
        _sub_val(b, "KuendigungsfristArbeitgeberMonate", p.kfrist_monate)
        for g in p.gehaelter:
            _sub_val(b, "Bruttogehalt", g)
        _sub_val(b, "GeplantesEnde", p.geplantes_ende)
        for al in p.alternativen:
            _sub(b, "Alternative", id=al.id, art=al.art,
                 freistellungAb=al.freistellung_ab.isoformat() if al.freistellung_ab else None,
                 ende=al.ende.isoformat(), herkunft=al.herkunft)
        _sub_val(b, "Rentenversicherungspflichtig", p.rv_pflichtig)
        a = _sub(pe, "Abfindung")
        _sub_val(a, "Betrag", p.abfindung)
        _sub_val(a, "FuenftelregelungVoraussetzungen", p.fuenftel_ok)
        kv = _sub(pe, "Krankenversicherung")
        _sub(kv, "Status", p.kv_status.value, herkunft=p.kv_status.herkunft)
        _sub_val(kv, "BeitragFreiwilligMonat", p.kv_beitrag_freiwillig)
        alg = _sub(pe, "Arbeitslosengeld")
        _sub_val(alg, "BetragMonat", p.alg_monat)
        _sub_val(alg, "Leistungssatz", p.alg_satz)
        _sub_val(alg, "SperrzeitErwartet", p.sperrzeit_erwartet)
        if p.auszahlungsfenster is not None:
            f = p.auszahlungsfenster
            _sub(pe, "Auszahlungsfenster", fruehestens=f"{f.fruehestens[0]:04d}-{f.fruehestens[1]:02d}",
                 spaetestensMonateNachAustritt=str(f.spaetestens_monate), herkunft=f.herkunft)

    v = d.vermietung
    ve = _sub(root, "Vermietung")
    _sub(ve, "AnzahlObjekte", str(v.anzahl))
    for e in v.einkuenfte:
        _sub_val(ve, "Einkuenfte", e.val, person=e.person)
    if v.angeschafft3j is not None:
        _sub_val(ve, "ObjekteAngeschafftInLetzten3Jahren", v.angeschafft3j)
    ke = _sub(root, "Kapitalertraege")
    for e in d.kapital:
        _sub_val(ke, "Ertrag", e.val, person=e.person)

    pl = _sub(root, "Planung")
    ms = _sub(pl, "Massnahmen")
    for m in d.massnahmen:
        me = _sub(ms, "Massnahme", id=m.id, art=m.art, jahr=str(m.jahr), person=m.person, afaArt=m.afa_art)
        _sub(me, "Bezeichnung", m.bezeichnung)
        for pa in m.params:
            _sub(me, "Parameter", pa.value, herkunft=pa.herkunft,
                 jahr=str(pa.jahr) if pa.jahr else None, hinweis=pa.hinweis, name=pa.name, einheit=pa.einheit)
    an = _sub(pl, "Annahmen")
    for a in d.annahmen:
        _sub(an, "Annahme", a.value, id=a.id, einheit=a.einheit, herkunft=a.herkunft, hinweis=a.hinweis)
    for vw in d.veranlagungswahl:
        _sub(pl, "Veranlagungswahl", jahr=str(vw.jahr), art=vw.art,
             sonderausgabenHaelftig="true" if vw.sonderausgaben_haelftig else "false")

    return etree.ElementTree(root)
