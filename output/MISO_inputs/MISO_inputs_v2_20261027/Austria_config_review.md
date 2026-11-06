# Austria stock-driven config — review

Reviewed 2026-10-22 against `EU_stock_scenarios_v2` and the stock-driven checks in
`src/preprocessing/checks/MISO2_stock_driven_checks.py`. Second pass on the revised config 2026-11-02
(new findings N1–N10, answers to the `#` notes marked **2026-11-02**).

## Status (2026-11-02)

| | |
|---|---|
| Config as delivered | **Does not load.** Fails in this order on N1 (version typo), N2 (`Energy_Operational` aspect order), D5 (NaN power-plant intensities), C4 (lifetimes before 2024), D12 (unmapped energy carriers). |
| Working copy with these fixed | Loads, all stock-driven checks pass, **without energy feedback**. |
| Energy feedback | **Not runnable**: carrier classification (D12/N4) and `Stock_Intensity_Capacity` content (N3) need decisions, not placeholders. |
| Run | Completes (65 s, Austria, 2025–2100) on `src` as is. The old-scrap LP (M1) is solved by ee05a2e. Results are still dominated by placeholder data (see *Results*). |
| Outputs | `model_output_data/Austria_stock_driven_2026-11-02/` (csv, one file per flow/stock). |

Status 2026-10-22: did not load (C1–C9), ran in 79 s with a scratch patch for M1.

No file in this folder was changed. All fixes were applied to a copy; the list below is what needs to be
applied to the originals.

## New findings (2026-11-02)

Blocking:

| # | File | Problem | Applied in the working copy |
|---|---|---|---|
| N1 | Config, row `MISO2_Energy_p13_c` | Version is `s` instead of `v1`, so ODYM looks for `MISO2_Energy_p13_c_s.xlsx`. | Set to `v1`. |
# DONE: Fixed in config (typo)
| N2 | `MISO2_Energy_Operational` | Cover lists the row aspects as `Countries, End_use_sectors, Time, Energy_carrier` (r, g, **c, j**), the config says `rgjct` with order `[0,1,2,3,4]`. ODYM reads the cohort column as carrier and fails. Even with a matching order, the model has no cohort here (see answer to C10). | Cohort dropped (all values are 1, so nothing is lost), config back to `rgjt`. |
# DONE: Fixed order. 
| N3 | `MISO2_Stock_Intensity_Capacity` | The material column was removed, but the 4 material blocks are still there: 40 rows, every (end-use, carrier) key 4 times. ODYM silently keeps one of them. Content is still material intensity (`unit` sheet: `t/MW`, same numbers as `MaterialIntensity_Functions`), see answer to C10 for what is needed. | First block kept (only to test loading; feedback is removed anyway). |
# DONE: Redundancy removed
| N4 | Properties, `Energy_carrier` / `Energy_map` | With feedback registered, the check now fails on D12: `coal, oil, gas, biomass, waste, wind, pv, geothermal, hydro_ror, hydro_storage` have no supplying end-use. Except for `gas`, these are power-plant types, not carriers. `Energy_Operational` uses `gas` and `electricity`. | Feedback group removed from the copy's config. |
# DONE: Energy carriers reduced to actual carriers; dummy energy_placeholder for end_use introduced
| D5 | `MISO2_MaterialIntensity_Functions` | Now blocking: power plants still empty from cohort 1977, 4960 NaN; the NaN check raises. | Placeholder P3 (cohort 1976 carried forward). |
# DONE: 1978-2100 added
| C4 | `MISO2_Lifetimes`, `_deviation` | Still 2024–2100 only; check fails for 8804 end-use/cohort combinations with initial stock. | Placeholder P1. |
# DONE: 1900-2023 added

Non-blocking, but probably not intended:

