# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""All adjustable inputs ("Stellschrauben") of a scenario.

Settings are derived from the personal XML (:func:`from_personal`) and written back
(:func:`to_personal`). Values without an own schema element are stored as
``Planung/Annahmen/Annahme id="ui_..."`` so the exported file stays schema-valid.
Each value has an origin (``herkunft``) and, if it comes from the XML, a source path.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from datetime import date, timedelta

from ..dates import add_months, days_in_month, month_index
from ..io.personal_model import (Auszahlungsfenster, Child, Massnahme, MParam, PersonalData, Person, PersonVal, Val,
                                 Veranlagungswahl)


@dataclass
class PersonSettings:
    id: str = ""
    label: str = ""
    rolle: str = ""
    birth: date = date(1980, 1, 1)
    steuerklasse: str = "IV"
    bz_jahre: float = 0.0
    kfrist_monate: float = 0.0
    vorbeschaeftigung_monate: int = 60
    salary: dict = field(default_factory=dict)  # year -> gross wage (meaning see salary_mode)
    salary_mode: str = "jahr"  # "jahr": gross for a full year of employment, "real": gross actually paid in the year
    austritt: bool = True  # False: no exit – the employment continues (no severance, no ALG)
    alg_aktiv: bool = True  # False: no unemployment benefit is claimed (no registration with the Agentur)
    kv_aktiv: bool = True   # False: KV/PV of the person is not calculated (no contributions, no Vorsorge deduction)
    end_date: date = date(2026, 12, 31)
    freistellung: bool = False
    freistellung_ab: date = date(2026, 12, 1)
    vertragsschluss: date = date(2026, 1, 1)
    severance: float = 0.0
    pay_idx: int = 0            # month index (year*12 + month-1) of the (main) payment
    fenster_aktiv: bool = False  # payment window from the severance offer (R_Faelligkeit)
    fenster_ab_idx: int = 0      # earliest payment month (month index)
    fenster_monate: int = 36     # latest payment = exit month + this many months
    fuenftel_ok: bool = True
    rv_pflichtig: bool = True
    sperrzeit_wochen: int = 0
    sperrzeit_ab_freistellung: bool = True
    arbeitsuchend_datum: date = date(2026, 1, 1)
    meldung: date = date(2027, 1, 1)
    alg_monat: float = 0.0
    urlaub_tage: int = 0
    newjob: bool = False
    newjob_start: date = date(2028, 1, 1)
    newjob_salary: float = 0.0
    kv_status: str = "pflichtversichert"
    kv_beitrag_schaetzung: float = 0.0
    kv_sonstige_einnahmen: float = 0.0
    bonus: float = 0.0
    bonus_year: int = 2027
    werbungskosten: float = 0.0
    rent: dict = field(default_factory=dict)     # year -> Einkünfte V+V
    capital: dict = field(default_factory=dict)  # year -> Kapitalerträge
    geplantes_ende: date = date(2026, 12, 31)    # planned end from the XML (reference for alternatives)
    alternativen: list = field(default_factory=list)  # [(id, art, ende, freistellung_ab | None)]

    def salary_for(self, year: int) -> tuple[float, int | None]:
        """Entered gross for a year; missing years are carried forward (returns source year)."""
        return _for_year(self.salary, year)

    def employed_months(self, year: int) -> float:
        """Months of the year in the previous employment (until the exit date), as a fraction."""
        if not self.austritt:
            return 12.0
        e = self.end_date
        if year > e.year:
            return 0.0
        if year < e.year:
            return 12.0
        return (e.month - 1) + e.day / days_in_month(e.year, e.month)

    def annual_equiv(self, year: int) -> float:
        """Gross for a full year of employment (basis for monthly wages, ALG and § 158 SGB III)."""
        v, src = self.salary_for(year)
        if self.salary_mode != "real" or src is None:
            return v
        em = self.employed_months(src)
        if em > 0:
            return v * 12 / em
        earlier = [y for y in self.salary if y < src and self.employed_months(y) > 0]
        return self.annual_equiv(max(earlier)) if earlier else v

    def prorated(self, year: int) -> float:
        """Gross paid in the year up to the exit date."""
        return self.annual_equiv(year) * self.employed_months(year) / 12

    def rent_for(self, year: int):
        return _for_year(self.rent, year)

    def capital_for(self, year: int):
        return _for_year(self.capital, year)

    @property
    def exit_idx(self) -> int:
        return month_index(self.end_date.year, self.end_date.month)

    def window(self) -> tuple[int, int] | None:
        """(earliest, latest) payment month index, or None if no window is set."""
        if not self.fenster_aktiv:
            return None
        return self.fenster_ab_idx, self.exit_idx + self.fenster_monate

    @property
    def pay_year(self) -> int:
        return self.pay_idx // 12

    @property
    def pay_month(self) -> int:
        return self.pay_idx % 12 + 1


def _for_year(d: dict, year: int):
    if not d:
        return 0.0, None
    if year in d:
        return d[year], year
    earlier = [y for y in d if y < year]
    y = max(earlier) if earlier else min(d)
    return d[y], y


# Kinds of Gestaltungen: key -> (label in the GUI, art in the XML, default Gegenwert)
GESTALTUNG_TYPEN = {
    "basisrente": ("Basisrente (Rürup)", "Basisrente", 1.0),
    "erhaltung": ("Erhaltungsaufwand (bestehende Mietobjekte)", "Erhaltungsaufwand", 1.0),
    "spende": ("Spende", "Spende", 0.0),
    "kauf": ("Immobilienkauf (vermietet)", "Immobilienkauf", 1.0),
    "sonstige": ("Sonstige Gestaltung", "Sonstige", 0.0),
}
ART_TO_TYP = {v[1]: k for k, v in GESTALTUNG_TYPEN.items()}
# Fields of a property purchase (kept in the entry; "illustrativ" allowed as origin)
KAUF_FIELDS = ("kaufpreis", "gebaeudeanteil", "nebenkosten_anteil", "afa_art", "darlehen", "zins", "disagio_anteil",
               "zinsbindung_jahre", "miete_jahr", "ortsuebliche_miete_jahr", "bewirtschaftung_jahr", "kauf_erhaltung")
