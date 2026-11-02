"""Builds Benchmark_LCCA_Solar_vs_Grid.xlsx: the manual benchmark in a plain spreadsheet.
Every result is an Excel formula on the Inputs sheet; nothing is computed in Python except the
'Tool output' column on the Validation sheet, which is pasted from a tool run for comparison."""
import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = sys.argv[1] if len(sys.argv) > 1 else "Benchmark_LCCA_Solar_vs_Grid.xlsx"
TOOL = {}  # filled from argv JSON if provided
if len(sys.argv) > 2:
    import json
    TOOL = json.load(open(sys.argv[2]))

F = "Arial"
BLUE = Font(name=F, color="0000FF")
BLACK = Font(name=F)
BOLD = Font(name=F, bold=True)
HEAD = Font(name=F, bold=True, color="FFFFFF")
GREEN = Font(name=F, color="008000")
TITLE = Font(name=F, bold=True, size=14)
HFILL = PatternFill("solid", fgColor="1F4E78")
YFILL = PatternFill("solid", fgColor="FFFF00")
GFILL = PatternFill("solid", fgColor="E2EFDA")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
RS = '"₹"#,##0;("₹"#,##0);"-"'
RS2 = '"₹"#,##0.00;("₹"#,##0.00);"-"'

wb = Workbook()

# ------------------------------------------------------------------ README
ws = wb.active
ws.title = "README"
lines = [
    ("Manual benchmark: LCCA of rooftop PV vs grid electricity", TITLE),
    ("CE725 Construction Economics and Finance, Topic 6. Team benchmark case for validating the LCCA tool.", BLACK),
    ("", BLACK),
    ("How to read this workbook", BOLD),
    ("1. Inputs: every assumption in one labelled cell with its source. Blue text = hard-coded input; yellow = key assumption.", BLACK),
    ("2. Tariff: the slab bill for one month worked out line by line (the hand calculation).", BLACK),
    ("3. AltA_Grid and AltB_PV: year-by-year cash flows at nominal prices, discount factor and present value.", BLACK),
    ("4. Summary: LCC, EUAC, net savings, payback; plus an independent closed-form check using P/A factors.", BLACK),
    ("5. RateSweep: LCC of both alternatives at discount rates from 2% to 15% (Excel NPV function).", BLACK),
    ("6. Validation: tool outputs (pasted) against the workbook formulas, with the difference.", BLACK),
    ("", BLACK),
    ("Conventions", BOLD),
    ("Year 0 = installation. Cash flows at end of each year. Amounts entered at base-year (FY 2026-27) prices.", BLACK),
    ("Nominal cash flow in year t = base amount x (1+e)^t; discounted at nominal rate d: PV = CF/(1+d)^t.", BLACK),
    ("Positive = cost; negative = subsidy / residual value. Lowest LCC is preferred.", BLACK),
    ("Monthly consumption and generation are treated as uniform across the year (no seasonal profile).", BLACK),
    ("Module life must be >= analysis period in this sheet (no module replacement is modelled here).", BLACK),
    ("", BLACK),
    ("Colour code: blue = input, black = formula, green = link to another sheet.", BLACK),
    ("To test a scenario, change only the blue cells on Inputs; every other number recalculates.", BLACK),
]
for r, (text, font) in enumerate(lines, 1):
    c = ws.cell(r, 1, text)
    c.font = font
ws.column_dimensions["A"].width = 120

# ------------------------------------------------------------------ Inputs
wi = wb.create_sheet("Inputs")
wi["A1"] = "Inputs and assumptions (base year FY 2026-27)"
wi["A1"].font = TITLE
hdr = ["Parameter", "Symbol", "Value", "Unit", "Source / justification"]
for j, h in enumerate(hdr, 1):
    c = wi.cell(3, j, h)
    c.font, c.fill, c.border = HEAD, HFILL, BOX