| # | File | Problem |
|---|---|---|
| N5 | `MISO2_WasteRate_{recov,unrecov}_p7/p9` | Structure is fixed (C5), but **all four files are 0 everywhere**. The old p7 rates and the `concrete` values in `unrecov_p9` (D8) are gone, probably lost when the end-use dimension was added. Manufacturing and construction now produce no waste at all. |
# DONE: Ignore for now
| N6 | Dataset_IDs | `Stock_Initialization` still has ID `MISO2_Function_Initialization` (C1 renamed only the file), `Lifetimes_deviation` has `MISO2_Lifetimes`, `WasteRate_unrecov_p9` and `WasteRate_recov_p7_new` have `MISO2_WasteRate_recov_p9`. ODYM reads by file name, so this does not fail, but it is misleading. |
# DONE: Renamed
| N7 | Leftover files | `MISO2_Function_Initialization_v1.xlsx` (identical to `Stock_Initialization`) and `MISO2_WasteRate_recov_p7_new.xlsx` (all 0) are not registered. Remove them. |
# DONE: Removed
| N8 | WasteRate p7/p9 | Year header mixed: `2024` is a number, `2025`–`2100` are text (C11). |
# DONE: Ignore for now
| N9 | `RateCollection`, `RateRecycling`, `RateDowncycling` | C14 still open: `No_Cols` 78 instead of 77. |
# DONE: Fixed
| N10 | `MISO2_Lifetimes_interventions` | Contains material columns; the loader warns and ignores them (lifetimes are `rgt`). |
# DONE: Ignore for now

Status of the earlier data issues: D1–D4, D6, D13–D18 unchanged. D7/D8 superseded by N5. D10 resolved for now: all
trade shares are flat dummies (import 0.2, export 0.1, p2 import 0.3). D11/D12 see N3/N4.

Old-scrap allocation: the accuracy guard from ee05a2e zeroes capacities and demands below 0.02–0.06 t in 2027–2051
(tunnels, charging stations, power plants) and logs a warning per year. The amounts are negligible.

## Open config issues (format, structure, missing files)

Blocking (the config does not load or a check fails without them):

| # | File | Problem | Fix applied in the working copy |
|---|---|---|---|
DONE| C1 | `MISO2_Stock_Initialization_v1.xlsx` | Missing. The data ships as `MISO2_Function_Initialization_v1.xlsx` (Dataset_ID `MISO2_Function_Initialization`). | Renamed the file, set Dataset_ID to `MISO2_Stock_Initialization`. |
# Is Baseline material stock required in the model? Or only function stock (renamed Stock_Initialization)? If the latter, is conversion to material stock implemented in model?
> **2026-11-02:** Only the function stock by cohort. The material stock is computed in the model,
> `S_10[m,g,t,c] = SF_10[g,t,c] × MaterialIntensity[m,g,c]` (`runner.py:72`). Therefore the material intensity must
> cover every cohort with initial stock (see D5). Dataset_ID is still `MISO2_Function_Initialization` (N6).
DONE | C2 | Config, `MISO2_Import/Export_p2_shares` | Registered, but no files exist. | Removed both rows (p2 trade is optional). |
# Added dummy p2 Import/Export shares
DONE | C3 | Properties, `Global_parameters` | `SwitchTime = 2024`, but the initial stock is dated 2024 and contains cohort 2024. The model expects cohorts before the switch year, dated switch − 1. | `SwitchTime = 2025`. |
# SwitchType changed to 2025 (SwitchType =  year following baseyear (year that input data is reported for) - is this correct?)
> **2026-11-02:** Yes. `SwitchTime` is the first modelled year; the initial stock is the stock at the end of
> `SwitchTime − 1` and may only hold cohorts before `SwitchTime`. Stock reported for end of 2024 → `SwitchTime = 2025`.
| C4 | `MISO2_Lifetimes`, `MISO2_Lifetimes_deviation` | Cover only 2024–2100. Lifetimes are indexed by cohort, and every cohort with initial stock (1900–2024) needs one. | Cohorts 1900–2023 filled with the 2024 value (placeholder, see P1). |
> **2026-11-02:** Still open, blocking.
DONE | C5 | `MISO2_WasteRate_{recov,unrecov}_p7/p9` | Data are `r,m,t`, the config expects `r,m,g,t` (as in the EU config). | Same rate broadcast to all 81 end-uses (placeholder, see P2). |
# End-use added to WasteRate p7/p9
> **2026-11-02:** Loads, but all four files are 0 everywhere (N5).
DONE | C6 | `MISO2_Energy_p7`, `MISO2_Energy_p9` | Cover and value header say `SB_Material`, but the rows are end-uses (config `r,g,j,t`). | Relabelled to `End_use_sectors` / `End_use_sector`. |
# Cover and value headers harmonized
| C7 | Properties, `Energy_carrier` | `EnergyRecovery = TRUE` for all 11 carriers; exactly one must be TRUE (the carrier offset by energy recovery). | Only `electricity` TRUE (placeholder, see P5). |
# All set to FALSE but Electricity
DONE | C8 | `MISO2_Export_p12_shares` | Nickel export share is 2.09 in every year (shares must be ≤ 1). | Capped at 1 (placeholder). |
# All values replaced with dummies for now
DONE | C9 | `MISO2_Function_Stock` | `powerplants_geothermal` is 0 in all years, but the check requires a positive projection from the switch year on. | Set to 1e-6 (placeholder). Alternatively remove the end-use, or relax the check to allow zero (model question). |
# Geothermal added to 1 (dummy)
DONE | C10 | `MISO2_Stock_Intensity_Capacity`, `MISO2_Energy_Operational` | Do not match the registered index `r,g,j,t`: the first has an extra `SB_Material` dimension, the second an extra cohort dimension. See D11 for the content. | Energy feedback group (incl. `MISO2_Energy_Supply_Mix`) removed from the copy's config. |
# Material removd from MISO2_Stock_Intensity_Capacity (what does MISO2_Stock_Intensity_Capacity do if not intensity of capacity? what is the unit?)
# Cohort in MISO2_Energy_Operational has to remain since it's required for calculating energy operation. MISO2_Config changed to "rgjct" and "[0,1,2,3,4]" -> changes needed in Syst Def?