# XML parameter name -> unit
PARAM_UNITS = {"betrag": "EUR", "monat": "Anzahl", "gegenwert": "Anteil", "abziehbar": "Anteil", "kaufpreis": "EUR",
               "gebaeudeanteil": "Anteil", "nebenkosten_anteil": "Anteil", "darlehen": "EUR", "zins": "Anteil",
               "disagio_anteil": "Anteil", "zinsbindung_jahre": "Jahre", "miete_jahr": "EUR_pro_Jahr",
               "ortsuebliche_miete_jahr": "EUR_pro_Jahr", "bewirtschaftung_jahr": "EUR_pro_Jahr", "kauf_erhaltung": "EUR"}


@dataclass
class Gestaltung:
    """One Gestaltung (several per kind and year possible).

    Gegenwert: share of the amount kept as wealth / personal value; only (1 − share) counts as expense in the
    Saldo, the tax effect always counts in full. For a purchase it refers to the running net costs."""
    typ: str = "basisrente"
    jahr: int = 2027              # year of payment (purchase: year of the transfer of possession)
    betrag: float = 0.0           # not used for a purchase (see kaufpreis …)
    monat: int = 12               # month of payment (liquidity); purchase: month of the transfer
    gegenwert: float = 1.0
    name: str = ""                # sonstige: what it is
    abziehbar: float = 1.0        # sonstige: deductible share of the amount
    person: str = ""              # sonstige: id of the person whose income is reduced
    kaufpreis: float = 0.0
    gebaeudeanteil: float = 0.8
    nebenkosten_anteil: float = 0.1
    afa_art: str = "standard"     # standard | ab2023 | vor1925 | degressiv
    darlehen: float = 0.0
    zins: float = 0.04
    disagio_anteil: float = 0.0
    zinsbindung_jahre: int = 10
    miete_jahr: float = 0.0
    ortsuebliche_miete_jahr: float = 0.0
    bewirtschaftung_jahr: float = 0.0
    kauf_erhaltung: float = 0.0

    @property
    def label(self) -> str:
        base = self.name if self.typ == "sonstige" and self.name else GESTALTUNG_TYPEN[self.typ][0]
        return f"{base} {self.jahr}"

    def params(self) -> list[str]:
        """Parameter names stored in the XML for this kind."""
        if self.typ == "kauf":
            return ["monat", "gegenwert"] + [f for f in KAUF_FIELDS if f != "afa_art"]
        out = ["betrag", "monat", "gegenwert"]
        if self.typ == "sonstige":
            out.append("abziehbar")
        return out


@dataclass
class Measures:
    items: dict = field(default_factory=dict)  # id -> Gestaltung


def gestaltungen(s, typ: str | None = None, year: int | None = None) -> list:
    """[(id, Gestaltung)] filtered by kind and year, sorted by year and kind."""
    out = [(gid, g) for gid, g in s.measures.items.items()
           if (typ is None or g.typ == typ) and (year is None or g.jahr == year)]
    return sorted(out, key=lambda x: (x[1].jahr, list(GESTALTUNG_TYPEN).index(x[1].typ), x[0]))


def new_gestaltung_id(s, taken=()) -> str:
    n = 1
    while f"G{n}" in s.measures.items or f"G{n}" in taken:
        n += 1
    return f"G{n}"


def add_gestaltung(s, typ: str, jahr: int, _taken=(), **values) -> str:
    gid = new_gestaltung_id(s, _taken)
    g = Gestaltung(typ=typ, jahr=jahr, gegenwert=GESTALTUNG_TYPEN[typ][2],
                   monat=1 if typ == "kauf" else 12, person=s.persons[0].id if s.persons else "")
    for k, v in values.items():
        setattr(g, k, v)
    s.measures.items[gid] = g
    return gid


def remove_gestaltung(s, gid: str) -> None:
    s.measures.items.pop(gid, None)
    prefix = f"measures.items.{gid}."
    for d in (s.origin, s.xml_paths):
        for k in [k for k in d if k.startswith(prefix)]:
            del d[k]


def set_basisrente_year(s, year: int, amount: float) -> None:
    """Optimiser proposal: the planned Basisrente of a year (an entry is created when there is none)."""
    planned = [gid for gid, g in gestaltungen(s, "basisrente", year)
               if s.origin_of(f"measures.items.{gid}.betrag") == "planung"]
    if planned:
        s.set(f"measures.items.{planned[0]}.betrag", amount)
        for gid in planned[1:]:
            s.set(f"measures.items.{gid}.betrag", 0.0)
    elif amount:
        add_gestaltung(s, "basisrente", year, betrag=amount)


@dataclass
class Options:
    horizon_auto: bool = True  # exit year … latest possible payment year / end of ALG (Ä1)
    horizon_start: int = 2026
    horizon_end: int = 2028
    gegenwert_arbeitszeit: float = 0.0  # value of the free time vs. the net salary: (1 − share) of the salary counts
    # Lohnsteuer-Freibetrag (ELStAM): only changes the monthly wage-tax deduction (liquidity), not the annual tax
    lst_freibetrag: float = 0.0
    lst_freibetrag_year: int = 2027
    lst_antrag_datum: date = date(2026, 10, 1)
    church: bool = False
    bundesland: str = ""
    kv_zusatz: float = 0.0
    kv_satz_allgemein: bool = False
    kv_abfindung_mode: int = 1   # 1 nicht verbeitragt, 2 Fristzeitraum, 3 verteilt
    kv_nachgehend_vorrang: bool = True
    tarif_index: float = 0.0
    vorsorge_factor: float = 1.0
    ein_jahres_regel: bool = True
    ein_jahres_ereignis: str = "vertragsende"  # or "freistellung"
    guenstiger_mode: str = "voll"  # voll | tarif
    bescheid_monat: int = 6
    sozialabgaben_anteil: float = 0.2
    rv_satz_annahme: float = 0.0  # used only if rv_beitragssatz_gesamt is missing in the legal XML


SECTIONS = {
    "haushalt": "Haushalt",
    "kv": "Krankenversicherung",
    "gestaltungen": "Gestaltungen",
    "optionen": "Optionen (Horizont, Rechtsfragen)",
}


