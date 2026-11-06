# Austria stock-driven config — review

Reviewed against `EU_stock_scenarios_v2` and the stock-driven checks in
`src/preprocessing/checks/MISO2_stock_driven_checks.py` (2026-10-22, second and third pass 2026-11-02).
Only open items are listed; fixed, answered and superseded items are in `Austria_config_fixed_issues.md`.
No file in this folder except the md files was changed; all fixes were applied to a copy.

## Status (2026-11-02, third pass, revised config with 100 end-uses and 5 carriers)

| | |
|---|---|
| Config as delivered | **Does not load.** Fails in this order on R1–R5 below. |
| Working copy with R1–R5 fixed | Loads with **all** optional groups, incl. energy feedback. All checks pass. |
| Run without feedback | Completes (147 s). Outputs: `model_output_data/Austria_stock_driven_2026-11-02b/`. |
| Run with feedback (`run_model(energy_feedback=True)`) | Runs, but **diverges**: hydro capacity 6.1e3 MW (2025) → 7.5e14 (2026) → 6e52 (2032), then overflow and NaN. Cause R6 + R7. |

Blocking (applied in the working copy):

| # | File | Problem | Fix in the copy |
|---|---|---|---|
| R1 | `MISO2_Energy_Operational` | Cover `No_Rows`/`No_Cols` formulas have no cached value (file saved without recalculation, C12); ODYM fails with `int(None)`. | Numbers written (57 / 77). |
# ? 
| R2 | Config, row `MISO2_Energy_Operational` | File is now `r,g,j,t`, but the config still says `rgjct` / `[0,1,2,3,4]`. | `rgjt` / `[0,1,2,3]`. |
# Done (failed to overwrite before)
| R3 | Properties, `Energy_carrier` | C7 regressed: after reducing the carriers, no carrier has `EnergyRecovery = TRUE`; exactly one must. | `electricity` TRUE. |
# Done (error due to order change)
| R4 | `MISO2_Function_Stock` | C9 regressed: `powerplants_geothermal` projection is 0 again. | Set to 1. |
# Done (needed to be added manually in post)
| R5 | `MISO2_Energy_Supply_Mix` | `energy_placeholder` is mapped to biomass, coal, gas, oil, but has no rows; the shares must sum to 1 per carrier (304 carrier-years fail). | Rows `energy_placeholder` × 4 carriers with share 1. |
Feedback diverges (data, not blocking the load):
# Done: Added placeholders for biomass, oil, gas, coal

| # | File | Problem |
|---|---|---|
| R6 | `MISO2_Energy_Operational` | Values are **totals per end-use**, not per function unit: `veh_car_icev` 1.56e8 GJ/yr oil ≈ all Austrian car fuel, `hha_fridge` 5.9e6 GJ/yr ≈ all fridges. The model multiplies by the function stock (`E_20_10 = intensity × SF_10`), so the stock is counted twice: E_20_10 electricity = 1.8e15 GJ/yr, ~10⁶ × Austria's total final energy (≈ 1.1e9 GJ/yr). Divide by the function stock of the base year (e.g. ≈ 34 GJ per car and year). |
# Done: Changed to per functional unit values (same for all years); absolutes removed
| R7 | `MISO2_Stock_Intensity_Capacity` | 1 MW per GJ/yr for all power plants (dummy). Realistic is 3e-5 to 3e-4 (see C10 in `Austria_config_fixed_issues.md`). With 1, the processing energy of building the plants needs more plants than it supplies, so the loop explodes even with correct R6. |
# Done: Changs dummies to lower valies (1e-5)

Not blocking, but probably not intended:

| # | File | Problem |
|---|---|---|
| R8 | `MISO2_MaterialIntensity_Functions` | Vehicles are named `vehic_*` (e.g. `vehic_bus_bev`), the classification `veh_*`. ODYM drops the rows silently, so all 28 vehicles have zero material. **This is probably what D2 was all along.** |
# Done: Changed to veh_
| R9 | `MISO2_Import/Export_p8_shares`, `Import_p8_shares_secondary` | Use `build_nr` and `build_rs_sfh`, which are not in the classification any more; rows are dropped. |
# Done: Updated stock names
| R10 | `MISO2_Lifetimes_interventions` | Refers to `build_nr`, `build_r_apb`, `build_r_mfh`, `build_r_sfh`; the loader keeps none of the interventions. |
# Done: Updated stock names
| R11 | `MISO2_Stock_Initialization` | No rows for the 8 `_tr`/`_tr_his` building end-uses (fine if they start at 0). Dataset_ID still `MISO2_Function_Initialization`, `Lifetimes_deviation` still `MISO2_Lifetimes`, `WasteRate_unrecov_p9` still `..._recov_p9` (N6 not applied). |
# ?
| R12 | Leftover files | `MISO2_Function_Initialization_v1.xlsx` and `MISO2_WasteRate_recov_p7_new.xlsx` are still there (N7 not applied); new duplicate `MISO2_Energy_Supply_Mix_v1 (1).xlsx` (identical). |
# Done: Removed
| R13 | Formulas in values | `Energy_Supply_Mix` (600 cells, `=$T10`), `MaterialIntensity_Functions` (804), `SB_Material!D22:D24` (`=TRUE()`, C15 back). Each breaks as soon as a script saves the file (C12); it happened twice while building the copy. |
# Done: Partly fixed: Replaced T10 with integers

Model questions from this pass:
- **Renovation.** `build_*_unr` shrinks while `build_*_tr` grows. The stock-driven model has no transfer between
  end-uses, so a renovated building is built as a new `_tr` cohort with its full material intensity, and the
  `_unr` stock that is no longer needed sleeps or is demolished (depending on `negative_inflow`). If `_tr` is meant
  as "same building, renovated", its material intensity should hold only the renovation material, and the `_unr`
  decline must not be counted as demolition waste. Needs a decision.