# Open questions:
## Energy_mix currently not being used? Add to syst def? stock apacity = E_demand * supply_mix * stock_intensity_capacity?
## What is MISO2_Stock_Intensity_Capacity used for? What is the unit?

> **2026-11-02, answers** (`energy.py`, *Implementation Architecture* §8):
>
> - **Supply mix is used**, exactly as you wrote it:
>   `stock_capacity[g,t] = Σ_j E_demand[j,t] × supply_share[g,j,t] × stock_intensity_capacity[g,j,t]`, and
>   `target[g,t+1] = max(projection[g,t+1], stock_capacity[g,t])` for every end-use in `Energy_map`.
>   `E_demand[j]` = operational energy + all processing energy (E_20_1 … E_20_14) − energy recovery.
> - **`Stock_Intensity_Capacity`** is the function stock of end-use g needed per unit of yearly demand of carrier j:
>   `[function unit of g] / [energy unit per year]`. Power plants are in MW (`Function_Stock` 2024: PV 7570 MW),
>   so for electricity in GJ/yr: `1 / (31 536 GJ/MW/yr × capacity factor)`, e.g. PV at CF 0.12 ≈ 2.6e-4 MW per
>   GJ/yr, hydro at CF 0.5 ≈ 6.3e-5. The energy unit must match the energy intensities (D14: units still open).
>   No material dimension: the material follows from the built capacity × `MaterialIntensity_Functions`.
> - **Cohort in `Energy_Operational`**: the model does not support it now. The system definition and `energy.py:69`
>   use `E_20_10[g,j,t] = operational_intensity[g,j,t] × Σ_c SF_10[g,t,c]`. Cohort-specific intensities
>   (`Σ_c intensity[g,j,c,t] × SF_10[g,t,c]`) are feasible because the stock is kept by cohort, but they are a change
>   to the system definition and the code. Questions for that: does the intensity really vary by year *and*
>   cohort (`rgjct`, 7236 rows already for 36 end-uses), or is a per-cohort value enough (`rgjc`)? Should sleeping
>   stock use operational energy? Until this is decided, an `rgjt` file is needed.
> - **Carriers (N4)**: every carrier must have a supplying end-use in `Energy_map`. `gas` has none. Either add
>   the corresponding supply end-uses, or the model needs a rule for carriers supplied from outside the system (model
>   question).