# Allowed origins (herkunft) per kind of value – the same groups as the types in personal_data.xsd:
FAKT = ("angabe", "annahme")                          # facts that may be uncertain
ABLEITBAR = ("angabe", "annahme", "abgeleitet")       # facts that can also be derived from other values
PLAN = ("planung", "angabe", "annahme")               # Stellschrauben (optimised when "planung")
EINSTELLUNG = ("angabe",)                             # pure tool settings (the user's choice)

ORIGINS_PERSON = {
    **dict.fromkeys(("bz_jahre", "salary", "rv_pflichtig", "rent", "capital", "werbungskosten",
                     "vorbeschaeftigung_monate", "kv_sonstige_einnahmen"), FAKT),
    **dict.fromkeys(("fuenftel_ok", "kfrist_monate", "kv_status", "kv_beitrag_schaetzung", "alg_monat",
                     "sperrzeit_wochen"), ABLEITBAR),
    **dict.fromkeys(("end_date", "severance", "pay_idx", "fenster_aktiv", "fenster_ab_idx",
                     "fenster_monate", "meldung", "newjob", "newjob_start",
                     "newjob_salary"), PLAN),
    "vertragsschluss": PLAN + ("abgeleitet",),        # can be derived from the end of the notice period
    "arbeitsuchend_datum": PLAN + ("abgeleitet",),    # latest date without a Sperrzeit (derived by the program)
}
ORIGINS_OPTIONS = {
    **dict.fromkeys(("church", "tarif_index", "sozialabgaben_anteil", "rv_satz_annahme", "gegenwert_arbeitszeit"), FAKT),
    **dict.fromkeys(("bundesland", "kv_zusatz", "vorsorge_factor"), ABLEITBAR),
}

# Tool settings that are genuine assumptions (default origin "annahme" when the XML has none).
ASSUMPTIONS_PERSON = {"vorbeschaeftigung_monate", "kv_sonstige_einnahmen"}
ASSUMPTIONS = {"options.tarif_index", "options.gegenwert_arbeitszeit"}


# Values the program can determine itself when their origin is "abgeleitet" (see scenario: ctx.derived).
PROGRAM_DERIVED_PERSON = {"fuenftel_ok", "kfrist_monate", "kv_status", "sperrzeit_wochen", "arbeitsuchend_datum",
                          "kv_beitrag_schaetzung", "alg_monat"}


def is_program_derived(path: str) -> bool:
    parts = path.split(".")
    return parts[0] == "persons" and len(parts) > 2 and parts[2] in PROGRAM_DERIVED_PERSON


def allowed_origins(path: str) -> tuple:
    """Origins that make sense for a value (choice in the GUI, check when setting)."""
    parts = path.split(".")
    head = parts[0]
    if head == "persons" and len(parts) > 2:
        return ORIGINS_PERSON.get(parts[2], EINSTELLUNG)
    if head == "options":
        return ORIGINS_OPTIONS.get(parts[1], EINSTELLUNG)
    if head in ("childcare", "objekte_angeschafft_3j"):
        return FAKT
    if head == "measures" and len(parts) > 3:  # measures.items.<id>.<field>
        f_ = parts[3]
        if f_ in ("gegenwert", "abziehbar"):
            return FAKT  # personal valuation / legal assessment
        if f_ in ("betrag", "monat"):
            return PLAN
        if f_ in KAUF_FIELDS and f_ != "afa_art":
            return PLAN + ("illustrativ",)
        return EINSTELLUNG  # kind, year, name, person, AfA kind
    if head in ("veranlagung", "sa_haelftig"):
        return PLAN
    return EINSTELLUNG


def is_planbar(path: str) -> bool:
    """Value can be influenced; only these may have the origin "planung" (and are optimised then)."""
    return "planung" in allowed_origins(path)


def default_origin(path: str) -> str:
    """Origin of a value that has none in the XML: Planung (can be influenced), Annahme (genuine
    assumption) or Angabe (a fact or a setting chosen by the user)."""
    if is_planbar(path):
        return "planung"
    parts = path.split(".")
    if path in ASSUMPTIONS or (parts[0] == "persons" and len(parts) > 2 and parts[2] in ASSUMPTIONS_PERSON):
        return "annahme"
    if parts[0] == "measures" and parts[-1] == "gegenwert":
        return "annahme"
    return "angabe"


def _key(obj, k: str):
    return int(k) if isinstance(obj, list) or (isinstance(obj, dict) and k.lstrip("-").isdigit()) else k


@dataclass
class Settings:
    persons: list[PersonSettings] = field(default_factory=list)
    joint: bool = True
    children: list = field(default_factory=list)  # (geburtsjahr, kindergeld)
    childcare: dict = field(default_factory=dict)
    measures: Measures = field(default_factory=Measures)
    options: Options = field(default_factory=Options)
    stand: date = field(default_factory=date.today)
    objekte_angeschafft_3j: bool = False
    erhaltung_max: float = 0.0
    bescheid: dict = field(default_factory=dict)  # {"jahr": int, "posten": {id: value}}
    # Optional input areas; a disabled area is read/written but ignored by the calculation (see effective()).
    sections: dict = field(default_factory=lambda: {k: True for k in SECTIONS})
    familienstand: str = "verheiratet"  # verheiratet | ledig | geschieden | verwitwet (spouse only if verheiratet)
    veranlagung: dict = field(default_factory=dict)  # year -> auto | zusammen | einzel (R_Einzelveranlagung)
    sa_haelftig: bool = False  # single assessment: special expenses half each (§ 26a Abs. 2 EStG)
    origin: dict = field(default_factory=dict)
    xml_paths: dict = field(default_factory=dict)

    # -- path access --------------------------------------------------------
    def _resolve(self, path: str):
        parts = path.split(".")
        obj = self
        for p in parts[:-1]:
            obj = obj[_key(obj, p)] if isinstance(obj, (list, dict)) else getattr(obj, p)
        return obj, parts[-1]

    def get(self, path: str):
        obj, last = self._resolve(path)
        if isinstance(obj, list):
            return obj[int(last)]
        if isinstance(obj, dict):
            return obj.get(_key(obj, last))
        return getattr(obj, last)

    def set(self, path: str, value, user: bool = True) -> None:
        obj, last = self._resolve(path)
        if isinstance(obj, dict):
            obj[_key(obj, last)] = value
        else:
            setattr(obj, last, value)
        # The origin (herkunft) is not changed by editing a value; it is chosen explicitly
        # (badge in the GUI) and always matches the XML after loading / saving.

    def origin_of(self, path: str) -> str:
        return self.origin.get(path, default_origin(path))

    def set_origin(self, path: str, herkunft: str) -> None:
        if herkunft not in allowed_origins(path):
            raise ValueError(f"Herkunft „{herkunft}“ ist für {path} nicht vorgesehen.")
        self.origin[path] = herkunft

    def xml_path_of(self, path: str) -> str:
        return self.xml_paths.get(path, "")

    def person(self, pid: str) -> PersonSettings:
        for p in self.persons:
            if p.id == pid:
                return p
        raise KeyError(pid)

    @property
    def married(self) -> bool:
        return self.familienstand == "verheiratet"

    def veranlagung_for(self, year: int) -> str:
        """Assessment choice for a year; only married couples with two persons can choose."""
        if not self.married or len(self.persons) < 2:
            return "zusammen" if self.joint else "einzel"
        return self.veranlagung.get(year, "auto" if self.joint else "einzel")

    def active(self, section: str) -> bool:
        return self.sections.get(section, True)

    def years(self) -> list[int]:
        return list(range(self.options.horizon_start, self.options.horizon_end + 1))

    def copy(self) -> "Settings":
        return copy.deepcopy(self)


