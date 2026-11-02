"""
LCCA Decision Tool  -  Streamlit front end
CE725 Construction Economics and Finance, Topic 6 (Life Cycle Cost Analysis)

Run locally:   pip install -r requirements.txt   then   streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lcca import (Alternative, CostItem, SolarCase, SlabTariff, breakeven_discount_rate,
                  build_alternatives, cashflow_table, discounted_payback,
                  lcc_vs_discount_rate, net_savings, pm_surya_ghar_cfa, real_rate,
                  simple_payback, summary, tornado_items, tornado_parameters, yearly_totals)
from lcca.io import (frame_to_items, items_to_frame, project_from_json, project_to_json,
                     results_workbook)
from lcca.solar import DEFAULT_SOURCES

st.set_page_config(page_title="LCCA Decision Tool", page_icon="📐", layout="wide")


def inr(x: float) -> str:
    """Indian-style rupee formatting (lakh/crore grouping)."""
    neg = x < 0
    x = abs(round(x))
    s = str(int(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-₹" if neg else "₹") + s


# ---------------------------------------------------------------------------------------
# Sidebar: mode and global settings
# ---------------------------------------------------------------------------------------
st.sidebar.title("📐 LCCA Decision Tool")
mode = st.sidebar.radio("Analysis mode",
                        ["Rooftop solar vs grid (benchmark)", "General LCCA (any alternatives)"],
                        help="The solar mode builds the cost streams from physical inputs and the "
                             "DISCOM slab tariff. The general mode lets you enter any cost items.")

st.sidebar.subheader("Economic settings")
n_years = int(st.sidebar.number_input("Analysis period N (years)", 1, 100, 25, 1))
d = st.sidebar.number_input("Nominal discount rate (%/yr)", 0.0, 50.0, 7.0, 0.25) / 100
inflation = st.sidebar.number_input("General inflation (%/yr)", 0.0, 30.0, 4.0, 0.25,
                                    help="Used to report the real discount rate and as the default "
                                         "O&M escalation in solar mode.") / 100
st.sidebar.caption(f"Real discount rate (Fisher) = {real_rate(d, inflation) * 100:.2f}%/yr")

alts: list[Alternative] = []
energy_df: pd.DataFrame | None = None
solar_case: SolarCase | None = None

# ---------------------------------------------------------------------------------------
# Mode 1: Solar vs grid
# ---------------------------------------------------------------------------------------
if mode.startswith("Rooftop"):
    st.title("Rooftop solar PV vs grid electricity: life cycle cost comparison")
    st.caption("Default inputs = team benchmark case (MSEDCL LT-I(B) residential consumer in "
               "Maharashtra, FY 2026-27 tariff). Change any input; every result updates.")

    with st.sidebar.expander("Building & consumption", expanded=True):
        cons = st.number_input("Monthly consumption (kWh)", 0.0, 10000.0, 300.0, 10.0)
    with st.sidebar.expander("Grid tariff (base year)", expanded=False):
        st.caption("Telescopic monthly slabs. Leave the last 'upper' blank for 'and above'.")
        slab_df = st.data_editor(
            pd.DataFrame({"upper_kWh": [100, 300, 500, None],
                          "energy_charge_Rs_per_kWh": [3.96, 10.80, 15.03, 17.53]}),
            num_rows="dynamic", key="slabs", use_container_width=True)
        wheeling = st.number_input("Wheeling charge (₹/kWh)", 0.0, 20.0, 1.60, 0.05)
        fixed = st.number_input("Fixed charge (₹/month)", 0.0, 5000.0, 130.0, 5.0)
        duty = st.number_input("Electricity duty (%)", 0.0, 50.0, 16.0, 0.5) / 100
        fac = st.number_input("Fuel adjustment charge (₹/kWh)", -5.0, 10.0, 0.0, 0.05)
        tariff_esc = st.number_input("Tariff escalation (%/yr, nominal)", -10.0, 30.0, 3.0, 0.25) / 100
    with st.sidebar.expander("Rooftop PV system", expanded=True):
        kwp = st.number_input("Capacity (kWp)", 0.5, 500.0, 2.0, 0.5)
        capex = st.number_input("Installed cost (₹/kWp, incl. GST)", 0.0, 500000.0, 60000.0, 1000.0)
        auto_sub = st.checkbox("Subsidy = PM Surya Ghar CFA rule", True)
        subsidy = None if auto_sub else st.number_input("Subsidy (₹)", 0.0, 1e7, 60000.0, 1000.0)
        if auto_sub:
            st.caption(f"CFA for {kwp:g} kWp = {inr(pm_surya_ghar_cfa(kwp))}")
        yield_ = st.number_input("Specific yield, year 1 (kWh/kWp/yr)", 500.0, 2500.0, 1440.0, 10.0)
        degr = st.number_input("Degradation (%/yr)", 0.0, 5.0, 0.5, 0.05) / 100
        mod_life = st.number_input("Module life (years)", 1, 50, 25, 1)
        om = st.number_input("O&M (₹/yr, base-year price)", 0.0, 1e6, 2000.0, 100.0)
        om_esc = st.number_input("O&M escalation (%/yr)", -10.0, 30.0, inflation * 100, 0.25) / 100
        inv_cost = st.number_input("Inverter replacement cost (₹)", 0.0, 1e7, 20000.0, 500.0)
        inv_life = st.number_input("Inverter life (years, whole number)", 1, 50, 12, 1)
        inv_esc = st.number_input("Inverter price escalation (%/yr)", -20.0, 30.0, 0.0, 0.25) / 100
        export = st.number_input("Surplus export rate (₹/kWh)", 0.0, 20.0, 0.0, 0.1,
                                 help="Paid for net surplus at year end under net metering. "
                                      "0 = conservative (no credit).")
    with st.sidebar.expander("Carbon (optional)", expanded=False):
        ef = st.number_input("Grid emission factor (tCO₂/MWh)", 0.0, 2.0, 0.727, 0.001)
        cprice = st.number_input("Carbon price (₹/tCO₂)", 0.0, 1e6, 0.0, 100.0,
                                 help="0 = report tonnes only, not monetised.")
        cesc = st.number_input("Carbon price escalation (%/yr)", -10.0, 30.0, 0.0, 0.5) / 100

    slabs = []
    for _, r in slab_df.dropna(subset=["energy_charge_Rs_per_kWh"]).iterrows():
        up = None if pd.isna(r["upper_kWh"]) else float(r["upper_kWh"])
        slabs.append((up, float(r["energy_charge_Rs_per_kWh"])))
    slabs.sort(key=lambda s: float("inf") if s[0] is None else s[0])
    if not slabs or slabs[-1][0] is not None:
        st.sidebar.warning("The last slab should have a blank upper limit ('and above'). "
                           "Units above the last limit are billed at the last rate.")
        if slabs:
            slabs[-1] = (None, slabs[-1][1])
    tariff = SlabTariff(slabs=slabs, wheeling=wheeling, fixed_monthly=fixed, duty=duty, fac=fac)
    solar_case = SolarCase(analysis_years=n_years, discount_rate=d, general_inflation=inflation,
                           monthly_consumption_kwh=cons, tariff=tariff, tariff_escalation=tariff_esc,
                           capacity_kwp=kwp, capex_per_kwp=capex, subsidy=subsidy,
                           specific_yield=yield_, degradation=degr, module_life=float(mod_life),
                           om_per_year=om, om_escalation=om_esc, inverter_cost=inv_cost,
                           inverter_life=float(inv_life), inverter_escalation=inv_esc,
                           export_rate=export, grid_emission_factor=ef, carbon_price=cprice,
                           carbon_escalation=cesc)
    if mod_life < n_years:
        st.warning(f"Module life ({mod_life} yr) is shorter than the analysis period ({n_years} yr): "
                   "the PV system is re-bought at end of life and generation is assumed to restart. "
                   "Consider setting N equal to the module life.")
    try:
        g, p, energy_df = build_alternatives(solar_case)
        alts = [g, p]
    except ValueError as exc:
        st.error(f"Input error: {exc}")
        st.stop()

# ---------------------------------------------------------------------------------------
# Mode 2: General LCCA
# ---------------------------------------------------------------------------------------
else:
    st.title("General life cycle cost analysis")
    st.caption("Enter each alternative as a list of cost items at base-year (today's) prices. "
               "Positive = cost, negative = benefit / subsidy / income.")

    def flooring_example() -> list[Alternative]:
        return [
            Alternative("Vitrified tile", [
                CostItem("Tile floor (supply + lay)", "capital", 150000, "Initial", life=20),
                CostItem("Cleaning & repairs", "annual", 2000, "O&M", escalation=0.0)]),
            Alternative("Epoxy coating", [
                CostItem("Epoxy floor", "capital", 90000, "Initial", life=8),
                CostItem("Cleaning & repairs", "annual", 3000, "O&M", escalation=0.0)]),
        ]

    preset = st.sidebar.selectbox("Start from", ["Illustrative flooring example", "Blank (2 alternatives)",
                                                 "Upload project file (.json)"])
    if preset.startswith("Upload"):
        up = st.sidebar.file_uploader("Project file", type="json")
        if up is None:
            st.info("Upload a project .json saved from this tool, or pick another starting point.")
            st.stop()
        loaded, n_json, d_json, _ = project_from_json(up.getvalue().decode())
        start_alts = loaded
        st.sidebar.caption(f"File saved with N = {n_json}, d = {d_json * 100:.2f}% "
                           "(the sidebar values above are used).")
    elif preset.startswith("Blank"):
        start_alts = [Alternative("Alternative 1", [CostItem("Initial cost", "once", 0, "Initial")]),
                      Alternative("Alternative 2", [CostItem("Initial cost", "once", 0, "Initial")])]
    else:
        start_alts = flooring_example()
        st.info("Illustrative numbers only (synthetic test case used in the validation report).")

    n_alt = st.sidebar.number_input("Number of alternatives", 2, 6, len(start_alts), 1)
    while len(start_alts) < n_alt:
        start_alts.append(Alternative(f"Alternative {len(start_alts) + 1}",
                                      [CostItem("Initial cost", "once", 0, "Initial")]))
    start_alts = start_alts[: int(n_alt)]

    kind_help = ("once = single amount in 'year'; annual = every year from 'start' to 'end' "
                 "(blank end = N); capital = bought in 'year', lasts 'life' years, re-bought if "
                 "'replace' is ticked, residual value credited automatically at N.")
    cols = st.columns(min(int(n_alt), 3))
    for k, a in enumerate(start_alts):
        with cols[k % len(cols)]:
            name = st.text_input(f"Alternative {k + 1} name", a.name, key=f"name{k}")
            df = st.data_editor(
                items_to_frame(a), num_rows="dynamic", key=f"items{k}", use_container_width=True,
                column_config={
                    "kind": st.column_config.SelectboxColumn(options=["once", "annual", "capital"],
                                                             help=kind_help, required=True),
                    "category": st.column_config.SelectboxColumn(
                        options=["Initial", "O&M", "Energy", "Replacement", "Subsidy", "Other"]),
                    "replace": st.column_config.CheckboxColumn(default=True),
                    "amount": st.column_config.NumberColumn("amount (₹)", format="%.0f"),
                    "escalation_pct": st.column_config.NumberColumn("escalation (%/yr)"),
                    "has_series": None,
                })
            alts.append(Alternative(name, frame_to_items(df, a)))
    st.caption(kind_help)
    try:
        for a in alts:
            for it in a.items:
                it.validate(n_years)
    except ValueError as exc:
        st.error(f"Input error: {exc}")
        st.stop()

# ---------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------
summ = summary(alts, n_years, d)
best = summ.sort_values("lcc").iloc[0]
base = alts[0]
others = alts[1:]

tab_sum, tab_cf, tab_sens, tab_energy, tab_method = st.tabs(
    ["Decision summary", "Cash flows", "Sensitivity", "Energy & carbon", "Method & sources"])

with tab_sum:
    st.subheader("Recommendation")
    st.success(f"**{best['alternative']}** has the lowest life cycle cost over {n_years} years "
               f"at a {d * 100:.2f}% discount rate: {inr(best['lcc'])} in present value "
               f"(equivalent to {inr(best['euac'])} per year).")
    mcols = st.columns(len(alts))
    for c, (_, row) in zip(mcols, summ.iterrows()):
        c.metric(row["alternative"], inr(row["lcc"]),
                 delta=None if row["alternative"] == base.name
                 else f"{inr(row['lcc'] - summ.iloc[0]['lcc'])} vs {base.name}",
                 delta_color="inverse")
        c.caption(f"Initial outlay {inr(row['initial_cost'])} · EUAC {inr(row['euac'])}/yr")

    rows = []
    for o in others:
        be = breakeven_discount_rate(base, o, n_years)
        rows.append({
            "Compared with": base.name, "Alternative": o.name,
            "Net savings (PV)": net_savings(base, o, n_years, d),
            "Simple payback (yr)": simple_payback(base, o, n_years),
            "Discounted payback (yr)": discounted_payback(base, o, n_years, d),
            "Break-even discount rate": ", ".join(f"{r * 100:.2f}%" for r in be) or "none in -5%..100%",
        })
    comp = pd.DataFrame(rows)
    st.dataframe(comp.style.format({"Net savings (PV)": inr,
                                    "Simple payback (yr)": lambda v: "—" if v is None or pd.isna(v) else f"{v:.1f}",
                                    "Discounted payback (yr)": lambda v: "—" if v is None or pd.isna(v) else f"{v:.1f}"}),
                 use_container_width=True, hide_index=True)
    st.caption("Net savings > 0 means the alternative is cheaper than the first alternative over the "
               "life cycle. The break-even discount rate is the rate at which the ranking flips "
               "(the IRR of the extra investment).")

    st.subheader("Present value by cost category")
    pv_cols = [c for c in summ.columns if c.startswith("pv: ")]
    cat = summ.set_index("alternative")[pv_cols].rename(columns=lambda c: c[4:])
    st.bar_chart(cat, stack=True)
    st.dataframe(cat.T.style.format(inr), use_container_width=True)

with tab_cf:
    st.subheader("Cumulative present value of costs")
    cum = pd.DataFrame({a.name: yearly_totals(a, n_years, d)["cumulative_pv"] for a in alts})
    st.line_chart(cum)
    st.caption("Where the lines cross is the discounted payback point.")
    pick = st.selectbox("Show cash-flow detail for", [a.name for a in alts])
    a_sel = next(a for a in alts if a.name == pick)
    st.dataframe(cashflow_table(a_sel, n_years, d).style.format(
        {"base": "{:,.0f}", "nominal": "{:,.0f}", "discount_factor": "{:.5f}", "present_value": "{:,.0f}"}),
        use_container_width=True, hide_index=True, height=360)
    extra = {"Energy & carbon": energy_df} if energy_df is not None else {}
    st.download_button("⬇️ Download all results (Excel)", results_workbook(alts, n_years, d, extra),
                       "lcca_results.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("⬇️ Save project (.json)", project_to_json(alts, n_years, d, mode),
                       "lcca_project.json", "application/json")

with tab_sens:
    st.subheader("Discount-rate sensitivity")
    lo_r, hi_r = st.slider("Discount-rate range (%)", 0.0, 30.0, (2.0, 15.0), 0.5)
    rates = [lo_r / 100 + k * (hi_r - lo_r) / 100 / 40 for k in range(41)]
    sweep = lcc_vs_discount_rate(alts, n_years, rates)
    sweep["discount_rate"] = (sweep["discount_rate"] * 100).round(2)
    st.line_chart(sweep.set_index("discount_rate"))
    st.caption("LCC of each alternative (₹, present value) against the discount rate (%).")

    if len(alts) >= 2:
        st.subheader(f"Tornado: what moves the net savings of {others[0].name} vs {base.name}?")
        if solar_case is not None:
            tor = tornado_parameters(solar_case)
            ref = tor.attrs["reference"]
            chart = pd.DataFrame({"low input": tor["ns_at_low"] - ref,
                                  "high input": tor["ns_at_high"] - ref}).set_index(tor["parameter"])
            st.bar_chart(chart, horizontal=True, stack=False)
            st.caption(f"Bars show the change from the base net savings of {inr(ref)}. "
                       "Ranges are documented in the table.")
            st.dataframe(tor.drop(columns=["range"]).style.format(
                {"ns_at_low": inr, "ns_at_high": inr}), use_container_width=True, hide_index=True)
            flips = tor[(tor["ns_at_low"] < 0) | (tor["ns_at_high"] < 0)]
            if flips.empty:
                st.info("No single input moved across its range reverses the decision.")
            else:
                st.warning("The decision reverses within the range of: " + ", ".join(flips["parameter"]))
        else:
            swing = st.slider("Swing each item's amount by ±%", 5, 50, 20, 5) / 100
            tor = tornado_items(base, others[0], n_years, d, swing)
            ref = tor.attrs["reference"]
            chart = pd.DataFrame({"amount low": tor["low"] - ref,
                                  "amount high": tor["high"] - ref}).set_index(tor["parameter"])
            st.bar_chart(chart, horizontal=True, stack=False)
            st.caption(f"Change from the base net savings of {inr(ref)}.")

with tab_energy:
    if energy_df is None:
        st.info("Energy and carbon results are shown in the solar mode.")
    else:
        e1, e2, e3 = st.columns(3)
        e1.metric("PV generation, year 1", f"{energy_df['generation_kwh'].iloc[0]:,.0f} kWh")
        e2.metric("Bill saving, year 1 (base prices)", inr(energy_df["bill_saving_base"].iloc[0]))
        e3.metric(f"CO₂ avoided over {n_years} yr", f"{energy_df['co2_avoided_t'].sum():,.1f} t")
        st.line_chart(energy_df.set_index("year")[["generation_kwh", "grid_import_B_kwh"]])
        st.dataframe(energy_df.style.format("{:,.2f}"), use_container_width=True, hide_index=True)
        b0 = solar_case.tariff.monthly_bill(solar_case.monthly_consumption_kwh)
        st.caption(f"Monthly grid bill without PV at base-year tariff: energy {inr(b0['energy'])} + "
                   f"wheeling {inr(b0['wheeling'])} + fixed {inr(b0['fixed'])} + duty {inr(b0['duty'])} "
                   f"= {inr(b0['total'])}.")

with tab_method:
    st.markdown(r"""
