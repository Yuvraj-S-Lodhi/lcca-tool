# LCCA Decision Tool

CE725 Construction Economics and Finance, Topic 6: Life Cycle Cost Analysis.

The tool compares building alternatives on their total present cost over an analysis period. That cost includes initial cost, O&M, energy, replacements and residual value, with discount-rate sensitivity, a tornado chart, break-even discount rate, payback and optional carbon cost.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

To deploy on Streamlit Community Cloud, push this folder to a GitHub repository, choose **New app**, and point it at `app.py`.

## Modes

* **Rooftop solar vs grid (benchmark).** Physical inputs (consumption, kWp, yield, degradation, capex, subsidy, inverter life) and the DISCOM slab tariff are converted into cash flows. The defaults are the team's validated benchmark case.
* **General LCCA.** Enter any number of alternatives as cost items:
  * `once`: a single amount in a given year.
  * `annual`: a yearly amount between a start and end year.
  * `capital`: an asset with a service life, automatic replacements and a residual value.
  * You can save a project to `.json` and load it back.

## Files

| Path | What it is |
|---|---|
| `app.py` | Streamlit user interface |
| `lcca/engine.py` | LCCA engine: cash flows, PV, LCC, EUAC, net savings, payback, break-even rate, tornado |
| `lcca/solar.py` | Slab tariff bill calculator, PM Surya Ghar subsidy rule, solar vs grid case builder, sourced defaults |
| `lcca/io.py` | JSON project save/load and Excel results export |
| `presets/` | Benchmark case and illustrative flooring case as project files |
| `tests/test_engine.py` | 26 automated checks against closed-form hand formulas |
| `tests/smoke_app.py` | Runs the whole UI script against a stub (no Streamlit needed) |

## Test

```bash
python -m unittest discover -s tests -v
python tests/smoke_app.py solar
python tests/smoke_app.py general
```

## Conventions

* Amounts are entered at base-year (today's) prices. The nominal cash flow in year t is `amount × (1+e)^t`.
* Cash flows are discounted at the nominal rate d, with end-of-year timing and year 0 as installation.
* Positive values are costs. Negative values are benefits, subsidies and residual value.
* The alternative with the lowest LCC is preferred.