inputs = [
    # key, label, symbol, value, unit, fmt, source, key_assumption
    ("N", "Analysis period", "N", 25, "years", "0", "Equal to PV module performance-warranty life (25 yr)", True),
    ("d", "Nominal discount rate", "d", 0.07, "per year", "0.00%", "PM Surya Ghar concessional loan 5.75% (repo + 0.5%); bank solar loans ~7%", True),
    ("i", "General inflation", "i", 0.04, "per year", "0.00%", "RBI CPI inflation target 4%", False),
    ("C", "Monthly consumption", "C", 300, "kWh/month", "0", "Benchmark household (PM Surya Ghar guidance: 150-300 units -> 2-3 kW)", True),
    ("u1", "Slab 1 upper limit", "", 100, "kWh/month", "0", "MSEDCL LT-I(B) residential slabs", False),
    ("u2", "Slab 2 upper limit", "", 300, "kWh/month", "0", "MSEDCL LT-I(B) residential slabs", False),
    ("u3", "Slab 3 upper limit", "", 500, "kWh/month", "0", "MSEDCL LT-I(B) residential slabs", False),
    ("r1", "Energy charge 0-100 kWh", "", 3.96, "Rs/kWh", "0.00", "MERC Order Case 75 of 2025, FY 2026-27 (as tabulated by billcalc.in, Aug 2026)", True),
    ("r2", "Energy charge 101-300 kWh", "", 10.80, "Rs/kWh", "0.00", "Same; corroborated by The Hitavada, 26 Jun 2025 (Rs 10.80 in 2026)", True),
    ("r3", "Energy charge 301-500 kWh", "", 15.03, "Rs/kWh", "0.00", "MERC Order Case 75 of 2025 via billcalc.in", False),
    ("r4", "Energy charge > 500 kWh", "", 17.53, "Rs/kWh", "0.00", "MERC Order Case 75 of 2025 via billcalc.in", False),
    ("w", "Wheeling charge (LT)", "", 1.60, "Rs/kWh", "0.00", "MERC Order Case 75 of 2025, Table 8 (FY 26-27)", True),
    ("fc", "Fixed charge (single phase)", "", 130, "Rs/month", "0", "MSEDCL tariff schedule via billcalc.in", False),
    ("ed", "Electricity duty", "", 0.16, "of bill", "0%", "Maharashtra residential electricity duty 16%", False),
    ("et", "Tariff escalation", "e_t", 0.03, "per year", "0.00%", "Team assumption: below CPI; MERC trajectory falls to FY30, FY21-27 history ~5.7%/yr", True),
    ("P", "PV capacity", "P", 2, "kWp", "0.0", "Sized so net import stays positive every month (no export)", True),
    ("cpk", "Installed cost", "", 60000, "Rs/kWp", "#,##0", "MNRE benchmark Rs 50,000/kW (Feb 2024); 2 kW market Rs 0.9-1.6 lakh (2026)", True),
    ("Y", "Specific yield (year 1)", "Y", 1440, "kWh/kWp/yr", "#,##0", "Rule of thumb 4 units/kWp/day (range 4-5)", True),
    ("g", "Module degradation", "g", 0.005, "per year", "0.00%", "Jordan & Kurtz (2013), median of ~2,000 field rates", False),
    ("Lm", "Module life", "", 25, "years", "0", "Typical 25-yr linear performance warranty", False),
    ("om", "O&M cost", "", 2000, "Rs/yr", "#,##0", "Rs 2,000-5,000/yr quoted for 3-5 kW residential systems", False),
    ("eom", "O&M escalation", "", "=C6", "per year", "0.00%", "Equal to general inflation", False),
    ("ic", "Inverter replacement cost", "", 20000, "Rs", "#,##0", "Residential on-grid inverter Rs 8,000-35,000 (2026)", False),
    ("Li", "Inverter life", "", 12, "years", "0", "Typical 10-15 years for string inverters", False),
    ("ei", "Inverter price escalation", "", 0.0, "per year", "0.00%", "Team assumption: electronics prices flat in nominal terms", False),
    ("EF", "Grid emission factor", "", 0.727, "tCO2/MWh", "0.000", "CEA CO2 Baseline Database v20 (FY 2023-24), weighted average", False),
]
REF = {}
for k, (key, label, sym, val, unit, fmt, src, keyass) in enumerate(inputs):
    r = 4 + k
    REF[key] = f"Inputs!$C${r}"
    wi.cell(r, 1, label).font = BLACK
    wi.cell(r, 2, sym).font = BLACK
    c = wi.cell(r, 3, val)
    c.font = BLACK if isinstance(val, str) and val.startswith("=") else BLUE
    c.number_format = fmt
    if keyass:
        c.fill = YFILL
    wi.cell(r, 4, unit).font = BLACK
    wi.cell(r, 5, src).font = BLACK
    for j in range(1, 6):
        wi.cell(r, j).border = BOX