**Method (NIST Handbook 135 / ASTM E917 / ISO 15686-5).** For each alternative

$$LCC = \sum_{t=0}^{N} \frac{CF_t}{(1+d)^t}, \qquad CF_t = \sum_{\text{items}} A_{i,t}\,(1+e_i)^t$$

where $A_{i,t}$ is the item amount at base-year prices, $e_i$ its nominal escalation and $d$ the
nominal discount rate (equivalent to real-rate discounting with differential escalation).
Capital items are replaced at the end of each service life while the replacement year is before $N$;
unused life at $N$ is credited as a straight-line **residual value**
$R = C\,(1+e)^N \times \frac{\text{remaining life}}{\text{life}}$.
EUAC $= LCC \times \frac{d(1+d)^N}{(1+d)^N-1}$. Net savings $NS = LCC_{base} - LCC_{alt}$.

**Conventions:** end-of-year cash flows; year 0 = installation; positive = cost; the alternative
with the lowest LCC is preferred.

**Known limitations:** monthly consumption and generation are treated as uniform (no seasonal or
time-of-day profile); tariff escalation is a single constant rate; fuel adjustment charge excluded
by default; taxes on subsidy and financing costs are not modelled; results are only as good as the
inputs — verify every input against the cited source before use.
""")
    if solar_case is not None:
        st.subheader("Sources of default inputs")
        st.dataframe(pd.DataFrame(DEFAULT_SOURCES, columns=["Input", "Source"]),
                     use_container_width=True, hide_index=True)
    st.caption("Privacy: the tool stores nothing on a server. Inputs live only in your browser "
               "session; run it locally (`streamlit run app.py`) for confidential project data.")
