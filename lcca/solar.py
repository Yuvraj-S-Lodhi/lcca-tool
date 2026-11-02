"""
Rooftop solar PV (net-metered) vs grid-only electricity: builds the two LCCA alternatives
from physical inputs and a telescopic (slab) retail tariff.

Default values are the team's benchmark case. Every default is traced to a source in
`DEFAULT_SOURCES` and in the user manual / validation report.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import pandas as pd

from .engine import Alternative, CostItem, net_savings

# ---------------------------------------------------------------------------------------
# Tariff
# ---------------------------------------------------------------------------------------


@dataclass
class SlabTariff:
    """Monthly telescopic slab tariff. `slabs` = [(upper_kWh_or_None, energy_charge_Rs_per_kWh)].
    Electricity duty is applied as a percentage of (energy + wheeling + fixed charges)."""

    name: str = "MSEDCL LT-I(B) Residential, single phase, FY 2026-27"
    slabs: list = field(default_factory=lambda: [(100, 3.96), (300, 10.80), (500, 15.03), (None, 17.53)])
    wheeling: float = 1.60          # Rs/kWh on all units billed
    fixed_monthly: float = 130.0    # Rs per connection per month
    duty: float = 0.16              # electricity duty (fraction)
    fac: float = 0.0                # fuel adjustment charge, Rs/kWh (varies monthly; 0 = excluded)

    def monthly_bill(self, units: float) -> dict:
        units = max(0.0, float(units))
        energy, lower, remaining = 0.0, 0.0, units
        for upper, rate in self.slabs:
            band = remaining if upper is None else min(remaining, upper - lower)
            if band <= 0:
                break
            energy += band * rate
            remaining -= band
            if upper is None:
                break
            lower = upper
        wheeling = units * self.wheeling
        fac = units * self.fac
        subtotal = energy + wheeling + fac + self.fixed_monthly
        duty = subtotal * self.duty
        return {"units": units, "energy": energy, "wheeling": wheeling, "fac": fac,
                "fixed": self.fixed_monthly, "duty": duty, "total": subtotal + duty}


def pm_surya_ghar_cfa(kwp: float) -> float:
    """Central Financial Assistance under PM Surya Ghar: Muft Bijli Yojana (residential):
    Rs 30,000/kW for the first 2 kW, Rs 18,000/kW for the 3rd kW, capped at Rs 78,000."""
    kwp = max(0.0, kwp)
    return 30000 * min(kwp, 2) + 18000 * max(0.0, min(kwp, 3) - 2)


# ---------------------------------------------------------------------------------------
# Case definition
# ---------------------------------------------------------------------------------------


@dataclass
class SolarCase:
    analysis_years: int = 25
    discount_rate: float = 0.07
    general_inflation: float = 0.04          # used for O&M escalation by default

    monthly_consumption_kwh: float = 300.0
    tariff: SlabTariff = field(default_factory=SlabTariff)
    tariff_escalation: float = 0.03

    capacity_kwp: float = 2.0
    capex_per_kwp: float = 60000.0
    subsidy: float | None = None             # None = compute PM Surya Ghar CFA
    specific_yield: float = 1440.0           # kWh per kWp per year (year 1)
    degradation: float = 0.005               # per year
    module_life: float = 25.0

    om_per_year: float = 2000.0
    om_escalation: float | None = None       # None = general_inflation

    inverter_cost: float = 20000.0
    inverter_life: float = 12.0
    inverter_escalation: float = 0.0

    export_rate: float = 0.0                 # Rs/kWh paid for annual surplus (base-year price)

    grid_emission_factor: float = 0.727      # tCO2/MWh (CEA CO2 Baseline Database v20, FY 2023-24)
    carbon_price: float = 0.0                # Rs per tCO2 (0 = not monetised)
    carbon_escalation: float = 0.0

    def resolved_subsidy(self) -> float:
        return pm_surya_ghar_cfa(self.capacity_kwp) if self.subsidy is None else float(self.subsidy)

    def resolved_om_escalation(self) -> float:
        return self.general_inflation if self.om_escalation is None else self.om_escalation


def energy_table(case: SolarCase) -> pd.DataFrame:
    """Year-by-year physical and billing quantities at BASE-YEAR tariff (escalation is applied
    later by the engine)."""
    n = case.analysis_years
    rows = []
    bill_a_month = case.tariff.monthly_bill(case.monthly_consumption_kwh)
    for t in range(1, n + 1):
        gen = case.capacity_kwp * case.specific_yield * (1 - case.degradation) ** (t - 1)
        if t > case.module_life:
            gen = 0.0
        gen_m = gen / 12.0
        net_m = max(0.0, case.monthly_consumption_kwh - gen_m)
        surplus = max(0.0, gen_m - case.monthly_consumption_kwh) * 12
        bill_b_month = case.tariff.monthly_bill(net_m)
        rows.append({
            "year": t,
            "generation_kwh": gen,
            "grid_import_A_kwh": case.monthly_consumption_kwh * 12,
            "grid_import_B_kwh": net_m * 12,
            "surplus_export_kwh": surplus,
            "bill_A_base": bill_a_month["total"] * 12,
            "bill_B_base": bill_b_month["total"] * 12,
            "co2_A_t": case.monthly_consumption_kwh * 12 * case.grid_emission_factor / 1000,
            "co2_B_t": net_m * 12 * case.grid_emission_factor / 1000,
        })
    df = pd.DataFrame(rows)
    df["bill_saving_base"] = df["bill_A_base"] - df["bill_B_base"]
    df["co2_avoided_t"] = df["co2_A_t"] - df["co2_B_t"]
    return df


def build_alternatives(case: SolarCase) -> tuple[Alternative, Alternative, pd.DataFrame]:
    et = energy_table(case)
    n = case.analysis_years

    grid = Alternative("A: Grid only", description="All electricity bought from the DISCOM")
    grid.items.append(CostItem("Electricity bill", kind="series", category="Energy",
                               series=list(et["bill_A_base"]), escalation=case.tariff_escalation))

    pv = Alternative("B: Rooftop PV + grid",
                     description=f"{case.capacity_kwp:g} kWp net-metered PV, balance from grid")
    pv.items += [
        CostItem("PV system (modules, inverter, BoS, installation)", kind="capital",
                 amount=case.capex_per_kwp * case.capacity_kwp, category="Initial",
                 year=0, life=case.module_life, replace=True),
        CostItem("PM Surya Ghar subsidy (CFA)", kind="once", amount=-case.resolved_subsidy(),
                 category="Subsidy", year=0),
        CostItem("Electricity bill (net import)", kind="series", category="Energy",
                 series=list(et["bill_B_base"]), escalation=case.tariff_escalation),
        CostItem("PV O&M (cleaning, inspection)", kind="annual", amount=case.om_per_year,
                 category="O&M", start=1, end=n, escalation=case.resolved_om_escalation()),
        CostItem("Inverter replacement", kind="capital", amount=case.inverter_cost,
                 category="Replacement", year=int(case.inverter_life), life=case.inverter_life,
                 replace=True, escalation=case.inverter_escalation),
    ]
    if case.export_rate and et["surplus_export_kwh"].sum() > 0:
        pv.items.append(CostItem("Surplus export credit", kind="series", category="Energy",
                                 series=list(-et["surplus_export_kwh"] * case.export_rate),
                                 escalation=case.tariff_escalation))
    if case.carbon_price:
        grid.items.append(CostItem("Carbon cost of grid electricity", kind="series",
                                   category="Carbon", series=list(et["co2_A_t"] * case.carbon_price),
                                   escalation=case.carbon_escalation))
        pv.items.append(CostItem("Carbon cost of grid electricity", kind="series",
                                 category="Carbon", series=list(et["co2_B_t"] * case.carbon_price),
                                 escalation=case.carbon_escalation))
    # the inverter replacement item would start at a year beyond N if life >= N
    if case.inverter_life >= n:
        pv.items = [i for i in pv.items if i.name != "Inverter replacement"]
    return grid, pv, et


# ---------------------------------------------------------------------------------------
# Parameter tornado (physical inputs)
# ---------------------------------------------------------------------------------------
TORNADO_RANGES = {
    # field: (label, low, high, source/justification)
    "capex_per_kwp": ("PV capex (Rs/kWp)", 50000, 75000,
                      "MNRE benchmark Rs 50,000/kW (low); upper 2026 market quotes (high)"),
    "specific_yield": ("Specific yield (kWh/kWp/yr)", 1300, 1600, "4-5 units/kWp/day rule of thumb"),
    "degradation": ("Module degradation (%/yr)", 0.003, 0.008, "Jordan & Kurtz: median 0.5%, mean 0.8%"),
    "tariff_escalation": ("Tariff escalation (%/yr)", 0.0, 0.06,
                          "MERC trajectory falls to FY30; FY21-FY27 history ~5.7%/yr"),
    "discount_rate": ("Discount rate (%/yr)", 0.05, 0.10, "Loan rate 5.75% to opportunity cost 10%"),
    "om_per_year": ("O&M (Rs/yr)", 1000, 4000, "Rs 2,000-5,000/yr quoted for 3-5 kW systems"),
    "inverter_cost": ("Inverter replacement (Rs)", 12000, 35000, "Rs 8,000-35,000 residential on-grid"),
    "inverter_life": ("Inverter life (yr)", 10, 15, "10-15 years typical"),
    "subsidy": ("Subsidy (Rs)", 0, 60000, "No subsidy vs full CFA for 2 kWp"),
}


def tornado_parameters(case: SolarCase, fields: list[str] | None = None) -> pd.DataFrame:
    def ns(c: SolarCase) -> float:
        a, b, _ = build_alternatives(c)
        return net_savings(a, b, c.analysis_years, c.discount_rate)

    ref = ns(case)
    rows = []
    for f in fields or list(TORNADO_RANGES):
        label, lo, hi, src = TORNADO_RANGES[f]
        vals = []
        for v in (lo, hi):
            c2 = replace(case, **{f: v})
            vals.append(ns(c2))
        rows.append({"parameter": label, "low_input": lo, "high_input": hi,
                     "ns_at_low": vals[0], "ns_at_high": vals[1],
                     "range": abs(vals[1] - vals[0]), "basis": src})
    out = pd.DataFrame(rows).sort_values("range", ascending=False).reset_index(drop=True)
    out.attrs["reference"] = ref
    return out


DEFAULT_SOURCES = [
    ("Tariff slabs FY 2026-27 (3.96 / 10.80 / 15.03 / 17.53 Rs/kWh), fixed Rs 130/month",
     "MERC Order, Case No. 75 of 2025 (MSEDCL review of MYT Order), as tabulated by billcalc.in (Aug 2026); 101-300 slab corroborated by The Hitavada (26 Jun 2025)"),
    ("LT wheeling charge Rs 1.60/kWh (FY 2026-27)", "MERC Order, Case No. 75 of 2025, Table 8"),
    ("Electricity duty 16% (residential)", "billcalc.in MSEDCL schedule; check against a current bill"),
    ("PM Surya Ghar CFA Rs 30,000/kW up to 2 kW, Rs 18,000 for 3rd kW, cap Rs 78,000",
     "PM Surya Ghar CFA structure (pmsuryaghar.gov.in via JBVNL/Pune district notices); PIB"),
    ("Capex Rs 60,000/kWp", "MNRE benchmark Rs 50,000/kW (Feb 2024); 2 kW market range Rs 0.9-1.6 lakh (2026)"),
    ("Specific yield 1,440 kWh/kWp/yr (4 units/day)", "Industry rule of thumb 4-5 units/kWp/day"),
    ("Degradation 0.5%/yr", "Jordan & Kurtz (2013), Prog. Photovolt. - median of ~2,000 rates"),
    ("Inverter life 12 yr, replacement Rs 20,000", "Typical 10-15 yr string-inverter life; Rs 12,000-35,000 replacement"),
    ("O&M Rs 2,000/yr", "Rs 2,000-5,000/yr quoted for 3-5 kW residential systems"),
    ("Discount rate 7% nominal", "PM Surya Ghar concessional loan 5.75% (repo + 0.5%) up to ~7% bank rates"),
    ("General inflation 4%", "RBI flexible inflation target (CPI 4%)"),
    ("Grid emission factor 0.727 tCO2/MWh", "CEA CO2 Baseline Database v20 (FY 2023-24), weighted average"),
    ("Net metering up to 10 kW exempt from Grid Support Charge; residential exempt from ToD-slot banking",
     "MERC Order, Case No. 75 of 2025, paras 35.16 and 38.11"),
]
