"""Save/load projects (JSON) and export results (Excel)."""
from __future__ import annotations

import io
import json

import pandas as pd

from .engine import Alternative, CostItem, cashflow_table, summary, yearly_totals

ITEM_COLUMNS = ["name", "kind", "amount", "category", "year", "start", "end", "life",
                "replace", "escalation"]


def project_to_json(alts: list[Alternative], n_years: int, d: float, title: str = "") -> str:
    return json.dumps({
        "title": title, "analysis_years": n_years, "discount_rate": d,
        "alternatives": [{"name": a.name, "description": a.description,
                          "items": [i.to_dict() for i in a.items]} for a in alts],
    }, indent=2)


def project_from_json(text: str) -> tuple[list[Alternative], int, float, str]:
    data = json.loads(text)
    alts = []
    for a in data["alternatives"]:
        alts.append(Alternative(a["name"], [CostItem(**i) for i in a["items"]],
                                a.get("description", "")))
    return alts, int(data["analysis_years"]), float(data["discount_rate"]), data.get("title", "")


def items_to_frame(alt: Alternative) -> pd.DataFrame:
    rows = []
    for i in alt.items:
        r = {c: getattr(i, c) for c in ITEM_COLUMNS}
        r["escalation_pct"] = (i.escalation or 0) * 100
        r.pop("escalation")
        r["has_series"] = bool(i.series)
        rows.append(r)
    cols = [c for c in ITEM_COLUMNS if c != "escalation"] + ["escalation_pct", "has_series"]
    return pd.DataFrame(rows, columns=cols)


def frame_to_items(df: pd.DataFrame, original: Alternative | None = None) -> list[CostItem]:
    """Rebuild items from the editable table. Series data (not editable in the grid) is carried
    over from the original item with the same name."""
    series_by_name = {i.name: i.series for i in (original.items if original else []) if i.series}
    items = []
    for _, r in df.iterrows():
        if not isinstance(r.get("name"), str) or not r["name"].strip():
            continue

        def num(key, default=None):
            v = r.get(key)
            try:
                if v is None or pd.isna(v):
                    return default
            except (TypeError, ValueError):
                pass
            return v

        kind = num("kind", "once")
        series = series_by_name.get(r["name"]) if kind == "series" else None
        items.append(CostItem(
            name=r["name"].strip(), kind=kind, amount=float(num("amount", 0.0)),
            category=num("category", "Other") or "Other", year=int(num("year", 0)),
            start=int(num("start", 1)),
            end=None if num("end") is None else int(num("end")),
            life=None if num("life") is None else float(num("life")),
            replace=bool(num("replace", True)),
            escalation=float(num("escalation_pct", 0.0)) / 100.0, series=series))
    return items


def results_workbook(alts: list[Alternative], n_years: int, d: float,
                     extra_sheets: dict[str, pd.DataFrame] | None = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary(alts, n_years, d).to_excel(xw, sheet_name="Summary", index=False)
        for a in alts:
            yt = yearly_totals(a, n_years, d).reset_index()
            yt.to_excel(xw, sheet_name=_safe(a.name, "Yearly "), index=False)
        pd.concat([cashflow_table(a, n_years, d) for a in alts]).to_excel(
            xw, sheet_name="All cash flows", index=False)
        for name, df in (extra_sheets or {}).items():
            df.to_excel(xw, sheet_name=_safe(name), index=False)
    return buf.getvalue()


def _safe(name: str, prefix: str = "") -> str:
    bad = '[]:*?/\\'
    s = prefix + "".join("_" if ch in bad else ch for ch in name)
    return s[:31]
