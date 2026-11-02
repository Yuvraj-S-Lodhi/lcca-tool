"""Figures for the reports and presentation, generated from the validated engine."""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lcca import (Alternative, CostItem, SolarCase, breakeven_discount_rate,  # noqa: E402
                  build_alternatives, cashflow_table, lcc_vs_discount_rate, tornado_parameters,
                  yearly_totals)

OUT = sys.argv[1] if len(sys.argv) > 1 else "figures"
os.makedirs(OUT, exist_ok=True)
S1, S2 = "#2a5098", "#3194da"
TXT, TXT2, GRID, SURF = "#1f3a6e", "#5b6b86", "#d5deeb", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
                     "axes.labelcolor": TXT2, "xtick.color": TXT2, "ytick.color": TXT2,
                     "text.color": TXT, "axes.facecolor": SURF, "figure.facecolor": SURF,
                     "axes.spines.top": False, "axes.spines.right": False})


def lakh(x, _=None):
    sign = "−" if x < 0 else ""
    x = abs(x)
    return f"{sign}₹{x / 1e5:.1f}L" if x >= 1e5 else f"{sign}₹{x / 1e3:.0f}k"


def thousands(x, _=None):
    return f"{'−' if x < 0 else ''}₹{abs(x) / 1e3:.0f}k"


def finish(ax, title, sub=None):
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=TXT, pad=24)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=TXT2, fontsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


case = SolarCase()
a, b, et = build_alternatives(case)
N, d = case.analysis_years, case.discount_rate

# 1. PV by cost category -------------------------------------------------------------
cats = ["Energy", "Initial", "Subsidy", "O&M", "Replacement", "Residual value"]
va = cashflow_table(a, N, d).groupby("category")["present_value"].sum()
vb = cashflow_table(b, N, d).groupby("category")["present_value"].sum()
fig, ax = plt.subplots(figsize=(10, 5.2))
y = range(len(cats))
h = 0.36
ax.barh([i - h / 2 - 0.01 for i in y], [va.get(c, 0) for c in cats], h, color=S1, label="A: Grid only")
ax.barh([i + h / 2 + 0.01 for i in y], [vb.get(c, 0) for c in cats], h, color=S2, label="B: Rooftop PV + grid")
for i, c in enumerate(cats):
    for off, v in ((-h / 2, va.get(c, 0)), (h / 2, vb.get(c, 0))):
        if v:
            ax.text(v + (8000 if v > 0 else -8000), i + off, lakh(v), va="center",
                    ha="left" if v > 0 else "right", fontsize=9, color=TXT2)
ax.set_yticks(list(y), cats)
ax.invert_yaxis()
ax.axvline(0, color=TXT2, linewidth=0.8)
ax.xaxis.set_major_formatter(FuncFormatter(lakh))
ax.set_xlim(-120000, 800000)
ax.grid(axis="x", color=GRID)
ax.set_axisbelow(True)
ax.legend(frameon=False, loc="lower right")
ax.set_title("Present value by cost category", loc="left", fontsize=14, fontweight="bold", pad=24)
ax.text(0, 1.02, f"LCC A = {lakh(va.sum())}   ·   LCC B = {lakh(vb.sum())}   ·   25 yr, 7% nominal",
        transform=ax.transAxes, color=TXT2, fontsize=10)
fig.tight_layout()
fig.savefig(f"{OUT}/fig1_pv_by_category.png", dpi=200)
plt.close(fig)

# 2. Cumulative PV ---------------------------------------------------------------------
ca = yearly_totals(a, N, d)["cumulative_pv"]
cb = yearly_totals(b, N, d)["cumulative_pv"]
fig, ax = plt.subplots(figsize=(10, 5.2))
ax.plot(ca.index, ca.values, color=S1, linewidth=2)
ax.plot(cb.index, cb.values, color=S2, linewidth=2)
ax.text(N + 0.3, ca.iloc[-1], "A: Grid only", color=TXT, va="center", fontsize=10)
ax.text(N + 0.3, cb.iloc[-1], "B: PV + grid", color=TXT, va="center", fontsize=10)
ax.annotate("Discounted payback ≈ 1.8 yr", xy=(1.78, 74000), xytext=(3.4, 12000),
            arrowprops=dict(arrowstyle="-", color=TXT2, linewidth=0.8), color=TXT2, fontsize=10)
ax.yaxis.set_major_formatter(FuncFormatter(lakh))
ax.set_xlabel("Year")
ax.set_xlim(0, N + 4)
finish(ax, "Cumulative present value of costs", "Lines cross where PV pays back its net investment")
fig.tight_layout()
fig.savefig(f"{OUT}/fig2_cumulative_pv.png", dpi=200)
plt.close(fig)

