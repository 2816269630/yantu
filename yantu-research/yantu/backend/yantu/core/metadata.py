"""core.metadata business operations."""

from __future__ import annotations
from ..core.models import EntityData


def get_meta(db, kind, ident):
    row = db.get(EntityData, f"{kind}:{ident}")
    return dict(row.data) if row else {}


def put_meta(db, kind, ident, values):
    key = f"{kind}:{ident}"
    row = db.get(EntityData, key)
    if row is None:
        row = EntityData(key=key, data={})
        db.add(row)
    row.data = {**row.data, **values}
    return row.data