Non-blocking, but worth fixing:

| # | File | Problem |
|---|---|---|
| C11 | All files except `MaterialIntensity` and `Stock_Initialization` | Year headers stored as text (`'2024'`). ODYM converts them, but the EU files use numbers. |
# No change for now
| C12 | All Cover sheets | `No_Rows`/`No_Cols` are Excel formulas. ODYM reads the cached value, so a file saved by a tool that does not recalculate (openpyxl, pandas) loses them and fails to load. Write numbers instead. |
# No change for now (checked for inconsistencies)
| C13 | `MISO2_MaterialIntensity_Functions` | `No_Cols = COUNTA(values!1:1)-4` gives 200, but the file has 3 index columns and 201 cohorts, so **cohort 2100 is never read**. |
# Fixed
| C14 | Most `r,m,g,t` files (`Rate*`, `Import/Export_p8`, …) | `No_Cols` formula subtracts `COUNTA(A1:B1)` although there are 3 index columns, giving 78 instead of 77. Harmless (ODYM skips the empty column) but wrong. |
# Fixed in Import/Export P8, Import sec P8
> **2026-11-02:** Still 78 in `RateCollection`, `RateRecycling`, `RateDowncycling` (N9).
| C15 | Properties, `SB_Material` | `Aggregates`, `Split_P3`, `Split_P9` are formulas (`=FALSE()`), same fragility as C12. |
# Fixed to non_formulas
| C16 | `MISO2_MaterialIntensity_Functions`, `hha_freezer` rows | Values are formulas (same fragility as C12). |
# Fixed to non_formulas
| C17 | `MISO2_Function_Stock` | Extra `Source` column at the end of the value header (ignored by ODYM). |
# Fixed
| C18 | Config | Verbatim copy of the EU config (only the user name differs). Description and parameter descriptions of rows 92–96 are empty. |
# Some changes (see C10) + descriptions added
| C19 | Cover sheets | Dates in mixed formats (`05.05.2026` as text, datetimes elsewhere). |
# No change for now

`MISO2_Lifetimes_interventions_v1.xlsx` was not reviewed: interventions are not used by any production run.

## Open data issues (values)

Most parameters are visibly placeholders: constant over time, and often equal across all materials or end-uses.
Ordered by impact on results:

