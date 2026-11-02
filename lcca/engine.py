"""
Core Life Cycle Cost Analysis (LCCA) engine.

Conventions (stated once, used everywhere):
* Year 0 = today (installation / purchase). Cash flows occur at the END of each year t = 1..N.
* Every amount is entered at BASE-YEAR (year-0) prices. The nominal cash flow in year t is
      CF_t = amount_t * (1 + e)^t
  where e is that item's own nominal escalation rate.
* Discounting uses a NOMINAL discount rate d:  PV = CF_t / (1 + d)^t.
  This is mathematically identical to discounting base-year amounts at the real rate
  r = (1+d)/(1+i) - 1 with a differential escalation (1+e)/(1+i) - 1 (Fisher relation).
* Sign: positive = cost (money out), negative = benefit / income / subsidy / residual value.
* LCC (life cycle cost) = sum of present values of all cash flows over the analysis period.
  The alternative with the LOWEST LCC is preferred.

References for the method: NIST Handbook 135 (Fuller & Petersen, 1996), ASTM E917,
ISO 15686-5.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Iterable

import pandas as pd

KINDS = ("once", "annual", "capital", "series")


@dataclass
class CostItem:
    """One cost (or benefit) stream belonging to an alternative.

    kind = "once"    -> single amount in `year` (0..N)
    kind = "annual"  -> same base-year amount every year from `start` to `end` (inclusive)
    kind = "capital" -> asset bought in `year` with service `life`; if `replace` is True it is
                        re-bought every `life` years while the purchase year is < N. Any life
                        left over at the end of the analysis period is credited back as a
                        straight-line residual value in year N.
    kind = "series"  -> explicit list of base-year amounts for years 1..N (`series[0]` is year 1)
    """

    name: str
    kind: str = "once"
    amount: float = 0.0
    category: str = "Other"
    year: int = 0
    start: int = 1
    end: int | None = None
    life: float | None = None
    replace: bool = True
    escalation: float = 0.0
    series: list[float] | None = None

    def validate(self, n_years: int) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}, got {self.kind!r}")
        if self.escalation <= -1:
            raise ValueError(f"{self.name}: escalation must be greater than -100%")
        if self.kind in ("once", "capital") and not (0 <= int(self.year) <= n_years):
            raise ValueError(f"{self.name}: year must be between 0 and {n_years}")
        if self.kind == "capital":
            if self.life is None or self.life <= 0:
                raise ValueError(f"{self.name}: a capital item needs a positive service life")
        if self.kind == "annual":
            end = n_years if self.end is None else int(self.end)
            if int(self.start) < 1 or end > n_years or int(self.start) > end:
                raise ValueError(f"{self.name}: annual item needs 1 <= start <= end <= {n_years}")
        if self.kind == "series":
            if not self.series:
                raise ValueError(f"{self.name}: series item needs a list of yearly amounts")
            if len(self.series) > n_years:
                raise ValueError(f"{self.name}: series longer than the analysis period")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Alternative:
    name: str
    items: list[CostItem] = field(default_factory=list)
    description: str = ""


# ----------------------------------------------------------------------------------------
# Standard engineering-economics factors (used by the tool and quoted in the validation)
# ----------------------------------------------------------------------------------------
def spw(d: float, t: float) -> float:
    """Single present worth factor (P/F, d, t) = 1/(1+d)^t."""
    return 1.0 / (1.0 + d) ** t


def upw(d: float, n: int) -> float:
    """Uniform present worth factor (P/A, d, n)."""
    if abs(d) < 1e-12:
        return float(n)
    return (1 - (1 + d) ** -n) / d


def upw_escalating(d: float, e: float, n: int) -> float:
    """Present worth of 1 (base-year price) paid every year 1..n escalating at e:
    sum_{t=1..n} ((1+e)/(1+d))^t   (NIST 'UPV*' factor)."""
    x = (1 + e) / (1 + d)
    if abs(x - 1) < 1e-12:
        return float(n)
    return x * (1 - x ** n) / (1 - x)


def crf(d: float, n: int) -> float:
    """Capital recovery factor (A/P, d, n), converts a present value to an equivalent annual value."""
    if abs(d) < 1e-12:
        return 1.0 / n
    return d * (1 + d) ** n / ((1 + d) ** n - 1)


def real_rate(nominal: float, inflation: float) -> float:
    """Fisher relation: real = (1+nominal)/(1+inflation) - 1."""
    return (1 + nominal) / (1 + inflation) - 1


# ----------------------------------------------------------------------------------------
# Cash-flow generation
# ----------------------------------------------------------------------------------------
def item_cashflows(item: CostItem, n_years: int) -> list[dict]:
    """Expand one item into rows {year, item, category, base, nominal}."""
    item.validate(n_years)
    e = float(item.escalation)
    rows: list[dict] = []

    def add(year: int, base: float, category: str | None = None, label: str | None = None):
        rows.append(
            {
                "year": int(year),
                "item": label or item.name,
                "category": category or item.category,
                "base": float(base),
                "nominal": float(base) * (1 + e) ** int(year),
            }
        )

    if item.kind == "once":
        add(item.year, item.amount)

    elif item.kind == "annual":
        end = n_years if item.end is None else int(item.end)
        for t in range(int(item.start), end + 1):
            add(t, item.amount)

    elif item.kind == "series":
        for idx, amt in enumerate(item.series):
            if amt:
                add(idx + 1, amt)

    elif item.kind == "capital":
        life = float(item.life)
        installs = [int(item.year)]
        if item.replace:
            nxt = item.year + life
            # a replacement falling exactly at (or after) year N is not bought
            while nxt < n_years - 1e-9:
                installs.append(nxt)
                nxt += life
        for k, y in enumerate(installs):
            if abs(y - round(y)) > 1e-9:
                raise ValueError(f"{item.name}: life must give whole-year replacement dates")
            add(int(round(y)), item.amount,
                label=item.name if k == 0 else f"{item.name} (replacement {k})")
        last = installs[-1]
        remaining = last + life - n_years
        if remaining > 1e-9:
            fraction = remaining / life
            add(n_years, -item.amount * fraction, category="Residual value",
                label=f"{item.name} (residual value, {remaining:g}/{life:g} life left)")
    return rows


def cashflow_table(alt: Alternative, n_years: int, d: float) -> pd.DataFrame:
    rows = []
    for it in alt.items:
        rows.extend(item_cashflows(it, n_years))
    df = pd.DataFrame(rows, columns=["year", "item", "category", "base", "nominal"])
    if df.empty:
        df = pd.DataFrame({"year": [0], "item": ["(none)"], "category": ["Other"],
                           "base": [0.0], "nominal": [0.0]})
    df["discount_factor"] = df["year"].apply(lambda t: spw(d, t))
    df["present_value"] = df["nominal"] * df["discount_factor"]
    df.insert(0, "alternative", alt.name)
    return df.sort_values(["year", "item"]).reset_index(drop=True)


def lcc(alt: Alternative, n_years: int, d: float) -> float:
    return float(cashflow_table(alt, n_years, d)["present_value"].sum())


def yearly_totals(alt: Alternative, n_years: int, d: float) -> pd.DataFrame:
    df = cashflow_table(alt, n_years, d)
    g = df.groupby("year")[["nominal", "present_value"]].sum()
    g = g.reindex(range(0, n_years + 1), fill_value=0.0)
    g["cumulative_pv"] = g["present_value"].cumsum()
    g.index.name = "year"
    return g


# ----------------------------------------------------------------------------------------
# Comparison metrics
# ----------------------------------------------------------------------------------------
def summary(alts: Iterable[Alternative], n_years: int, d: float) -> pd.DataFrame:
    out = []
    for a in alts:
        df = cashflow_table(a, n_years, d)
        by_cat = df.groupby("category")["present_value"].sum().to_dict()
        total = float(df["present_value"].sum())
        initial = float(df.loc[df["year"] == 0, "nominal"].sum())
        out.append({"alternative": a.name, "initial_cost": initial, "lcc": total,
                    "euac": total * crf(d, n_years), **{f"pv: {k}": v for k, v in by_cat.items()}})
    s = pd.DataFrame(out).fillna(0.0)
    s["rank"] = s["lcc"].rank(method="min").astype(int)
    return s


def net_savings(base: Alternative, alt: Alternative, n_years: int, d: float) -> float:
    """NS = LCC(base) - LCC(alt). Positive means `alt` is cheaper over the life cycle."""
    return lcc(base, n_years, d) - lcc(alt, n_years, d)


def discounted_payback(base: Alternative, alt: Alternative, n_years: int, d: float) -> float | None:
    """First year in which cumulative discounted savings of `alt` over `base` become >= 0,
    with linear interpolation inside the year. None if never within the analysis period."""
    yb = yearly_totals(base, n_years, d)["present_value"]
    ya = yearly_totals(alt, n_years, d)["present_value"]
    diff = (yb - ya).cumsum()
    if diff.iloc[0] >= 0:
        return 0.0
    for t in range(1, n_years + 1):
        if diff.iloc[t] >= 0:
            prev, cur = diff.iloc[t - 1], diff.iloc[t]
            return (t - 1) + (-prev) / (cur - prev) if cur != prev else float(t)
    return None


def simple_payback(base: Alternative, alt: Alternative, n_years: int) -> float | None:
    """Payback on undiscounted nominal cash flows."""
    return discounted_payback(base, alt, n_years, 0.0)


def breakeven_discount_rate(base: Alternative, alt: Alternative, n_years: int,
                            lo: float = -0.05, hi: float = 1.0, steps: int = 2100) -> list[float]:
    """Discount rate(s) at which both alternatives have equal LCC. This is the internal rate of
    return of the incremental cash flows (alt instead of base). Returns every sign change found
    on a fine grid, refined by bisection; empty list if the ranking never flips."""
    # nominal cash flows do not depend on the discount rate, so build them once
    nb = yearly_totals(base, n_years, 0.0)["nominal"].to_numpy()
    na = yearly_totals(alt, n_years, 0.0)["nominal"].to_numpy()
    diff = nb - na
    years = list(range(n_years + 1))

    def f(r):
        return float(sum(diff[t] / (1 + r) ** t for t in years))

    roots = []
    grid = [lo + (hi - lo) * k / steps for k in range(steps + 1)]
    vals = [f(r) for r in grid]
    for k in range(steps):
        a, b = grid[k], grid[k + 1]
        fa, fb = vals[k], vals[k + 1]
        if fa == 0:
            roots.append(a)
        elif fa * fb < 0:
            for _ in range(60):
                m = 0.5 * (a + b)
                fm = f(m)
                if fa * fm <= 0:
                    b, fb = m, fm
                else:
                    a, fa = m, fm
            roots.append(0.5 * (a + b))
    return roots


def lcc_vs_discount_rate(alts: list[Alternative], n_years: int, rates: Iterable[float]) -> pd.DataFrame:
    nominal = {a.name: yearly_totals(a, n_years, 0.0)["nominal"].to_numpy() for a in alts}
    rows = []
    for r in rates:
        row = {"discount_rate": r}
        for name, cf in nominal.items():
            row[name] = float(sum(cf[t] / (1 + r) ** t for t in range(n_years + 1)))
        rows.append(row)
    return pd.DataFrame(rows)


def tornado_items(base: Alternative, alt: Alternative, n_years: int, d: float,
                  swing: float = 0.20) -> pd.DataFrame:
    """Generic one-at-a-time sensitivity: each item's amount in either alternative is moved by
    +/- swing and the change in net savings (base vs alt) is recorded."""
    ref = net_savings(base, alt, n_years, d)
    rows = []
    for which, owner in (("base", base), ("alt", alt)):
        for idx, it in enumerate(owner.items):
            res = []
            for factor in (1 - swing, 1 + swing):
                clone = Alternative(owner.name, [CostItem(**it.to_dict()) for it in owner.items])
                c = clone.items[idx]
                c.amount = it.amount * factor
                if c.series:
                    c.series = [v * factor for v in it.series]
                b2, a2 = (clone, alt) if which == "base" else (base, clone)
                res.append(net_savings(b2, a2, n_years, d))
            rows.append({"parameter": f"{owner.name}: {it.name}", "low": res[0], "high": res[1],
                         "range": abs(res[1] - res[0])})
    out = pd.DataFrame(rows).sort_values("range", ascending=False).reset_index(drop=True)
    out.attrs["reference"] = ref
    return out