# -- construction from the personal XML -----------------------------------------------

def _num_annahme(pd: PersonalData, aid: str):
    return pd.annahme_float(aid)


def from_personal(pd: PersonalData, legal) -> Settings:
    s = Settings()
    s.stand = pd.stand
    h = pd.household
    s.familienstand = h.familienstand
    s.joint = h.veranlagung == "Zusammenveranlagung" and s.married
    s.children = [(k.geburtsjahr, k.kindergeld) for k in h.kinder]
    for b in h.betreuungskosten:
        s.childcare[b.jahr or pd.stand.year] = b.value
    o = s.options
    o.church = bool(h.kirchensteuer.value)
    o.bundesland = h.bundesland.value
    s.origin["options.church"] = h.kirchensteuer.herkunft
    s.xml_paths["options.church"] = "Haushalt/Kirchensteuerpflichtig"
    s.origin["options.bundesland"] = h.bundesland.herkunft
    s.xml_paths["options.bundesland"] = "Haushalt/Bundesland"
    for y in s.childcare:
        s.origin[f"childcare.{y}"] = next(b.herkunft for b in h.betreuungskosten if (b.jahr or pd.stand.year) == y)
        s.xml_paths[f"childcare.{y}"] = f"Haushalt/Kinderbetreuungskosten[@jahr={y}]"

    if pd.vermietung and pd.vermietung.angeschafft3j is not None:
        s.objekte_angeschafft_3j = bool(pd.vermietung.angeschafft3j.value)
        s.origin["objekte_angeschafft_3j"] = pd.vermietung.angeschafft3j.herkunft
        s.xml_paths["objekte_angeschafft_3j"] = "Vermietung/ObjekteAngeschafftInLetzten3Jahren"
    b = pd.bescheid_latest()
    if b:
        s.bescheid = {"jahr": b.jahr, "posten": {po.id: po.value for po in b.posten}}

    wk = pd.annahme("werbungskosten_je_person")

    for i, p in enumerate(pd.persons):
        ps = PersonSettings(id=p.id, rolle=p.rolle, label=_label(i), birth=p.geburtsdatum,
                            steuerklasse=p.steuerklasse)
        base = f"persons.{i}"
        xp = f"Personen/Person[@id='{p.id}']"

        def reg(fieldname, val: Val | None, xml: str, herkunft: str | None = None):
            s.origin[f"{base}.{fieldname}"] = herkunft or (val.herkunft if val else "annahme")
            s.xml_paths[f"{base}.{fieldname}"] = f"{xp}/{xml}" if xml else ""

        ps.bz_jahre = p.bz_jahre.value
        reg("bz_jahre", p.bz_jahre, "Beschaeftigung/BetriebszugehoerigkeitJahre")
        ps.kfrist_monate = p.kfrist_monate.value
        reg("kfrist_monate", p.kfrist_monate, "Beschaeftigung/KuendigungsfristArbeitgeberMonate")
        for g in p.gehaelter:
            ps.salary[g.jahr] = g.value
            reg(f"salary.{g.jahr}", g, f"Beschaeftigung/Bruttogehalt[@jahr={g.jahr}]")
        ps.end_date = p.geplantes_ende.value
        ps.geplantes_ende = p.geplantes_ende.value
        ps.alternativen = [(a.id, a.art, a.ende, a.freistellung_ab) for a in p.alternativen]
        reg("end_date", p.geplantes_ende, "Beschaeftigung/GeplantesEnde")
        ps.severance = p.abfindung.value
        reg("severance", p.abfindung, "Abfindung/Betrag")
        ps.fuenftel_ok = bool(p.fuenftel_ok.value)
        reg("fuenftel_ok", p.fuenftel_ok, "Abfindung/FuenftelregelungVoraussetzungen")
        ps.rv_pflichtig = bool(p.rv_pflichtig.value)
        reg("rv_pflichtig", p.rv_pflichtig, "Beschaeftigung/Rentenversicherungspflichtig")
        ps.kv_status = p.kv_status.value
        reg("kv_status", p.kv_status, "Krankenversicherung/Status")
        ps.kv_beitrag_schaetzung = p.kv_beitrag_freiwillig.value
        reg("kv_beitrag_schaetzung", p.kv_beitrag_freiwillig, "Krankenversicherung/BeitragFreiwilligMonat")
        ps.alg_monat = p.alg_monat.value
        reg("alg_monat", p.alg_monat, "Arbeitslosengeld/BetragMonat")

        # Sperrzeit: expected -> rule duration from the legal XML
        weeks = int(legal.value("alg_sperrzeit_arbeitsaufgabe_wochen")) if p.sperrzeit_erwartet.value else 0
        ps.sperrzeit_wochen = weeks
        reg("sperrzeit_wochen", p.sperrzeit_erwartet, "Arbeitslosengeld/SperrzeitErwartet")

        # Exit alternatives: a Freistellung runs until the end of the notice period,
        # so its end date is used to derive the date the contract was concluded.
        alt = next((a for a in p.alternativen if a.art == "Freistellung"), None)
        ps.freistellung_ab = alt.freistellung_ab if alt and alt.freistellung_ab else ps.end_date
        if alt and p.kfrist_monate.value:
            ps.vertragsschluss = add_months(alt.ende, -int(p.kfrist_monate.value))
            reg("vertragsschluss", None, "", "abgeleitet")
        else:
            ps.vertragsschluss = pd.stand
            reg("vertragsschluss", None, "", "annahme")
        reg("freistellung", None, "", "planung")
        reg("freistellung_ab", None, f"Beschaeftigung/Alternative[@id='{alt.id}']" if alt else "",
            alt.herkunft if alt else "annahme")
        ps.arbeitsuchend_datum = ps.vertragsschluss
        reg("arbeitsuchend_datum", None, "", "abgeleitet")
        reg("vorbeschaeftigung_monate", None, "", "annahme")

        # Payment month and registration date: stored as tool settings (ui_*); default the month after the exit
        nxt = add_months(ps.end_date, 1)
        ps.pay_idx = month_index(nxt.year, nxt.month)
        reg("pay_idx", None, "", "planung")
        fw = p.auszahlungsfenster
        if legal.has("abf_auszahlung_spaetestens_monate_default"):
            ps.fenster_monate = int(legal.value("abf_auszahlung_spaetestens_monate_default"))
        ps.fenster_ab_idx = ps.exit_idx
        if fw is not None:
            ps.fenster_aktiv = True
            ps.fenster_ab_idx = month_index(*fw.fruehestens)
            ps.fenster_monate = fw.spaetestens_monate
        for f_ in ("fenster_aktiv", "fenster_ab_idx", "fenster_monate"):
            reg(f_, None, "Auszahlungsfenster" if fw else "", fw.herkunft if fw else "planung")

        ps.meldung = ps.end_date + timedelta(days=1)
        reg("meldung", None, "", "planung")


        if wk is not None:
            ps.werbungskosten = float(wk.value)
            reg("werbungskosten", None, f"Planung/Annahmen/Annahme[@id='{wk.id}']", wk.herkunft)
        else:
            ps.werbungskosten = float(legal.value("est_arbeitnehmer_pauschbetrag"))
            reg("werbungskosten", None, "", "abgeleitet")

        for e in pd.vermietung.einkuenfte:
            if e.person == p.id:
                y = e.val.jahr or pd.stand.year
                ps.rent[y] = e.val.value
                reg(f"rent.{y}", e.val, f"Vermietung/Einkuenfte[@person='{p.id}'][@jahr={y}]")
        for e in pd.kapital:
            if e.person == p.id:
                y = e.val.jahr or pd.stand.year
                ps.capital[y] = e.val.value
                reg(f"capital.{y}", e.val, f"Kapitalertraege/Ertrag[@person='{p.id}'][@jahr={y}]")
        s.persons.append(ps)

    # horizon: year of the earliest exit until two years later
    o.horizon_start = min(p.end_date.year for p in s.persons)
    o.horizon_end = o.horizon_start + 2
    o.kv_zusatz = float(legal.value("kv_zusatzbeitrag_durchschnitt", o.horizon_start))
    s.origin["options.kv_zusatz"] = "abgeleitet"
    sa = pd.annahme("sozialabgaben_anteil_gehalt")
    if sa is not None:
        o.sozialabgaben_anteil = float(sa.value)
        s.origin["options.sozialabgaben_anteil"] = sa.herkunft
        s.xml_paths["options.sozialabgaben_anteil"] = f"Planung/Annahmen/Annahme[@id='{sa.id}']"
    else:
        o.sozialabgaben_anteil = float(legal.value("alg_sv_pauschale"))
        s.origin["options.sozialabgaben_anteil"] = "annahme"
    s.origin["options.tarif_index"] = "annahme"

    # Gestaltungen (one Massnahme element each; elements of the old format are removed when loading)
    pay_years = sorted({p.pay_year for p in s.persons})
    default_year = pay_years[-1] if pay_years else o.horizon_start + 1
    o.lst_freibetrag_year = default_year
    o.lst_antrag_datum = pd.stand
    for m_ in pd.massnahmen:
        typ = ART_TO_TYP.get(m_.art)
        if typ is None:
            continue
        g = Gestaltung(typ=typ, jahr=m_.jahr, gegenwert=GESTALTUNG_TYPEN[typ][2], monat=1 if typ == "kauf" else 12)
        if typ == "sonstige":
            g.name = m_.bezeichnung
            g.person = m_.person or (s.persons[0].id if s.persons else "")
        if m_.afa_art:
            g.afa_art = m_.afa_art
        s.measures.items[m_.id] = g
        base = f"measures.items.{m_.id}"
        s.xml_paths[f"{base}.jahr"] = f"Planung/Massnahmen/Massnahme[@id='{m_.id}']"
        for pa in m_.params:
            if not hasattr(g, pa.name) or pa.name in ("typ", "jahr", "name", "person", "afa_art"):
                continue
            cur = getattr(g, pa.name)
            setattr(g, pa.name, int(pa.value) if isinstance(cur, int) else float(pa.value))
            s.origin[f"{base}.{pa.name}"] = pa.herkunft
            s.xml_paths[f"{base}.{pa.name}"] = f"Planung/Massnahmen/Massnahme[@id='{m_.id}']/Parameter[@name='{pa.name}']"

    for y in range(o.horizon_start, o.horizon_end + 1):
        s.veranlagung[y] = "auto" if s.joint else "einzel"
        s.origin[f"veranlagung.{y}"] = "planung"
    for vw in pd.veranlagungswahl:
        s.veranlagung[vw.jahr] = vw.art
        s.sa_haelftig = s.sa_haelftig or vw.sonderausgaben_haelftig
        s.origin[f"veranlagung.{vw.jahr}"] = "planung"
        s.xml_paths[f"veranlagung.{vw.jahr}"] = f"Planung/Veranlagungswahl[@jahr={vw.jahr}]"

    for path, h in list(s.origin.items()):
        if h not in allowed_origins(path):
            s.origin[path] = default_origin(path)
    _apply_ui(s, pd)
    return s