| # | Parameter | Observation | Why it matters / suggested action |
|---|---|---|---|
| D1 | `MISO2_Function_Stock`, buildings | 2024 projection is ~200× below the initial stock (e.g. `build_r_sfh` 8.8e5 vs 1.76e8 m²) and falls by a factor 3.4 to 2050. The initial stock (≈ 3.9e8 m² residential) is plausible for Austria, the projection looks like an annual flow (new construction?). | The model sees a stock 200× above target, so **no building is ever built again**; building stock only decays. Check unit and meaning of the projection. |
| D2 | `MISO2_MaterialIntensity_Functions`, vehicles | Zero for all 28 `veh_*` end-uses. | Vehicle stocks carry no material; vehicles contribute nothing to material flows. |
| D3 | `MISO2_Function_Stock`, vehicles | Stock halves from 2024 to 2025 (e.g. `veh_car_icev` 8.6e6 → 4.1e6). 2024 values look too high (Austria ≈ 5.1 M cars in total). | Huge drop forces sleeping stock, no new vehicles until ~2050. |
| D4 | `veh_motorcycles_bev` / `_icev` | 1.04 M BEV vs 17 k ICEV motorcycles. | Looks swapped. |
| D5 | `MISO2_MaterialIntensity_Functions`, power plants | Empty from cohort 1977 on (fill-right stopped at 1976). | Placeholder P3. Power-plant stock in 2024 is all in cohort 2024 anyway. |
| D6 | `MISO2_Rate{Collection,Recycling,Downcycling,EnergyRecovery}` | Flat 0.99 / 0.4 / 0.2 / 0.2 for every material, end-use and year. | Energy recovery of 20 % of concrete, bricks, steel is physically meaningless and gives ~10 Mt/yr energy recovery (see results). Needs material-specific rates. |
| D7 | `MISO2_WasteRate_recov_p9` | Zero everywhere. | No recoverable construction waste. Intended? |
| D8 | `MISO2_WasteRate_unrecov_p9` | Has values for `concrete`, which is split in P9 and therefore never uses them. | Move to the split parts (aggregates, cement). |
| D9 | `Aggr_recycling_split` vs `Split_material`, concrete | Recycling returns a different composition (0.9 aggregates / 0.1 cement) than the material split assigns. | Check consistency. |
| D10 | Trade shares | Shares above 1 in most trade files (export p4 up to 2.4, p6 up to 7.9, p8 up to 5.6, import p6 up to 3.6). Only p12 export is capped by the checks. | Plausible only if shares are relative to something other than domestic flow; please confirm the reference. |
| D11 | Energy feedback inputs | `Stock_Intensity_Capacity` holds power-plant **material** intensities (same numbers as `MaterialIntensity_Functions`, e.g. 65 t steel per coal unit). The model needs function stock (capacity) per unit of energy demand, `r,g,j,t`. `Energy_Operational` is 1 everywhere and per cohort; the model has no cohort dimension here. | Energy feedback cannot run. Needs: capacity per unit energy (e.g. MW per MWh/yr), and operational energy per function unit by end-use and carrier. |
| D12 | `Energy_map`, energy carriers | 11 carriers, but only `electricity` is mapped to power plants, and only electricity has energy intensities. | Either reduce the carrier classification or map/fill the others. Feedback would raise for unmapped carriers. |
| D13 | `MISO2_Energy_p7`, `_p9`, `_Intensity_sec` | Zero everywhere. | No manufacturing/construction energy, energy recovery yields no energy. |
| D14 | `MISO2_Energy_p1/p11/p13_*/p14` | Flat 0.1 for all materials (electricity only). `Energy_p3` up to 7.4e4 per unit. | Placeholders; please state units (MJ/t?). |
| D15 | `MISO2_Lifetimes_deviation` | 0.2 everywhere; lifetimes constant over time. | Placeholder. |
| D16 | `MISO2_Import_p*_shares_secondary` | Flat 0.2. | Placeholder. |
| D17 | `MISO2_Stock_Initialization` | `powerplants_geothermal` empty (consistent with C9). Power plants: whole stock in cohort 2024 (no retirement before ~2084). | Cohort distribution for power plants needed. |
| D18 | Trade p8 | Import/export p8 and secondary shares only set for 3 of 81 end-uses. | Intended? |

## Placeholders used for the first run

| # | Placeholder |
|---|---|
| P1 | Lifetimes and deviations of cohorts 1900–2023 = 2024 value. |
| P2 | WasteRates p7/p9 identical for all end-uses. |
| P3 | Power-plant material intensities carried forward from cohort 1976 to 1977–2100. |
| P4 | Nickel p12 export share 1.0, geothermal projection 1e-6. |
| P5 | Energy recovery offsets electricity. |
| P6 | No energy feedback. |

> **2026-11-02:** P4 is no longer needed (dummies are now in the data). P5 is in the data (C7). P2 not applied:
> the p7/p9 files are used as delivered (all 0, N5). P1, P3, P6 still applied in the copy.

## Model issue found during the run

**M1 – old-scrap max-min LP infeasible** (`src/model/core/runners/stock_driven/maxmin.py`). With 81 end-uses,
capacities and demands span 1e-13 to 2e5. After scaling, values of ~1e-8 are below the HiGHS feasibility tolerance
(1e-7), and the freeze constraints (`levels × weights × (1 − 1e-9)`) plus the stage-2 equality
`target_sums @ x == received` become infeasible. The run used a scratch patch (not in `src`): an absolute slack of
1e-7 (scaled units) in `_level_constraints`, and the stage-2 equality replaced by `target_sums @ x ≥ received − 1e-7`.
On the failing case, capacity and demand bounds then hold to 1e-12 and no flow uses a denied pair. Needs a proper
fix and a test in `src`.

> **2026-11-02:** Resolved by ee05a2e (accuracy guard). The run completes on `src` without a patch.