r = 4 + len(inputs) + 1
wi.cell(r, 1, "Derived values").font = BOLD
derived = [
    ("cap", "PV system cost", f"={REF['P']}*{REF['cpk']}", "Rs", "#,##0", "P x cost per kWp"),
    ("sub", "PM Surya Ghar subsidy (CFA)", f"=30000*MIN({REF['P']},2)+18000*MAX(0,MIN({REF['P']},3)-2)", "Rs", "#,##0",
     "Rs 30,000/kW up to 2 kW + Rs 18,000 for 3rd kW, cap Rs 78,000"),
    ("G1", "PV generation, year 1", f"={REF['P']}*{REF['Y']}", "kWh/yr", "#,##0", "P x Y"),
    ("rr", "Real discount rate (for reference)", f"=(1+{REF['d']})/(1+{REF['i']})-1", "per year", "0.00%", "Fisher"),
]
for k, (key, label, f, unit, fmt, note) in enumerate(derived):
    rr = r + 1 + k
    REF[key] = f"Inputs!$C${rr}"
    wi.cell(rr, 1, label).font = BLACK
    c = wi.cell(rr, 3, f)
    c.font, c.number_format = BLACK, fmt
    wi.cell(rr, 4, unit).font = BLACK
    wi.cell(rr, 5, note).font = BLACK
    for j in range(1, 6):
        wi.cell(rr, j).border = BOX
for col, w in zip("ABCDE", (34, 8, 14, 12, 95)):
    wi.column_dimensions[col].width = w
wi.freeze_panes = "A4"


def bill_month(units_ref: str) -> str:
    """Excel expression for the monthly bill (Rs) at base-year tariff for `units_ref` kWh."""
    u = units_ref
    energy = (f"MIN({u},{REF['u1']})*{REF['r1']}"
              f"+MAX(0,MIN({u},{REF['u2']})-{REF['u1']})*{REF['r2']}"
              f"+MAX(0,MIN({u},{REF['u3']})-{REF['u2']})*{REF['r3']}"
              f"+MAX(0,{u}-{REF['u3']})*{REF['r4']}")
    return f"(({energy})+{u}*{REF['w']}+{REF['fc']})*(1+{REF['ed']})"


# ------------------------------------------------------------------ Tariff (hand calc of one month)
wt = wb.create_sheet("Tariff")
wt["A1"] = "Monthly bill at base-year tariff: slab-by-slab hand calculation"
wt["A1"].font = TITLE
wt["A3"], wt["B3"], wt["C3"] = "Line", "Alt A: grid only", "Alt B: with PV, year 1"
for c in ("A3", "B3", "C3"):
    wt[c].font, wt[c].fill = HEAD, HFILL
