"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Operational energy use (MISO2_Energy_Operational: GJ per functional unit, energy carrier and year)

GJ per functional unit (m2, appliance, vehicle, MW) and year, by energy carrier (data_operational_energy.xlsx):
  'Operational energy'     fixed value per unit, e.g. lighting per m2, electricity per appliance,
                           fuel per vehicle (= annual mileage x energy per vehicle-km). A row for 'build_r_sfh'
                           applies to all end uses starting with 'build_r_sfh_' (_unr, _tr_his, _tr).
  'Energy per pkm' / 'tkm' trains: energy per pkm (tkm) x modelled traffic / number of trains sharing it
  'Energy carrier factor'  heating and cooling systems: modelled final energy per MW installed capacity
                           x carrier input per GJ final energy (e.g. district heat -> biomass, gas, waste, ...)
Vehicles: per-vehicle values x car mileage measures (km per vehicle). The MISO2 file gets GJ per functional unit
and year (MISO2 multiplies by the function stock); the totals (GJ per FU x stock) are written to
output/results/operational_energy.csv.
"""

from __future__ import annotations
import logging
import pandas as pd
from .config import ModelError, Settings
from .data import read_sheet
from .mappings import COOLING_TO_MISO, HEATING_TO_MISO, TRAIN_TRAFFIC, VEH_TO_MISO, VEHICLE_TO_TRAFFIC

log = logging.getLogger(__name__)
KWH_TO_GJ = 0.0036

def load_energy_inputs(s: Settings) -> pd.DataFrame:
    s.require('operational_energy')
    d = read_sheet(s.input_path('operational_energy'), ['End_use_sector', 'Energy_carrier'])
    src = pd.read_excel(s.input_path('operational_energy'), sheet_name='input')
    d['Source'] = src['Source'].fillna('').astype(str)
    d['Notes'] = src['Notes'].fillna('').astype(str) if 'Notes' in src else ''
    known = {'Operational energy', 'Energy per pkm', 'Energy per tkm', 'Energy carrier factor'}
    bad = sorted(set(d['Parameter']) - known)
    if bad:
        raise ModelError(f'data_operational_energy.xlsx: unknown Parameter(s) {bad}; known: {sorted(known)}')
    d['Value'] = d['Value'].astype(float)
    return d

def _match(row_key: str, end_uses) -> list:
    """End uses a data row applies to: exact name, or all end uses starting with '<key>_' (buildings)."""
    if row_key in end_uses:
        return [row_key]
    return [e for e in end_uses if e.startswith(row_key + '_') and e.startswith('build_')]

def _vehicle_type(end_use):
    """'veh_car_icev' -> 'Cars' (SPIN vehicle type), None for other end uses."""
    names = [k for k, v in VEH_TO_MISO.items() if v == end_use]
    for name in names:
        for t in sorted(VEHICLE_TO_TRAFFIC, key=len, reverse=True):
            if name == t or name.startswith(t + '_'):
                return t
    return None

def operational_energy(r, d: pd.DataFrame, end_uses, s: Settings) -> pd.DataFrame:
    """End_use_sector, Energy_carrier, Year, Value (GJ per functional unit and year), Source."""
    years = list(range(s.base_year, s.end_year + 1))
    rows = []

    # fixed values per unit
    for _, x in d[d['Parameter'] == 'Operational energy'].iterrows():
        for e in _match(x['End_use_sector'], end_uses):
            vtype = _vehicle_type(e)
            mob = r.scenario.mobility
            for y in years:
                f = mob.mileage_factor(vtype, y) if vtype else 1.0     # km per vehicle (mileage measures)
                rows.append((e, x['Energy_carrier'], y, x['Value'] * f, x['Source'], x['Notes']))

    # trains: energy per pkm / tkm x traffic / number of trains
    veh = r.vehicles.vehicles.groupby(['Type_lv2', 'Year'])['Value'].sum()
    for _, x in d[d['Parameter'].isin(['Energy per pkm', 'Energy per tkm'])].iterrows():
        e = x['End_use_sector']
        if e not in TRAIN_TRAFFIC or e not in end_uses:
            continue
        mode, types = TRAIN_TRAFFIC[e]
        traffic = r.vehicles.traffic.get(mode)
        if traffic is None:
            log.warning('Operational energy: no %s traffic for %s', mode, e)
            continue
        for y in years:
            n = sum(veh.get((t, y), 0.0) for t in types)
            if n > 0 and y in traffic.index:
                gj = x['Value'] * traffic[y] * 1e9 / n * KWH_TO_GJ
                rows.append((e, x['Energy_carrier'], y, gj, x['Source'], x['Notes']))

    # heating and cooling systems: final energy per MW x energy carrier factor
    for df, col, mapping in ((r.heating, 'Heating_system', HEATING_TO_MISO), (r.cooling, 'Cooling_system', COOLING_TO_MISO)):
        g = df.groupby([col, 'Year'])[['Final_energy', 'Capacity']].sum()
        per_mw = (g['Final_energy'] * 3600 / g['Capacity']).where(g['Capacity'] > 0)     # GJ per MW and year
        for system, e in mapping.items():
            if e not in end_uses:
                continue
            fac = d[(d['Parameter'] == 'Energy carrier factor') & (d['End_use_sector'] == e)]
            if fac.empty:
                log.warning('Operational energy: no energy carrier factor for %s', e)
                continue
            for _, x in fac.iterrows():
                for y in years:
                    v = per_mw.get((system, y))
                    if v is not None and pd.notna(v):
                        rows.append((e, x['Energy_carrier'], y, v * x['Value'],
                                     f'SPIN final energy / installed capacity of {system}; carrier: {x["Source"]}',
                                     x['Notes']))
    out = pd.DataFrame(rows, columns=['End_use_sector', 'Energy_carrier', 'Year', 'Value', 'Source', 'Notes'])
    missing = sorted(e for e in set(end_uses) - set(out['End_use_sector'])
                     if not e.startswith(('infra_', 'powerplants_')))      # infrastructure / power plants: no operational energy
    if missing:
        log.warning('Operational energy: no data for %s (left out of MISO2_Energy_Operational)', missing)
    return out

def energy_sheets(op: pd.DataFrame, region: str, s: Settings, scenario: str) -> dict:
    """'values' and 'sources' of MISO2_Energy_Operational: one row per end use and energy carrier, one column per
    year, GJ per functional unit and year (MISO2 multiplies by the function stock). Totals: results/operational_energy.csv."""
    years = list(range(s.base_year, s.end_year + 1))
    wide = op.pivot_table(index=['End_use_sector', 'Energy_carrier'], columns='Year', values='Value', aggfunc='sum')
    wide = wide.reindex(columns=years).fillna(0)
    src = op.groupby(['End_use_sector', 'Energy_carrier'])[['Source', 'Notes']].first()
    prefix = (f"SPIN (Service-driven Product Stock Inventory), scenario '{scenario}'. GJ per functional unit and year. ")
    cols = ['MISO2_country', 'End_use_sector', 'Energy_carrier', *[str(y) for y in years]]
    vals, srcs = [], []
    for (e, c), v in wide.iterrows():
        text = prefix + '; '.join(t for t in src.loc[(e, c)] if t)
        vals.append([region, e, c, *v.to_list()])
        srcs.append([region, e, c, *([text] * len(years))])
    return {'values': pd.DataFrame(vals, columns=cols), 'sources': pd.DataFrame(srcs, columns=cols)}
