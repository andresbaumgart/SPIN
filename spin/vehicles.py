"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Traffic and vehicle fleet projections

1. Traffic (pkm / tkm) per mode from the last data year onwards:
   base x (pop / pop_base) x (GDP / GDP_base) ^ elasticity, with the GDP
   elasticity estimated from history; cycling and walking follow population.
   Demand reduction scales all modes.
2. Modal shift: car pkm -> rail / subway-tram, road tkm -> rail tkm.
3. Vehicle-km = traffic (pkm or tkm) / occupancy (pkm per vkm) or load factor (tkm per vkm),
   data_vehicle_occupancy.xlsx x occupancy measures. Vehicles grow with their vehicle-km, starting from
   the latest observed fleet: vehicles(t) = fleet(y0) x vkm(t) / vkm(y0) / mileage factor(t)
   (km per vehicle constant unless a mileage measure changes it). With constant occupancy and mileage this
   equals growth with traffic. Vehicle-km per traffic mode also drive the infrastructure.
4. Fleet split by fuel with base-year shares; electrification moves fossil and
   hybrid shares to electric.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.stats import linregress
from .mappings import (ACTIVE_MODES, MODE_OCCUPANCY_TYPE, DEFAULT_ELASTICITY, ELECTRIFICATION_GROUPS, MAX_ABS_ELASTICITY, PKM_SHIFT_FROM, PKM_SHIFT_TO, TKM_SHIFT_FROM, TKM_SHIFT_TO, TRAFFIC_EXCLUDED, VEHICLE_TO_TRAFFIC)
from .scenarios import MobilityParams, phase_in_share

@dataclass
class VehicleResult:
    traffic:    dict          # Traffic type -> Series(year -> billion pkm/tkm), history + projection
    vehicles:   pd.DataFrame  # Type_lv2, Year, Value
    by_fuel:    pd.DataFrame  # Type_lv2, Fuel_type, Year, Value
    vkm:        dict = None   # Traffic mode -> Series(year -> billion vkm; modes without occupancy: billion pkm/tkm)

def _history(traffic: pd.DataFrame, ttype) -> pd.Series:
    d = traffic[(traffic['Type_lv2'] == ttype) & traffic['Value'].notna() & (traffic['Value'] > 0)]
    return d.groupby('Year')['Value'].sum()

def gdp_elasticity(hist: pd.Series, gdp: pd.Series, pop: pd.Series) -> float:
    """Slope of log(traffic per capita) on log(GDP per capita)."""
    if len(hist) < 3:
        return DEFAULT_ELASTICITY
    nearest = lambda s, y: s.get(y, s.iloc[np.abs(s.index - y).argmin()])  # noqa: E731
    g = np.array([nearest(gdp, y) for y in hist.index])
    p = np.array([nearest(pop, y) for y in hist.index])
    try:
        slope = linregress(np.log(g), np.log(hist.values / p))[0]
    except Exception:
        return DEFAULT_ELASTICITY
    return slope if abs(slope) < MAX_ABS_ELASTICITY else DEFAULT_ELASTICITY

def project_traffic(traffic, gdp, pop, params: MobilityParams, base_year=2024, end_year=2100) -> dict:
    out = {}
    for ttype in traffic['Type_lv2'].unique():
        if ttype in TRAFFIC_EXCLUDED:
            continue
        hist = _history(traffic, ttype)
        active = ttype in ACTIVE_MODES
        if hist.empty or (not active and len(hist) < 3):
            continue
        y0, v0 = hist.index[-1], hist.iloc[-1]
        e = 0.0 if active else gdp_elasticity(hist, gdp, pop)
        proj = {}
        for y in range(y0 + 1, end_year + 1):
            if y not in pop.index or (not active and y not in gdp.index):
                continue
            v = v0 * (pop[y] / pop.get(y0, pop.iloc[0]))
            if not active:
                v = v * (gdp[y] / gdp.get(y0, gdp.iloc[0])) ** e
            proj[y] = v * params.demand_factor(y)
        out[ttype] = pd.concat([hist, pd.Series(proj, dtype=float)])

    def shift(source, targets, timed):
        if timed is None or source not in out:
            return
        targets = [t for t in targets if t in out]
        if not targets:
            return
        weights = {t: out[t].get(base_year, 0) for t in targets}
        total = sum(weights.values())
        moved = pd.Series({y: v * phase_in_share(y, timed.start, timed.end, timed.value)
                           for y, v in out[source].items() if y > base_year})
        out[source] = out[source].sub(moved, fill_value=0)
        for t in targets:
            w = weights[t] / total if total > 0 else 1 / len(targets)
            out[t] = out[t].add(moved * w, fill_value=0)

    shift(PKM_SHIFT_FROM, PKM_SHIFT_TO, params.pkm_shift)
    shift(TKM_SHIFT_FROM, TKM_SHIFT_TO, params.tkm_shift)
    return out