rows = [
    ("Units billed (kWh/month)", f"={REF['C']}", f"=MAX(0,{REF['C']}-{REF['G1']}/12)", "0.00"),
    ("Slab 1 units", "=MIN(B4,{u1})", "=MIN(C4,{u1})", "0.00"),
    ("Slab 2 units", "=MAX(0,MIN(B4,{u2})-{u1})", "=MAX(0,MIN(C4,{u2})-{u1})", "0.00"),
    ("Slab 3 units", "=MAX(0,MIN(B4,{u3})-{u2})", "=MAX(0,MIN(C4,{u3})-{u2})", "0.00"),
    ("Slab 4 units", "=MAX(0,B4-{u3})", "=MAX(0,C4-{u3})", "0.00"),
    ("Energy charge (Rs)", "=B5*{r1}+B6*{r2}+B7*{r3}+B8*{r4}", "=C5*{r1}+C6*{r2}+C7*{r3}+C8*{r4}", RS2),
    ("Wheeling charge (Rs)", "=B4*{w}", "=C4*{w}", RS2),
    ("Fixed charge (Rs)", "={fc}", "={fc}", RS2),
    ("Subtotal (Rs)", "=SUM(B9:B11)", "=SUM(C9:C11)", RS2),
    ("Electricity duty (Rs)", "=B12*{ed}", "=C12*{ed}", RS2),
    ("Monthly bill (Rs)", "=B12+B13", "=C12+C13", RS2),
    ("Annual bill = 12 x monthly (Rs)", "=12*B14", "=12*C14", RS2),
]
for k, (label, fb, fcx, fmt) in enumerate(rows):
    rr = 4 + k
    wt.cell(rr, 1, label).font = BOLD if "bill" in label.lower() else BLACK
    for j, f in ((2, fb), (3, fcx)):
        c = wt.cell(rr, j, f.format(**REF))
        c.font = GREEN if k in (0,) else BLACK
        c.number_format = fmt
        c.border = BOX
wt["A17"] = ("Check: Alt A annual bill should equal AltA_Grid!C6 (base bill, year 1); "
             "Alt B should equal AltB_PV!E6.")
wt["A17"].font = Font(name=F, italic=True)
wt["A18"] = "Difference A:"
wt["B18"] = "=B15-AltA_Grid!C6"
wt["A19"] = "Difference B:"
wt["B19"] = "=C15-AltB_PV!E6"
for c in ("B18", "B19"):
    wt[c].number_format = RS2
wt.column_dimensions["A"].width = 36
wt.column_dimensions["B"].width = 20
wt.column_dimensions["C"].width = 24

# ------------------------------------------------------------------ Year tables
YEARS = 25  # rows for years 0..25 (sheet assumes N = 25; rows beyond N are zeroed by formula)


def header(ws, cols):
    for j, h in enumerate(cols, 1):
        c = ws.cell(4, j, h)
        c.font, c.fill, c.border = HEAD, HFILL, BOX
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[4].height = 45


wa = wb.create_sheet("AltA_Grid")
wa["A1"] = "Alternative A: grid electricity only"
wa["A1"].font = TITLE
wa["A2"] = "Bill at base-year tariff is constant (consumption constant); escalated at tariff escalation."
colsA = ["Year t", "Grid import (kWh)", "Bill at base-year prices (Rs)", "Escalation factor (1+e_t)^t",
         "Nominal cash flow (Rs)", "Discount factor 1/(1+d)^t", "Present value (Rs)", "Cumulative PV (Rs)",
         "CO2 (t)"]
header(wa, colsA)
for t in range(0, YEARS + 1):
    r = 5 + t
    on = f"AND(A{r}>=1,A{r}<={REF['N']})"
    wa.cell(r, 1, t)
    wa.cell(r, 2, f"=IF({on},12*{REF['C']},0)")
    wa.cell(r, 3, f"=IF({on},12*{bill_month(REF['C'])},0)")
    wa.cell(r, 4, f"=(1+{REF['et']})^A{r}")
    wa.cell(r, 5, f"=C{r}*D{r}")
    wa.cell(r, 6, f"=1/(1+{REF['d']})^A{r}")
    wa.cell(r, 7, f"=E{r}*F{r}")
    wa.cell(r, 8, f"=G{r}" if t == 0 else f"=H{r - 1}+G{r}")
    wa.cell(r, 9, f"=B{r}*{REF['EF']}/1000")
last = 5 + YEARS
tot = last + 1
wa.cell(tot, 1, "TOTAL").font = BOLD
for j, col in ((2, "B"), (5, "E"), (7, "G"), (9, "I")):
    c = wa.cell(tot, j, f"=SUM({col}5:{col}{last})")
    c.font, c.fill = BOLD, GFILL
for r in range(5, tot + 1):
    for j, fmt in zip(range(1, 10), ("0", "#,##0", RS, "0.0000", RS, "0.00000", RS, RS, "0.000")):
        c = wa.cell(r, j)
        c.number_format = fmt
        c.border = BOX
        if c.font != BOLD:
            c.font = BLACK