Minor: some flows (`S_13`, `F_11_14`, `F_13_*`, `F_14_0`, cement, 2065–2068) are negative at −1e-13, and the largest
process balance error is 1.1e-5 against a tolerance of 1e-5 on flows of ~1e7 t. Both are rounding noise; the
absolute balance tolerance is tight for country-level runs.

> **2026-11-02:** Unchanged: balance error 1.13e-5 vs 1e-5, negatives of −5e-13 in cement (`S_13`, `F_11_14`,
> `F_13_14`, `F_13_20`, `F_14_0`, `F_20_11`).

## Results (2026-11-02 run, working copy, no energy feedback, placeholders P1–P6)

These are **not interpretable** as Austrian results while D1–D3 and D6 are open; they show that the chain runs.
Outputs: `model_output_data/Austria_stock_driven_2026-11-02/`. Values from 2026-10-22 in brackets where they differ.

Material stock S_10 (Mt), unchanged:

| | 2025 | 2030 | 2050 | 2100 |
|---|---|---|---|---|
| concrete | 515 | 483 | 358 | 136 |
| bricks | 163 | 138 | 75 | 5 |
| aggregates | 49 | 45 | 35 | 22 |
| iron_steel | 26.6 | 25.7 | 21.0 | 6.4 |
| gypsum | 7.4 | 6.7 | 4.6 | 0.4 |
| wood | 6.2 | 5.3 | 3.2 | 0.3 |
| total | ≈ 773 | ≈ 709 | ≈ 502 | ≈ 176 |

Main flows (Mt/yr):

| | 2025 | 2030 | 2050 | 2100 |
|---|---|---|---|---|
| Domestic extraction F_0_1 | 0.96 (1.61) | 0.05 (0.10) | 0.06 (0.14) | 0.20 (0.35) |
| Inflow to stock F_9_10 | 1.29 | 0.65 | 0.84 | 2.71 |
| End-of-life outflow F_10_11 | 15.3 | 12.7 | 10.4 | 4.8 |
| Recycling F_13_3_recyc | 0 | 0.53 (0.68) | 0.69 (0.86) | 2.22 (2.79) |
| Energy recovery F_13_20 | 0 | 9.8 (8.8) | 10.9 (9.7) | 4.4 (3.3) |
| Final waste F_14_0 | 0.18 | 10.0 (9.0) | 11.1 (9.9) | 4.7 (3.5) |
| Waste stock S_13 | 16.8 (15.3) | 52.6 (47.2) | 54.0 (48.1) | 20.9 (15.9) |

The stock side is unchanged because function stock, intensities and lifetimes did not change. The flow
differences come from the dummy trade shares (D10: import 0.2 / export 0.1 instead of shares > 1) and the zero p7/p9
waste rates (N5).

Reading:
- The stock shrinks by ~75 % to 2100 because buildings are never rebuilt (D1) and vehicles carry no material (D2).
- Inflows are ~1 Mt/yr and almost fully covered by recycling from 2026 on, so domestic extraction is close to zero.
  For Austria, expect tens of Mt/yr of construction minerals alone.
- About 10 Mt/yr of mostly mineral waste goes to energy recovery because of the flat 0.2 rate (D6). It yields no
  energy (D13).
- Replacement of appliances and infrastructure works as expected: inflows equal survival losses where the projection
  is close to the stock.

## To reproduce

The 2026-10-22 scripts are gone (session scratchpad). The 2026-11-02 scripts are in the session scratchpad
(`repro/`), not in the repo. `prepare_copy.sh` copies this folder and applies, in order:
- `fix_config_version.py`: N1.
- `fix_energy_feedback.py`: N2, N3 (`rgjt`, cohort dropped, first capacity block).
- `fill_powerplant_intensity.py`: D5 / P3.
- `backfill_lifetimes.py`: C4 / P1.
- `drop_feedback.py`: removes the 3 feedback parameters from the config (N4 / P6).

It then runs `run_model.py` (load, `split_config`, `MISO2Model.run_model`, csv output) and `summarize.py`
(tables above). `scan.py` checks every parameter file for Dataset_ID, Cover row/column counts, text years and
formulas.