- **2025 front-loading.** Inflow F_9_10 is 217 Mt in 2025, 115 Mt in 2030; end-of-life outflow 206 → 91 Mt. Driven
  by infrastructure (`infra_local` 90 Mt in 2025, 37 Mt in 2050) with a nearly flat projection, i.e. much of the
  initial stock is in cohorts already past their mean lifetime. Check the cohort distribution of infrastructure in
  `Stock_Initialization` against `Lifetimes`.

Results without feedback (2026-11-02b), still with placeholders D6, D13, R8:

| | 2025 | 2030 | 2050 | 2100 |
|---|---|---|---|---|
| Material stock S_10 (Mt) | 2671 | 2786 | 3314 | 4940 |
| of which aggregates / concrete / asphalt | 1368 / 668 / 332 | 1450 / 716 / 353 | 1829 / 810 / 448 | 3005 / 956 / 745 |
| Domestic extraction F_0_1 (Mt/yr) | 159 | 10 | 20 | 19 |
| Inflow to stock F_9_10 | 217 | 115 | 90 | 152 |
| End-of-life outflow F_10_11 | 206 | 91 | 65 | 121 |
| Recycling / downcycling | 0 / 0 | 83 / 8 | 41 / 17 | 81 / 33 |
| Energy recovery F_13_20 | 0 | 40 | 17 | 33 |

The orders of magnitude are now plausible for Austria (≈ 300 t/cap stock). Domestic extraction drops from 159 to 10 Mt
because recycling starts in 2026 (one-year lag of the waste stock) and the flat recycling rate of 0.4 (D6) then
covers most of the demand. The process balance error rose to 6e-5 (tolerance 1e-5) at the larger flows, and the
long-term balance check now fails too; relative to flows of 1e8 t this is still rounding. The accuracy guard zeroes
only geothermal amounts (≤ 0.12 t).

Reproduce: session scratchpad `repro/prepare_copy_v2.sh <dir>` (freezes all formulas to cached values first, then
R1–R5), then `run_model.py <dir> <out> [--feedback]`.

## Open from earlier passes

Deferred by the config side:

| # | File | Problem |
|---|---|---|
| N5 | `MISO2_WasteRate_{recov,unrecov}_p7/p9` | All four files are 0 everywhere. The old p7 rates and the `concrete` values in `unrecov_p9` (D7/D8) are gone. Manufacturing and construction produce no waste. `# Ignore for now` |
| N8 | WasteRate p7/p9 | Year header mixed: `2024` is a number, `2025`–`2100` are text (C11). `# Ignore for now` |
| N10 | `MISO2_Lifetimes_interventions` | Contains material columns; the loader warns and ignores them (lifetimes are `rgt`). `# Ignore for now` |
| C11 | All files except `MaterialIntensity` and `Stock_Initialization` | Year headers stored as text (`'2024'`). ODYM converts them, but the EU files use numbers. `# No change for now` |
| C12 | All Cover sheets | `No_Rows`/`No_Cols` are Excel formulas. ODYM reads the cached value, so a file saved by a tool that does not recalculate (openpyxl, pandas) loses them and fails to load (R1 is such a case). Write numbers instead. `# No change for now` |
| C19 | Cover sheets | Dates in mixed formats (`05.05.2026` as text, datetimes elsewhere). `# No change for now` |

## Open data issues (values)

Most parameters are visibly placeholders: constant over time, and often equal across all materials or end-uses.

| # | Parameter | Observation | Why it matters / suggested action |
|---|---|---|---|
| D2 | `MISO2_MaterialIntensity_Functions`, vehicles | Zero material for all 28 `veh_*` end-uses. | Probably the naming mismatch R8. |
| D3 | `MISO2_Function_Stock`, vehicles | Stock halves from 2024 to 2025 (e.g. `veh_car_icev` 8.6e6 → 4.1e6). 2024 values look too high (Austria ≈ 5.1 M cars in total). | Huge drop forces sleeping stock, no new vehicles until ~2050. |
| D4 | `veh_motorcycles_bev` / `_icev` | 1.04 M BEV vs 17 k ICEV motorcycles. | Looks swapped. |
| D6 | `MISO2_Rate{Collection,Recycling,Downcycling,EnergyRecovery}` | Flat 0.99 / 0.4 / 0.2 / 0.2 for every material, end-use and year. | Energy recovery of 20 % of concrete, bricks, steel is physically meaningless. Needs material-specific rates. |
| D9 | `Aggr_recycling_split` vs `Split_material`, concrete | Recycling returns a different composition (0.9 aggregates / 0.1 cement) than the material split assigns. | Check consistency. |
| D13 | `MISO2_Energy_p7`, `_p9`, `_Intensity_sec` | Zero everywhere. | No manufacturing/construction energy, energy recovery yields no energy. |
| D14 | `MISO2_Energy_p1/p11/p13_*/p14` | Flat 0.1 for all materials. `Energy_p3` up to 7.4e4 per unit. | Placeholders; please state units (MJ/t?). |
| D15 | `MISO2_Lifetimes_deviation` | 0.2 everywhere; lifetimes constant over time. | Placeholder. |
| D16 | `MISO2_Import_p*_shares_secondary` | Flat 0.2. | Placeholder. |
| D17 | `MISO2_Stock_Initialization` | `powerplants_geothermal` empty. Power plants: whole stock in cohort 2024 (no retirement before ~2084). | Cohort distribution for power plants needed. |
| D18 | Trade p8 | Import/export p8 and secondary shares only set for 3 end-uses. | Intended? |