wa.cell(tot, 1).font = BOLD
for j in range(1, 10):
    wa.column_dimensions[get_column_letter(j)].width = 17
wa.freeze_panes = "B5"

wb_ = wb.create_sheet("AltB_PV")
wb_["A1"] = "Alternative B: 2 kWp net-metered rooftop PV + grid for the balance"
wb_["A1"].font = TITLE
wb_["A2"] = ("Generation degrades geometrically; net monthly import billed at the slab tariff; "
             "inverter re-bought every Li years before N; unused inverter life credited at N.")
colsB = ["Year t", "PV generation (kWh)", "Net grid import (kWh/month)", "Grid import (kWh/yr)",
         "Bill at base-year prices (Rs)", "Bill nominal (Rs)", "PV system cost (Rs)", "Subsidy (Rs)",
         "O&M nominal (Rs)", "Inverter replacement nominal (Rs)", "Residual value (Rs)",
         "Total nominal cash flow (Rs)", "Discount factor", "Present value (Rs)", "Cumulative PV (Rs)",
         "CO2 (t)"]
header(wb_, colsB)
for t in range(0, YEARS + 1):
    r = 5 + t
    on = f"AND(A{r}>=1,A{r}<={REF['N']})"
    wb_.cell(r, 1, t)
    wb_.cell(r, 2, f"=IF({on},{REF['G1']}*(1-{REF['g']})^(A{r}-1),0)")
    wb_.cell(r, 3, f"=IF({on},MAX(0,{REF['C']}-B{r}/12),0)")
    wb_.cell(r, 4, f"=12*C{r}")
    wb_.cell(r, 5, f"=IF({on},12*{bill_month(f'C{r}')},0)")
    wb_.cell(r, 6, f"=E{r}*(1+{REF['et']})^A{r}")
    wb_.cell(r, 7, f"=IF(A{r}=0,{REF['cap']},0)")
    wb_.cell(r, 8, f"=IF(A{r}=0,-{REF['sub']},0)")
    wb_.cell(r, 9, f"=IF({on},{REF['om']}*(1+{REF['eom']})^A{r},0)")
    wb_.cell(r, 10, f"=IF(AND(A{r}>0,MOD(A{r},{REF['Li']})=0,A{r}<{REF['N']}),"
                    f"{REF['ic']}*(1+{REF['ei']})^A{r},0)")
    # residual: inverter bought at last multiple of Li below N; modules (life Lm >= N)
    lastinv = f"{REF['Li']}*INT(({REF['N']}-1)/{REF['Li']})"
    wb_.cell(r, 11, f"=IF(A{r}={REF['N']},"
                    f"-IF({lastinv}>0,{REF['ic']}*(1+{REF['ei']})^A{r}*MAX(0,{lastinv}+{REF['Li']}-{REF['N']})/{REF['Li']},0)"
                    f"-{REF['cap']}*MAX(0,{REF['Lm']}-{REF['N']})/{REF['Lm']},0)")
    wb_.cell(r, 12, f"=F{r}+G{r}+H{r}+I{r}+J{r}+K{r}")
    wb_.cell(r, 13, f"=1/(1+{REF['d']})^A{r}")
    wb_.cell(r, 14, f"=L{r}*M{r}")
    wb_.cell(r, 15, f"=N{r}" if t == 0 else f"=O{r - 1}+N{r}")
    wb_.cell(r, 16, f"=D{r}*{REF['EF']}/1000")
wb_.cell(tot, 1, "TOTAL").font = BOLD
for j in (2, 4, 6, 7, 8, 9, 10, 11, 12, 14, 16):
    col = get_column_letter(j)
    c = wb_.cell(tot, j, f"=SUM({col}5:{col}{last})")
    c.font, c.fill = BOLD, GFILL
fmtsB = ("0", "#,##0", "0.00", "#,##0", RS, RS, RS, RS, RS, RS, RS, RS, "0.00000", RS, RS, "0.000")
for r in range(5, tot + 1):
    for j, fmt in zip(range(1, 17), fmtsB):
        c = wb_.cell(r, j)
        c.number_format = fmt
        c.border = BOX
        if r != tot:
            c.font = BLACK