def set_salary_mode(s: Settings, i: int, mode: str, years) -> None:
    """Switch the meaning of the salary inputs and convert the values so the result is unchanged."""
    ps = s.persons[i]
    if ps.salary_mode == mode:
        return
    for y in years:
        em = ps.employed_months(y)
        if em <= 0:
            continue
        full = ps.annual_equiv(y)
        s.set(f"persons.{i}.salary.{y}", round(full * em / 12 if mode == "real" else full, 2))
    s.set(f"persons.{i}.salary_mode", mode)


def apply_exit(s: Settings, i: int, alt_id: str) -> None:
    """Exit choice: 'geplant' (planned end) or the id of an alternative from the XML."""
    ps = s.persons[i]
    if alt_id == "geplant":
        s.set(f"persons.{i}.end_date", ps.geplantes_ende)
        s.set(f"persons.{i}.freistellung", False)
        return
    for aid, art, ende, fab in ps.alternativen:
        if aid == alt_id:
            s.set(f"persons.{i}.end_date", ende)
            if art == "Freistellung" and fab:
                s.set(f"persons.{i}.freistellung", True)
                s.set(f"persons.{i}.freistellung_ab", fab)
            else:
                s.set(f"persons.{i}.freistellung", False)


def _label(i: int) -> str:
    """Display name by position: the first person is the taxpayer, the second the spouse."""
    return "Steuerpflichtige(r)" if i == 0 else "Ehepartner"