# 3. Discount-rate sweep ---------------------------------------------------------------
rates = [0.02 + 0.0025 * k for k in range(53)]
sw = lcc_vs_discount_rate([a, b], N, rates)
fig, ax = plt.subplots(figsize=(10, 5.2))
ax.plot(sw.discount_rate * 100, sw[a.name], color=S1, linewidth=2)
ax.plot(sw.discount_rate * 100, sw[b.name], color=S2, linewidth=2)
ax.text(15.2, sw[a.name].iloc[-1], "A: Grid only", va="center", fontsize=10)
ax.text(15.2, sw[b.name].iloc[-1], "B: PV + grid", va="center", fontsize=10)
ax.axvline(7, color=TXT2, linewidth=0.8, linestyle=(0, (3, 3)))
ax.text(7.15, ax.get_ylim()[1] * 0.95, "base case 7%", color=TXT2, fontsize=9)
ax.yaxis.set_major_formatter(FuncFormatter(lakh))
ax.set_xlabel("Nominal discount rate (%)")
ax.set_xlim(2, 17.5)
finish(ax, "Life cycle cost vs discount rate",
       f"B stays cheaper at every rate up to the break-even of {breakeven_discount_rate(a, b, N)[0] * 100:.1f}%")
fig.tight_layout()
fig.savefig(f"{OUT}/fig3_rate_sweep.png", dpi=200)
plt.close(fig)

# 4. Tornado --------------------------------------------------------------------------
tor = tornado_parameters(case)
ref = tor.attrs["reference"]
fig, ax = plt.subplots(figsize=(10, 5.6))
yy = range(len(tor))
ax.barh(list(yy), tor["ns_at_low"] - ref, 0.62, color=S1, label="Input at low value")
ax.barh(list(yy), tor["ns_at_high"] - ref, 0.62, color=S2, label="Input at high value")
ax.set_yticks(list(yy), tor["parameter"])
ax.invert_yaxis()
ax.axvline(0, color=TXT2, linewidth=0.8)
ax.xaxis.set_major_formatter(FuncFormatter(thousands))
ax.grid(axis="x", color=GRID)
ax.set_axisbelow(True)
ax.legend(frameon=False, loc="lower right")
ax.set_title("What moves the net savings of PV over grid?", loc="left", fontsize=14,
             fontweight="bold", pad=24)
ax.text(0, 1.02, f"Change from base net savings of {lakh(ref)}; no input in its range flips the decision",
        transform=ax.transAxes, color=TXT2, fontsize=10)
fig.tight_layout()
fig.savefig(f"{OUT}/fig4_tornado.png", dpi=200)
plt.close(fig)
tor.to_csv(f"{OUT}/tornado.csv", index=False)

# 5. Flooring crossover ---------------------------------------------------------------
x = Alternative("Vitrified tile", [CostItem("Tile", "capital", 150000, life=20),
                                   CostItem("M", "annual", 2000)])
yv = Alternative("Epoxy coating", [CostItem("Epoxy", "capital", 90000, life=8),
                                   CostItem("M", "annual", 3000)])
rates = [0.02 + 0.0025 * k for k in range(53)]
sw = lcc_vs_discount_rate([x, yv], 30, rates)
be = breakeven_discount_rate(x, yv, 30)[0]
fig, ax = plt.subplots(figsize=(10, 5.2))
ax.plot(sw.discount_rate * 100, sw[x.name], color=S1, linewidth=2)
ax.plot(sw.discount_rate * 100, sw[yv.name], color=S2, linewidth=2)
ax.text(15.2, sw[x.name].iloc[-1], "Tile", va="center", fontsize=10)
ax.text(15.2, sw[yv.name].iloc[-1], "Epoxy", va="center", fontsize=10)
ax.axvline(be * 100, color=TXT2, linewidth=0.8, linestyle=(0, (3, 3)))
ax.text(be * 100 + 0.15, ax.get_ylim()[1] * 0.93, f"ranking flips at {be * 100:.1f}%", color=TXT2, fontsize=9)
ax.yaxis.set_major_formatter(FuncFormatter(lakh))
ax.set_xlabel("Nominal discount rate (%)")
ax.set_xlim(2, 16.5)
ax.yaxis.set_major_locator(MultipleLocator(50000))
finish(ax, "Illustrative case: flooring LCC vs discount rate",
       "Tile (dearer, 20-yr life) wins below the break-even rate; epoxy (cheaper, 8-yr life) above it")
fig.tight_layout()
fig.savefig(f"{OUT}/fig5_flooring_crossover.png", dpi=200)
plt.close(fig)
print("figures written to", OUT)