for j in range(1, 17):
    wb_.column_dimensions[get_column_letter(j)].width = 15
wb_.freeze_panes = "B5"

# PV of each component (for the validation table)
comp_r = tot + 2
wb_.cell(comp_r, 1, "PV by component").font = BOLD
comps = [("Energy (bill)", "F"), ("PV system", "G"), ("Subsidy", "H"), ("O&M", "I"),
         ("Inverter replacements", "J"), ("Residual value", "K")]
for k, (name, col) in enumerate(comps):
    rr = comp_r + 1 + k
    wb_.cell(rr, 1, name).font = BLACK
    c = wb_.cell(rr, 2, f"=SUMPRODUCT({col}5:{col}{last},$M$5:$M${last})")
    c.number_format, c.font = RS2, BLACK
c = wb_.cell(comp_r + 7, 1, "Sum of components")
c.font = BOLD
c = wb_.cell(comp_r + 7, 2, f"=SUM(B{comp_r + 1}:B{comp_r + 6})")
c.number_format, c.font = RS2, BOLD
PVB = {name: f"AltB_PV!$B${comp_r + 1 + k}" for k, (name, _) in enumerate(comps)}

# ------------------------------------------------------------------ Summary
ss = wb.create_sheet("Summary")
ss["A1"] = "Summary of results (all values recalculate from Inputs)"
ss["A1"].font = TITLE
for j, h in enumerate(["Metric", "A: Grid only", "B: Rooftop PV + grid", "Note"], 1):
    c = ss.cell(3, j, h)
    c.font, c.fill, c.border = HEAD, HFILL, BOX
crf = f"({REF['d']}*(1+{REF['d']})^{REF['N']}/((1+{REF['d']})^{REF['N']}-1))"
srows = [
    ("Life cycle cost, LCC (PV, Rs)", f"=AltA_Grid!G{tot}", f"=AltB_PV!N{tot}", "Sum of present values, years 0-N", RS2),
    ("Initial outlay, year 0 (Rs)", "=AltA_Grid!E5", "=AltB_PV!L5", "Net of subsidy", RS),
    ("EUAC (Rs/yr)", f"=B4*{crf}", f"=C4*{crf}", "LCC x CRF(d, N)", RS2),
    ("Net savings of B vs A (PV, Rs)", "", "=B4-C4", "NS = LCC(A) - LCC(B); > 0 means B preferred", RS2),
    ("Preferred alternative", "", '=IF(C4<B4,"B: Rooftop PV + grid","A: Grid only")', "Lowest LCC", "@"),
    ("Discounted payback of B (years)", "", f"=IFERROR(MATCH(TRUE,INDEX(AltA_Grid!H5:H{last}-AltB_PV!O5:O{last}>=0,0),0)-1,\"none\")",
     "First year-end at which cumulative PV(A) >= cumulative PV(B)", "0"),
    ("CO2 over N years (t)", f"=AltA_Grid!I{tot}", f"=AltB_PV!P{tot}", "Grid imports x CEA factor", "#,##0.0"),
    ("CO2 avoided by B (t)", "", "=B10-C10", "", "#,##0.0"),
]
for k, (label, fa, fb, note, fmt) in enumerate(srows):
    rr = 4 + k
    ss.cell(rr, 1, label).font = BOLD if k in (0, 3, 4) else BLACK
    for j, f in ((2, fa), (3, fb)):
        c = ss.cell(rr, j, f if f else None)
        c.number_format, c.font, c.border = fmt, GREEN if "!" in (f or "") else BLACK, BOX
    ss.cell(rr, 4, note).font = BLACK
    ss.cell(rr, 1).border = BOX