# -- ui annahmen ---------------------------------------------------------------

PERSON_UI = ["austritt", "alg_aktiv", "kv_aktiv", "salary_mode", "vorbeschaeftigung_monate", "vertragsschluss",
             "pay_idx", "sperrzeit_wochen",
             "arbeitsuchend_datum", "meldung", "newjob",
             "newjob_start", "newjob_salary", "kv_sonstige_einnahmen", "werbungskosten"]
OPTION_NATIVE = {"church", "bundesland"}
# Inputs removed from the tool (simplified exit); old entries are dropped from the XML when saving.
REMOVED_PERSON_UI = ["freistellung", "freistellung_ab", "sperrzeit_ab_freistellung", "urlaub_tage", "bonus", "bonus_year",
                     "split_share", "split_idx", "bav_amount", "bav_dienstjahre", "bav_vorjahre",
                     "kfrist_aus_tabelle", "alg_mode"]
REMOVED_OPTIONS = {"ein_jahres_ereignis", "kv_mode", "gebunden_gewicht", "include_salary"}  # gebunden_gewicht → Gegenwert je Gestaltung


def _enc(v) -> str:
    if isinstance(v, dict):
        return ";".join(f"{k}:{x}" for k, x in sorted(v.items()))
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _dec(v: str, like):
    if isinstance(like, dict):
        out = {}
        for part in filter(None, v.split(";")):
            k, x = part.split(":")
            out[int(k)] = float(x)
        return out
    if isinstance(like, bool):
        return v.strip().lower() == "true"
    if isinstance(like, date):
        return date.fromisoformat(v.strip())
    if isinstance(like, int):
        return int(float(v))
    if isinstance(like, float):
        return float(v)
    return v


def _ui_items(s: Settings):
    for i, ps in enumerate(s.persons):
        for f_ in PERSON_UI:
            yield f"ui_{ps.id}__{f_}", f"persons.{i}.{f_}"
    for f_ in fields(Options):
        if f_.name not in OPTION_NATIVE | REMOVED_OPTIONS:
            yield f"ui_o__{f_.name}", f"options.{f_.name}"
    for k in SECTIONS:
        yield f"ui_s__{k}", f"sections.{k}"
    yield "ui_v__sa_haelftig", "sa_haelftig"


def effective(s: Settings, legal) -> Settings:
    """Copy of the settings in which disabled areas are replaced by neutral values.

    (not married: the second person is left out; single assessment)
    haushalt     no children, no childcare costs, no church tax, no tariff indexation, factor 1,
                 social-contribution share = alg_sv_pauschale, no RV rate assumption
    kv           no KV/PV contributions (handled in the scenario run)
    gestaltungen no Gestaltungen
    optionen     horizon = year of the earliest exit + 2, salary in the Saldo, no wage-tax allowance,
                 one-year rule on (event: end of contract)
    """
    t = s.copy()
    # Simplified exit (no Freistellung, no paid-out leave, no bonus): these inputs are no longer offered
    # and are ignored even if an older file still contains them.
    for ps in t.persons:
        ps.freistellung = False
        ps.urlaub_tage = 0
        ps.bonus = 0.0
        if not ps.austritt:  # employment continues: no severance, no unemployment, no new job
            ps.severance = 0.0
            ps.fenster_aktiv = False
            ps.newjob = False
            ps.sperrzeit_wochen = 0
        if not ps.alg_aktiv:  # no claim: a Sperrzeit has no effect
            ps.sperrzeit_wochen = 0
    t.options.ein_jahres_ereignis = "vertragsende"
    if not t.married:  # without a spouse only the taxpayer is calculated (a second person stays in the file)
        t.persons = t.persons[:1]
        t.joint = False
    d_opt = Options()
    if not t.active("haushalt"):
        t.children = []
        t.childcare = {}
        o = t.options
        o.church = False
        o.tarif_index = 0.0
        o.vorsorge_factor = 1.0
        o.guenstiger_mode = d_opt.guenstiger_mode
        o.sozialabgaben_anteil = float(legal.value("alg_sv_pauschale"))
        o.rv_satz_annahme = 0.0
        o.bescheid_monat = d_opt.bescheid_monat
        t.veranlagung = {}
        t.sa_haelftig = False
    if not t.active("gestaltungen"):
        t.measures = Measures()
    if not t.active("optionen"):
        o = t.options
        o.horizon_auto = True
        o.gegenwert_arbeitszeit = d_opt.gegenwert_arbeitszeit
        o.lst_freibetrag = 0.0
        o.ein_jahres_regel = True
        o.ein_jahres_ereignis = "vertragsende"
    return t


