# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Load XML files and validate them against their XSD with readable error messages."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
PERSONAL_XSD = SCHEMA_DIR / "personal_data.xsd"
LEGAL_XSD = SCHEMA_DIR / "regulatory_input.xsd"

NS_PERSONAL = "urn:abfindung:persoenlich:v1"
NS_LEGAL = "urn:abfindung:recht:v1"


class ValidationError(Exception):
    """Raised when a file is not well-formed or violates its schema."""

    def __init__(self, path: str | Path, errors: list[str]):
        self.path = str(path)
        self.errors = errors
        super().__init__(f"{self.path}: " + "; ".join(errors[:5]))

    def pretty(self) -> str:
        lines = [f"Die Datei „{Path(self.path).name}“ ist ungültig:"]
        lines += [f"  • {e}" for e in self.errors[:30]]
        if len(self.errors) > 30:
            lines.append(f"  … und {len(self.errors) - 30} weitere Fehler")
        return "\n".join(lines)


@lru_cache(maxsize=4)
def _schema(xsd_path: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(xsd_path))


def _clean(msg: str) -> str:
    msg = re.sub(r"\{[^}]*\}", "", msg)  # drop namespace URIs
    msg = msg.replace("Element '", "Element „").replace("': ", "“: ")
    return msg


def validate_tree(tree: etree._ElementTree, xsd: Path) -> list[str]:
    schema = _schema(str(xsd))
    if schema.validate(tree):
        return []
    return [f"Zeile {e.line}: {_clean(e.message)}" for e in schema.error_log]


REMOVED_ELEMENTS = {  # element (local path) -> description; dropped when reading an older file
    "Planung/Abfindungsvarianten": "Abfindungsvarianten",
    "Planung/ALGSzenarien": "ALG-Szenarien",
    "Referenzergebnisse": "Referenzergebnisse",
}


def _migrate_personal(tree: etree._ElementTree) -> list[str]:
    """Older files may use herkunft="bescheid" (removed from the schema): it is read as "angabe".
    Variants, scenarios and reference results are no longer supported: they are dropped."""
    notes = []
    n = 0
    for el in tree.getroot().iter():
        if el.get("herkunft") == "bescheid":
            el.set("herkunft", "angabe")
            n += 1
    if n:
        notes.append(f"{n} Wert(e) mit Herkunft „bescheid“ als „angabe“ übernommen (wird so gespeichert).")
    root = tree.getroot()
    ns = {"p": root.nsmap.get(None) or "urn:abfindung:persoenlich:v1"}
    for path, label in REMOVED_ELEMENTS.items():
        for el in root.findall("/".join(f"p:{x}" for x in path.split("/")), ns):
            el.getparent().remove(el)
            notes.append(f"{label} werden nicht mehr unterstützt und beim Speichern entfernt.")
    # Measures in the old format (candidates / examples without "gegenwert") are not Gestaltungen of the tool.
    old = [m for m in root.findall("p:Planung/p:Massnahmen/p:Massnahme", ns)
           if m.find("p:Parameter[@name='gegenwert']", ns) is None]
    for m in old:
        m.getparent().remove(m)
    if old:
        notes.append(f"{len(old)} Maßnahme(n) im alten Format (Kandidaten, Rechenbeispiele) entfernt; Gestaltungen "
                     "werden im Tab „Gestaltungen“ angelegt.")
    return notes


def parse_and_validate(path: str | Path, xsd: Path, migrate=None, notes: list | None = None) -> etree._ElementTree:
    path = Path(path)
    if not path.exists():
        raise ValidationError(path, ["Datei nicht gefunden."])
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, no_network=True)
    try:
        tree = etree.parse(str(path), parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(path, [f"XML-Syntaxfehler: {_clean(str(exc))}"]) from exc
    if migrate:
        found = migrate(tree)
        if notes is not None:
            notes.extend(found)
    errors = validate_tree(tree, xsd)
    if errors:
        raise ValidationError(path, errors)
    return tree


def load_legal(path: str | Path):
    from .legal_model import parse_legal

    tree = parse_and_validate(path, LEGAL_XSD)
    data = parse_legal(tree.getroot())
    data.path = str(path)
    return data


def load_personal(path: str | Path):
    from .personal_model import parse_personal

    notes: list[str] = []
    tree = parse_and_validate(path, PERSONAL_XSD, migrate=_migrate_personal, notes=notes)
    data = parse_personal(tree.getroot())
    data.path = str(path)
    data.migration_notes = notes
    return data
