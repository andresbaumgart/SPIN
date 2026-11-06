# Austria stock-driven config — fixed issues log

Items removed from `Austria_config_review.md` once fixed, answered or superseded. Newest first. Original problem
text kept; `#` lines are the notes from the config side.

## 2026-11-02, third pass (revised config with 100 end-uses and 5 carriers)

Fixed, confirmed in the data:

| # | File | Problem | Resolution |
|---|---|---|---|
| N1 | Config, row `MISO2_Energy_p13_c` | Version `s` instead of `v1`, ODYM looked for `MISO2_Energy_p13_c_s.xlsx`. | `# DONE: Fixed in config (typo)` |
| N2 | `MISO2_Energy_Operational` | Cover listed the row aspects as r, g, **c, j**, config said `rgjct`; the model has no cohort here. | File is now `r,g,j,t`. The config row still says `rgjct`, open as **R2**. |
| N3 | `MISO2_Stock_Intensity_Capacity` | Material column removed, but the 4 material blocks were still there (every key 4 times). | `# DONE: Redundancy removed`. Content is a dummy 1, open as **R7**. |
| N4, D12 | Properties, `Energy_carrier` / `Energy_map` | Carriers `coal, oil, gas, biomass, waste, wind, pv, geothermal, hydro_*` had no supplying end-use; most were power-plant types, not carriers. | `# DONE: Energy carriers reduced to actual carriers; dummy energy_placeholder for end_use introduced`. Follow-ups open as **R3**, **R5**. |
| D5 | `MISO2_MaterialIntensity_Functions` | Power plants empty from cohort 1977, 4960 NaN. | `# DONE: 1978-2100 added` |
| C4 | `MISO2_Lifetimes`, `_deviation` | Only 2024–2100; every cohort with initial stock needs a lifetime. | `# DONE: 1900-2023 added` |
| N9, C14 | `RateCollection`, `RateRecycling`, `RateDowncycling` (and other `r,m,g,t` files) | `No_Cols` 78 instead of 77 (formula subtracted 2 instead of 3 index columns). | Fixed. |
| C13 | `MISO2_MaterialIntensity_Functions` | `No_Cols` gave 200, so cohort 2100 was never read. | Fixed. |
| D1 | `MISO2_Function_Stock`, buildings | 2024 projection ~200× below the initial stock (looked like an annual flow), so no building was ever rebuilt. | Projections now continue the initial stock (`_unr` declines, `_tr` / `_tr_his` grow from 0). |

Superseded (tracked under a new number in the review):

| # | Was | Now |
|---|---|---|
| C7 | `EnergyRecovery = TRUE` for all 11 carriers. `# All set to FALSE but Electricity` | Regressed after the carrier reduction: no carrier is TRUE → **R3**. |
| C9 | `powerplants_geothermal` projection 0. `# Geothermal added to 1 (dummy)` | Regressed, 0 again → **R4**. |
| C15, C16 | Formulas in `SB_Material` (`=FALSE()`) and `MaterialIntensity_Functions` (`hha_freezer`). `# Fixed to non_formulas` | Formulas are back (`=TRUE()`, 804 cells) → **R13**. |
| N6 | Dataset_IDs `MISO2_Function_Initialization`, `MISO2_Lifetimes`, `MISO2_WasteRate_recov_p9` in the wrong files. `# DONE: Renamed` | Not applied → **R11**. |
| N7 | Leftover `MISO2_Function_Initialization_v1.xlsx`, `MISO2_WasteRate_recov_p7_new.xlsx`. `# DONE: Removed` | Still there → **R12**. |
| D11 | `Stock_Intensity_Capacity` held material intensities; `Energy_Operational` was 1 everywhere and per cohort. | Structure fixed (N2, N3); content → **R6**, **R7**. |
| P1–P6 | Placeholders of the second-pass run (see below). | Not needed any more; the third-pass copy applies only R1–R5. |

## 2026-11-02, second pass

Fixed in the config (from the 2026-10-22 review):

| # | File | Problem | Resolution |
|---|---|---|---|
| C1 | `MISO2_Stock_Initialization_v1.xlsx` | Missing, data shipped as `MISO2_Function_Initialization_v1.xlsx`. | File renamed. Dataset_ID follow-up N6 → R11. |
| C2 | Config, `MISO2_Import/Export_p2_shares` | Registered, but no files. | `# Added dummy p2 Import/Export shares` |
| C3 | Properties, `Global_parameters` | `SwitchTime = 2024`, but the initial stock is dated 2024 and contains cohort 2024. | `SwitchTime = 2025`. |
| C5 | `MISO2_WasteRate_{recov,unrecov}_p7/p9` | Data `r,m,t`, config expects `r,m,g,t`. | `# End-use added to WasteRate p7/p9`. All values 0 → N5 (open). |
| C6 | `MISO2_Energy_p7`, `_p9` | Cover and header said `SB_Material`, rows are end-uses. | `# Cover and value headers harmonized` |
| C8 | `MISO2_Export_p12_shares` | Nickel export share 2.09. | `# All values replaced with dummies for now` |
| C10 | `MISO2_Stock_Intensity_Capacity`, `MISO2_Energy_Operational` | Extra `SB_Material` and cohort dimensions vs. `r,g,j,t`. | Material removed (N3), cohort removed (N2). |
| C17 | `MISO2_Function_Stock` | Extra `Source` column. | `# Fixed` |
| C18 | Config | Verbatim copy of the EU config, descriptions of rows 92–96 empty. | `# Some changes (see C10) + descriptions added` |
| D10 | Trade shares | Shares above 1 in most trade files. | Resolved for now: flat dummies (import 0.2, export 0.1, p2 import 0.3). |
| M1 | `maxmin.py` | Old-scrap max-min LP infeasible (values below the HiGHS tolerance). | Fixed in `src` by ee05a2e (accuracy guard). |