# closed-form check
ss["A14"] = "Independent closed-form check (textbook factors, no year-by-year table)"
ss["A14"].font = BOLD
x = f"((1+{REF['et']})/(1+{REF['d']}))"
xo = f"((1+{REF['eom']})/(1+{REF['d']}))"
kx = f"((1-{REF['g']})*{x})"
c12 = f"12*(1+{REF['ed']})"
closed = [
    ("UPV* factor for tariff, sum((1+e)/(1+d))^t", f"={x}*(1-{x}^{REF['N']})/(1-{x})", "0.00000"),
    ("A: LCC = annual base bill x UPV*", f"=AltA_Grid!C6*B15", RS2),
    ("B: bill term 1  [C x (r1+w) + fixed] x 12(1+ed) x UPV*",
     f"={c12}*({REF['C']}*({REF['r1']}+{REF['w']})+{REF['fc']})*B15", RS2),
    ("B: bill term 2  -(G1/12)(r1+w) x 12(1+ed) x x(1-(kx)^N)/(1-kx)",
     f"=-{c12}*({REF['G1']}/12)*({REF['r1']}+{REF['w']})*{x}*(1-{kx}^{REF['N']})/(1-{kx})", RS2),
    ("B: O&M = om x UPV*(e_om)", f"={REF['om']}*{xo}*(1-{xo}^{REF['N']})/(1-{xo})", RS2),
    ("B: inverter = ic[(P/F,12)+(P/F,24)] - ic x 11/12 x (P/F,25)",
     f"={REF['ic']}/(1+{REF['d']})^12+{REF['ic']}/(1+{REF['d']})^24-{REF['ic']}*11/12/(1+{REF['d']})^25", RS2),
    ("B: capital net of subsidy", f"={REF['cap']}-{REF['sub']}", RS2),
    ("B: LCC (closed form)", "=SUM(B17:B21)", RS2),
    ("Difference A: table - closed form", "=B4-B16", RS2),
    ("Difference B: table - closed form", "=C4-B22", RS2),
]
for k, (label, f, fmt) in enumerate(closed):
    rr = 15 + k
    ss.cell(rr, 1, label).font = BLACK
    c = ss.cell(rr, 2, f)
    c.number_format, c.font, c.border = fmt, BLACK, BOX
ss["A26"] = ("Closed form for B is valid only while net import stays in slab 1 every year "
             "(true for the benchmark: max net import < 100 kWh/month) and Li = 12, N = 25.")
ss["A26"].font = Font(name=F, italic=True)
ss.column_dimensions["A"].width = 62
ss.column_dimensions["B"].width = 22
ss.column_dimensions["C"].width = 24
ss.column_dimensions["D"].width = 55

# ------------------------------------------------------------------ Rate sweep
rw = wb.create_sheet("RateSweep")
rw["A1"] = "LCC vs discount rate (Excel NPV of the nominal cash flows)"
rw["A1"].font = TITLE
for j, h in enumerate(["Discount rate", "LCC A (Rs)", "LCC B (Rs)", "Net savings B vs A (Rs)"], 1):
    c = rw.cell(3, j, h)
    c.font, c.fill, c.border = HEAD, HFILL, BOX
for k in range(14):
    rr = 4 + k
    rw.cell(rr, 1, 0.02 + 0.01 * k).number_format = "0%"
    rw.cell(rr, 1).font = BLUE
    rw.cell(rr, 2, f"=AltA_Grid!E5+NPV(A{rr},AltA_Grid!E6:E{last})").number_format = RS
    rw.cell(rr, 3, f"=AltB_PV!L5+NPV(A{rr},AltB_PV!L6:L{last})").number_format = RS
    rw.cell(rr, 4, f"=B{rr}-C{rr}").number_format = RS
    for j in range(1, 5):
        rw.cell(rr, j).border = BOX
rw["A19"] = "Break-even discount rate (IRR of B's extra investment):"
rw["A19"].font = BOLD
rw["A20"] = "Incremental cash flow (A - B) by year:"
for t in range(0, YEARS + 1):
    rw.cell(21 + t, 1, t)
    rw.cell(21 + t, 2, f"=AltA_Grid!E{5 + t}-AltB_PV!L{5 + t}").number_format = RS
rw["C19"] = f"=IRR(B21:B{21 + YEARS},0.3)"
rw["C19"].number_format = "0.00%"
rw["C19"].fill = GFILL
for col, wdt in zip("ABCD", (16, 20, 20, 24)):
    rw.column_dimensions[col].width = wdt