def _legacy_measures(s: Settings, pd: PersonalData) -> None:
    """Older saves kept the measures as tool settings (ui_m__*): converted into entries."""
    def val(name, default=None):
        a = pd.annahme(f"ui_m__{name}")
        return a.value.strip() if a is not None and a.value.strip() else default

    def num(name, default=0.0):
        v = val(name)
        try:
            return float(v) if v is not None else default
        except ValueError:
            return default

    gw = {k: num(f"gegenwert_{k}", GESTALTUNG_TYPEN[k][2]) for k in ("basisrente", "erhaltung", "spende", "kauf")}
    br = val("basisrente", "")
    if br and ":" not in br and num("basisrente") and val("basisrente_year"):  # older format: one amount + year
        br = f"{int(num('basisrente_year'))}:{num('basisrente')}"
    for part in filter(None, br.split(";")):
        y, v = part.split(":")
        if float(v):
            add_gestaltung(s, "basisrente", int(y), betrag=float(v), monat=int(num("basisrente_monat", 12)),
                           gegenwert=gw["basisrente"])
    if num("erhaltung"):
        add_gestaltung(s, "erhaltung", int(num("erhaltung_year", 2027)), betrag=num("erhaltung"),
                       monat=int(num("erhaltung_monat", 12)), gegenwert=gw["erhaltung"])
    if num("spende"):
        add_gestaltung(s, "spende", int(num("spende_year", 2027)), betrag=num("spende"), gegenwert=gw["spende"])
    if val("kauf_aktiv") == "true":
        kw = {f_: num(f_, getattr(Gestaltung(), f_)) for f_ in KAUF_FIELDS if f_ != "afa_art"}
        kw["zinsbindung_jahre"] = int(kw["zinsbindung_jahre"])
        add_gestaltung(s, "kauf", int(num("kauf_year", 2027)), monat=int(num("kauf_monat", 1)), gegenwert=gw["kauf"],
                       afa_art=val("afa_art", "standard"), **kw)
    for name in ("lst_freibetrag", "lst_freibetrag_year", "lst_antrag_datum"):
        v = val(name)
        if v is not None and pd.annahme(f"ui_o__{name}") is None:
            try:
                s.set(f"options.{name}", _dec(v, s.get(f"options.{name}")))
            except (ValueError, TypeError):
                pass


def _apply_ui(s: Settings, pd: PersonalData) -> None:
    if not s.measures.items:
        _legacy_measures(s, pd)
    for aid, path in _ui_items(s):
        a = pd.annahme(aid)
        if a is None:
            continue
        try:
            s.set(path, _dec(a.value, s.get(path)), user=False)
            # Older saves wrote every tool setting with herkunft "planung"; for values that cannot be influenced
            # the origin of the XML element (or the default) stays authoritative.
            if a.herkunft in allowed_origins(path):
                s.origin[path] = a.herkunft
                s.xml_paths[path] = f"Planung/Annahmen/Annahme[@id='{aid}']"
        except (ValueError, TypeError):
            pass
    # Former switches "computed or own value" are now expressed by the origin "abgeleitet".
    switches = [(f"ui_{ps.id}__kfrist_aus_tabelle", "true", f"persons.{i}.kfrist_monate") for i, ps in enumerate(s.persons)]
    switches += [(f"ui_{ps.id}__alg_mode", "berechnung", f"persons.{i}.alg_monat") for i, ps in enumerate(s.persons)]
    switches += [("ui_o__kv_mode", "berechnet", f"persons.{i}.kv_beitrag_schaetzung") for i in range(len(s.persons))]
    for aid, on, path in switches:
        a = pd.annahme(aid)
        if a is not None and a.value.strip().lower() == on:
            s.origin[path] = "abgeleitet"
    # Former switch "salary in the Saldo" (off = the salary did not count, i.e. the working time is worth it).
    a = pd.annahme("ui_o__include_salary")
    if a is not None and pd.annahme("ui_o__gegenwert_arbeitszeit") is None and a.value.strip().lower() == "false":
        s.options.gegenwert_arbeitszeit = 1.0
        s.origin["options.gegenwert_arbeitszeit"] = "angabe"


def _set_val(val: Val, new, herkunft: str) -> None:
    val.value = new
    val.herkunft = herkunft


def _new_person(ps: PersonSettings) -> Person:
    """Person element for a spouse added in the tool (values are written from the settings afterwards)."""
    v = lambda x: Val(x, "angabe")  # noqa: E731
    return Person(id=ps.id, rolle=ps.rolle or "Partner", geburtsdatum=ps.birth, steuerklasse=ps.steuerklasse,
                  bz_jahre=v(0.0), kfrist_monate=v(0.0), gehaelter=[], geplantes_ende=Val(ps.end_date, "planung"),
                  alternativen=[], rv_pflichtig=v(True), abfindung=Val(0.0, "planung"), fuenftel_ok=v(True),
                  kv_status=v("pflichtversichert"), kv_beitrag_freiwillig=v(0.0), alg_monat=v(0.0), alg_satz=v(0.6),
                  sperrzeit_erwartet=v(False))


def set_familienstand(s: Settings, value: str) -> None:
    """Change the marital status. Married: a spouse is added if the file has none, joint assessment is the
    default again; otherwise single assessment (a second person stays in the file but is not calculated)."""
    if value == s.familienstand:
        return
    s.familienstand = value
    if s.married:
        s.joint = True
        s.veranlagung = {y: "auto" for y in s.veranlagung}
        if len(s.persons) < 2:
            p0 = s.persons[0]
            ps = PersonSettings(id="P_Ehepartner", label=_label(1), rolle="Partner", birth=p0.birth,
                                end_date=p0.end_date, geplantes_ende=p0.end_date, pay_idx=p0.pay_idx,
                                fenster_ab_idx=p0.exit_idx, meldung=p0.end_date + timedelta(days=1),
                                arbeitsuchend_datum=p0.end_date, vertragsschluss=p0.vertragsschluss,
                                kv_status="pflichtversichert", sperrzeit_wochen=0, werbungskosten=p0.werbungskosten,
                                salary={p0.end_date.year: 0.0})
            s.persons.append(ps)
            b = "persons.1"
            s.origin[f"{b}.arbeitsuchend_datum"] = "abgeleitet"
            s.origin[f"{b}.sperrzeit_wochen"] = "angabe"
    else:
        s.joint = False