Superseded: D7, D8 (WasteRate p9 values) → N5 (open).

Answers given (2026-11-02):

- **C1, baseline material stock.** Only the function stock by cohort is needed. The material stock is computed in
  the model, `S_10[m,g,t,c] = SF_10[g,t,c] × MaterialIntensity[m,g,c]` (`runner.py:72`), so the material
  intensity must cover every cohort with initial stock.
- **C3, SwitchTime.** `SwitchTime` is the first modelled year; the initial stock is the stock at the end of
  `SwitchTime − 1` and may only hold cohorts before `SwitchTime`. Stock reported for end of 2024 → `SwitchTime = 2025`.
- **C10, energy feedback** (`energy.py`, *Implementation Architecture* §8):
  - **Supply mix is used**:
    `stock_capacity[g,t] = Σ_j E_demand[j,t] × supply_share[g,j,t] × stock_intensity_capacity[g,j,t]`, and
    `target[g,t+1] = max(projection[g,t+1], stock_capacity[g,t])` for every end-use in `Energy_map`.
    `E_demand[j]` = operational energy + all processing energy (E_20_1 … E_20_14) − energy recovery.
  - **`Stock_Intensity_Capacity`** is the function stock of end-use g needed per unit of yearly demand of carrier j:
    `[function unit of g] / [energy unit per year]`. Power plants are in MW, so for electricity in GJ/yr:
    `1 / (31 536 GJ/MW/yr × capacity factor)`, e.g. PV at CF 0.12 ≈ 2.6e-4 MW per GJ/yr, hydro at CF 0.5 ≈ 6.3e-5.
    No material dimension: the material follows from the built capacity × `MaterialIntensity_Functions`.
  - **Cohort in `Energy_Operational`**: not supported. `E_20_10[g,j,t] = operational_intensity[g,j,t] × Σ_c SF_10[g,t,c]`
    (`energy.py:69`). Cohort-specific intensities would be a change to the system definition and the code.
    Resolved by going back to `rgjt`.
  - **Carriers**: every carrier must have a supplying end-use in `Energy_map`. Resolved by N4.

Placeholders used for the second-pass run (working copy only):

| # | Placeholder |
|---|---|
| P1 | Lifetimes and deviations of cohorts 1900–2023 = 2024 value. |
| P2 | WasteRates p7/p9 identical for all end-uses (not applied on 2026-11-02, files used as delivered). |
| P3 | Power-plant material intensities carried forward from cohort 1976 to 1977–2100. |
| P4 | Nickel p12 export share 1.0, geothermal projection 1e-6. |
| P5 | Energy recovery offsets electricity. |
| P6 | No energy feedback. |

Status of the second pass: did not load (N1, N2, D5, C4, D12). The working copy loaded without energy feedback and
ran in 65 s on `src` as is; outputs in `model_output_data/Austria_stock_driven_2026-11-02/`. Largest process
balance error 1.13e-5 vs a tolerance of 1e-5, negatives of −5e-13 in cement (rounding).

Results of the second-pass run (not interpretable, D1–D3 and D6 open at the time):

| Material stock S_10 (Mt) | 2025 | 2030 | 2050 | 2100 |
|---|---|---|---|---|
| total | ≈ 773 | ≈ 709 | ≈ 502 | ≈ 176 |
| concrete | 515 | 483 | 358 | 136 |
| bricks | 163 | 138 | 75 | 5 |

| Mt/yr | 2025 | 2030 | 2050 | 2100 |
|---|---|---|---|---|
| Domestic extraction F_0_1 | 0.96 | 0.05 | 0.06 | 0.20 |
| Inflow to stock F_9_10 | 1.29 | 0.65 | 0.84 | 2.71 |
| End-of-life outflow F_10_11 | 15.3 | 12.7 | 10.4 | 4.8 |
| Energy recovery F_13_20 | 0 | 9.8 | 10.9 | 4.4 |

## 2026-10-22, first review

Did not load (C1–C9). Ran in 79 s with a scratch patch for M1 (since fixed by ee05a2e).
