# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Write the personal data model as XML; the result is validated before it is written."""

from __future__ import annotations

import shutil
from pathlib import Path

from lxml import etree

from .personal_model import PersonalData, to_xml
from .xml_loader import PERSONAL_XSD, ValidationError, validate_tree


def to_bytes(data: PersonalData) -> bytes:
    tree = to_xml(data)
    # Re-parse to get line numbers for possible validation errors.
    raw = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    errors = validate_tree(etree.ElementTree(etree.fromstring(raw)), PERSONAL_XSD)
    if errors:
        raise ValidationError("(Export)", errors)
    return raw


def save_personal(data: PersonalData, path: str | Path, backup: bool = True) -> Path:
    """Validate and write. With ``backup`` an existing file is copied to ``<name>.bak`` first."""
    path = Path(path)
    raw = to_bytes(data)
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return path