def _children_out(children: list, old: list) -> list:
    """Children as in the settings; existing ids are kept by position, new children get the next free id."""
    used = {k.id for k in old}
    out = []
    for n, (gj, kg) in enumerate(children):
        if n < len(old):
            cid = old[n].id
        else:
            m = len(out) + 1
            while f"K{m}" in used:
                m += 1
            cid = f"K{m}"
            used.add(cid)
        out.append(Child(cid, int(gj), bool(kg)))
    return out


def _massnahme_out(s: Settings, gid: str, g: Gestaltung) -> Massnahme:
    base = f"measures.items.{gid}"
    params = [MParam(name, getattr(g, name), PARAM_UNITS[name], s.origin_of(f"{base}.{name}")) for name in g.params()]
    return Massnahme(gid, GESTALTUNG_TYPEN[g.typ][1], g.jahr, g.name if g.typ == "sonstige" else GESTALTUNG_TYPEN[g.typ][0],
                     params, person=g.person if g.typ == "sonstige" else None,
                     afa_art=g.afa_art if g.typ == "kauf" else None)


def to_personal(s: Settings, pd: PersonalData) -> PersonalData:
    """Write the settings back into a copy of the personal data model."""
    d = pd.clone()
    o = s.origin_of
    _set_val(d.household.kirchensteuer, s.options.church, o("options.church"))
    _set_val(d.household.bundesland, s.options.bundesland, o("options.bundesland"))
    d.household.kinder = _children_out(s.children, d.household.kinder)
    d.household.familienstand = s.familienstand
    d.household.veranlagung = "Zusammenveranlagung" if s.married and s.joint else "Einzelveranlagung"
    if d.vermietung is not None:
        if d.vermietung.angeschafft3j is None:
            d.vermietung.angeschafft3j = Val(s.objekte_angeschafft_3j, o("objekte_angeschafft_3j"))
        _set_val(d.vermietung.angeschafft3j, s.objekte_angeschafft_3j, o("objekte_angeschafft_3j"))
    for b in d.household.betreuungskosten:
        y = b.jahr or d.stand.year
        if y in s.childcare:
            _set_val(b, s.childcare[y], o(f"childcare.{y}"))
    for i, ps in enumerate(s.persons):
        if not any(p_.id == ps.id for p_ in d.persons):
            d.persons.append(_new_person(ps))
        p = d.person(ps.id)
        b = f"persons.{i}"
        p.geburtsdatum = ps.birth
        p.steuerklasse = ps.steuerklasse
        _set_val(p.bz_jahre, ps.bz_jahre, o(f"{b}.bz_jahre"))
        _set_val(p.kfrist_monate, ps.kfrist_monate, o(f"{b}.kfrist_monate"))
        for y, v in sorted(ps.salary.items()):
            g = p.gehalt(y)
            if g is None:
                p.gehaelter.append(Val(v, o(f"{b}.salary.{y}"), None, y))
            else:
                _set_val(g, v, o(f"{b}.salary.{y}"))
        _set_val(p.geplantes_ende, ps.end_date, o(f"{b}.end_date"))
        _set_val(p.abfindung, ps.severance, o(f"{b}.severance"))
        _set_val(p.fuenftel_ok, ps.fuenftel_ok, o(f"{b}.fuenftel_ok"))
        _set_val(p.rv_pflichtig, ps.rv_pflichtig, o(f"{b}.rv_pflichtig"))
        _set_val(p.kv_status, ps.kv_status, o(f"{b}.kv_status"))
        _set_val(p.kv_beitrag_freiwillig, ps.kv_beitrag_schaetzung, o(f"{b}.kv_beitrag_schaetzung"))
        _set_val(p.alg_monat, ps.alg_monat, o(f"{b}.alg_monat"))
        _set_val(p.sperrzeit_erwartet, ps.sperrzeit_wochen > 0, o(f"{b}.sperrzeit_wochen"))
        if ps.fenster_aktiv:
            fr = (ps.fenster_ab_idx // 12, ps.fenster_ab_idx % 12 + 1)
            p.auszahlungsfenster = Auszahlungsfenster(fr, ps.fenster_monate, o(f"{b}.fenster_ab_idx"))
        else:
            p.auszahlungsfenster = None
        _sync_person_vals(d.vermietung.einkuenfte, ps.id, ps.rent, lambda y, b=b: o(f"{b}.rent.{y}"))
        _sync_person_vals(d.kapital, ps.id, ps.capital, lambda y, b=b: o(f"{b}.capital.{y}"))

    if s.married and len(s.persons) >= 2:
        d.veranlagungswahl = [Veranlagungswahl(y, art, s.sa_haelftig) for y, art in sorted(s.veranlagung.items())]

    removed = {f"ui_{ps.id}__{f_}" for ps in s.persons for f_ in REMOVED_PERSON_UI} | {
        f"ui_o__{f_}" for f_ in REMOVED_OPTIONS} | {"ui_s__partner"}  # spouse now follows the marital status
    d.annahmen = [a for a in d.annahmen if a.id not in removed and not a.id.startswith("ui_m__")]
    d.massnahmen = [_massnahme_out(s, gid, g) for gid, g in gestaltungen(s)]
    for aid, path in _ui_items(s):
        d.set_annahme(aid, _enc(s.get(path)), "keine", o(path), hinweis="Einstellung des Abfindungsoptimierers")
        d.annahme(aid).herkunft = o(path)
    return d


def _sync_person_vals(lst: list[PersonVal], pid: str, values: dict, origin) -> None:
    for y, v in values.items():
        e = next((e for e in lst if e.person == pid and (e.val.jahr == y)), None)
        if e is None:
            lst.append(PersonVal(pid, Val(v, origin(y), None, y)))
        else:
            _set_val(e.val, v, origin(y))