# ------------------------------------------------------------------ Validation
wv = wb.create_sheet("Validation")
wv["A1"] = "Validation: tool output vs this benchmark workbook"
wv["A1"].font = TITLE
wv["A2"] = ("Tool output column is PASTED from the Streamlit tool (lcca package v1.0.0) run with the "
            "default inputs; benchmark column is formula-linked to this workbook.")
for j, h in enumerate(["Quantity", "Benchmark (workbook)", "Tool output", "Difference", "Diff %", "Status"], 1):
    c = wv.cell(4, j, h)
    c.font, c.fill, c.border = HEAD, HFILL, BOX
vrows = [
    ("Monthly bill, grid only (Rs)", "=Tariff!B14", "bill_A_month"),
    ("Monthly bill, with PV year 1 (Rs)", "=Tariff!C14", "bill_B_month"),
    ("PV generation year 25 (kWh)", f"=AltB_PV!B{last}", "gen_25"),
    ("A: PV of electricity bills = LCC A", "=Summary!B4", "lcc_A"),
    ("B: PV of electricity bills", f"={PVB['Energy (bill)']}", "B_Energy"),
    ("B: PV system cost", f"={PVB['PV system']}", "B_Initial"),
    ("B: Subsidy", f"={PVB['Subsidy']}", "B_Subsidy"),
    ("B: PV of O&M", f"={PVB['O&M']}", "B_O&M"),
    ("B: PV of inverter replacements", f"={PVB['Inverter replacements']}", "B_Replacement"),
    ("B: PV of residual value", f"={PVB['Residual value']}", "B_Residual value"),
    ("LCC B", "=Summary!C4", "lcc_B"),
    ("Net savings B vs A", "=Summary!C7", "ns"),
    ("EUAC A", "=Summary!B6", "euac_A"),
    ("EUAC B", "=Summary!C6", "euac_B"),
    ("Break-even discount rate", "=RateSweep!C19", "breakeven"),
    ("LCC A at 4%", "=RateSweep!B6", "lcc_A_4"),
    ("LCC B at 12%", "=RateSweep!C14", "lcc_B_12"),
    ("CO2 avoided (t)", "=Summary!C11", "co2_avoided"),
    ("Discounted payback of B (yr)", "=Summary!C9", "dpb"),
]
for k, (label, f, key) in enumerate(vrows):
    rr = 5 + k
    wv.cell(rr, 1, label).font = BLACK
    c = wv.cell(rr, 2, f)
    c.font = GREEN
    tv = TOOL.get(key)
    c2 = wv.cell(rr, 3, tv)
    c2.font = BLUE
    wv.cell(rr, 4, f"=IF(C{rr}=\"\",\"\",C{rr}-B{rr})")
    wv.cell(rr, 5, f"=IF(OR(C{rr}=\"\",B{rr}=0),\"\",D{rr}/ABS(B{rr}))")
    wv.cell(rr, 6, f"=IF(C{rr}=\"\",\"\",IF(ABS(D{rr})<=MAX(0.01,ABS(B{rr})*0.000001),\"MATCH\",\"CHECK\"))")
    fmt = "0.0000%" if "rate" in label else ("#,##0.000" if "(t)" in label or "kWh" in label or "(yr)" in label else RS2)
    for j in (2, 3, 4):
        wv.cell(rr, j).number_format = fmt
    wv.cell(rr, 5).number_format = "0.0000%"
    for j in range(1, 7):
        wv.cell(rr, j).border = BOX
wv.cell(5 + len(vrows) - 1, 7, "Convention difference, not an error: workbook reports the first whole year-end with "
        "cumulative savings >= 0; the tool interpolates within the year (1.78 yr). See validation report D1.").font = Font(name=F, italic=True)
wv.column_dimensions["G"].width = 60
wv.cell(5 + len(vrows) + 1, 1, "Tolerance: |difference| <= max(Rs 0.01, 0.0001% of value).").font = Font(name=F, italic=True)
for col, wdt in zip("ABCDEF", (40, 22, 22, 16, 12, 10)):
    wv.column_dimensions[col].width = wdt

wb.save(OUT)
print("saved", OUT)