def project_fleet(fleet: pd.DataFrame, traffic: dict, base_year=2024, end_year=2100, occupancy: dict | None = None,
                  params: MobilityParams | None = None) -> pd.DataFrame:
    """Each vehicle type grows with its vehicle-km (traffic / occupancy) from its latest observed year."""
    years = range(base_year, end_year + 1)
    occupancy = occupancy or {}

    def occ(vtype, y):
        base = occupancy[vtype].get(y, occupancy[vtype].iloc[-1]) if vtype in occupancy else 1.0
        return base * (params.occupancy_factor(vtype, y) if params else 1.0)

    rows = []
    for vtype, ttype in VEHICLE_TO_TRAFFIC.items():
        obs = fleet[(fleet['Type_lv2'] == vtype) & (fleet['Value'] > 0)].groupby('Year_from')['Value'].sum()
        t = traffic.get(ttype)
        if obs.empty or t is None:
            continue
        common = [y for y in obs.index if y in t.index]
        if not common:
            continue
        y0 = max(common)
        vkm0 = t[y0] / occ(vtype, y0)
        for y in years:
            if y in t.index:
                mileage = params.mileage_factor(vtype, y) / params.mileage_factor(vtype, y0) if params else 1.0
                rows.append({'Type_lv2': vtype, 'Year': y, 'Value': obs[y0] * (t[y] / occ(vtype, y)) / vkm0 / mileage})
    return pd.DataFrame(rows)

def vehicle_km(traffic: dict, occupancy: dict | None, params: MobilityParams | None = None) -> dict:
    """Vehicle-km per traffic mode = traffic / occupancy of the mode's vehicle type (x occupancy measures)."""
    occupancy = occupancy or {}
    out = {}
    for mode, t in traffic.items():
        vtype = MODE_OCCUPANCY_TYPE.get(mode)
        if vtype not in occupancy:
            out[mode] = t
            continue
        occ = occupancy[vtype]
        f = [occ.get(y, occ.iloc[-1]) * (params.occupancy_factor(vtype, y) if params else 1.0) for y in t.index]
        out[mode] = t / pd.Series(f, index=t.index)
    return out

def split_by_fuel(vehicles: pd.DataFrame, fuel_shares: pd.DataFrame, params: MobilityParams) -> pd.DataFrame:
    base_shares = {t: dict(zip(g['Fuel_type'], g['Share'])) for t, g in fuel_shares.groupby('Type_lv2')}
    rows = []
    for (vtype, year), n in vehicles.set_index(['Type_lv2', 'Year'])['Value'].items():
        shares = dict(base_shares.get(vtype, {'NA': 1.0}))
        timed = params.electrification.get(ELECTRIFICATION_GROUPS.get(vtype))
        if timed:
            f = phase_in_share(year, timed.start, timed.end, timed.value)
            moved = (shares.get('Fossil', 0) + shares.get('Hybrid', 0)) * f
            shares = {k: v * (1 - f) if k in ('Fossil', 'Hybrid') else v for k, v in shares.items()}
            shares['Electric'] = shares.get('Electric', 0) + moved
        for fuel, share in shares.items():
            if share > 0:
                rows.append({'Type_lv2': vtype, 'Fuel_type': fuel, 'Year': year, 'Value': n * share})
    return pd.DataFrame(rows)

def project_vehicles(params: MobilityParams, d, base_year=2024, end_year=2100) -> VehicleResult:
    traffic = project_traffic(d.traffic, d.gdp, d.pop, params, base_year, end_year)
    vehicles = project_fleet(d.fleet, traffic, base_year, end_year, d.occupancy, params)
    return VehicleResult(traffic, vehicles, split_by_fuel(vehicles, d.fuel_shares, params),
                         vehicle_km(traffic, d.occupancy, params))
