"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Space cooling (useful cooling, final energy, installed capacity)

Like heating, cooling is calculated per m2 of the building stock:
  useful cooling = floor area x cooling demand (kWh/m2, by year)
Cooling demand per m2 (data_heating_cooling_demand.xlsx, parameter 'Cooling demand') follows the projection
of BMK (2024) chosen on the settings sheet (WEM or Transition), which covers growing use of air-conditioning
and a warmer climate; linear between the given years, after the last year with cooling degree days
(data_degree_days.xlsx). Rows can be given for a building type and / or renovation status; 'All' is used otherwise.
Per cooling system: useful cooling x system share (data_heating_cooling_system_shares.xlsx);
final energy = useful / SEER; installed capacity (MW) = useful cooling / full-load hours.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .config import ModelError, Settings
from .data import degree_days, read_sheet
from .mappings import COOLING_SYSTEMS

@dataclass
class CoolingInputs:
    demand:     dict        # (Type_lv2 or 'All', Renovation_status or 'All') -> Series Year -> kWh/m2/a
    shares:     pd.DataFrame  # Type_lv2 (or 'All'), Renovation_status, Cooling_system, Share
    efficiency: dict        # Cooling_system -> useful cooling / final energy
    hours:      dict        # Cooling_system -> full-load hours (h/a)

def load_cooling_inputs(s: Settings) -> CoolingInputs:
    s.require('hc_demand', 'hc_shares', 'hc_systems', 'degree_days')
    d = read_sheet(s.input_path('hc_demand'), ['Type_lv2', 'Renovation_status', 'Projection', 'Year_from'])
    d = d[d['Parameter'] == 'Cooling demand']
    available = sorted(d['Projection'].dropna().astype(str).unique())
    d = d[d['Projection'].astype(str) == s.cooling_scenario]
    if d.empty:
        raise ModelError(f"data_heating_cooling_demand.xlsx: no 'Cooling demand' for projection "
                         f'{s.cooling_scenario!r} (settings: Cooling demand scenario); available: {available}')
    years = np.arange(s.base_year, s.end_year + 1)
    cdd = degree_days(s, 'Cooling')
    demand = {}
    for key, g in d.groupby(['Type_lv2', 'Renovation_status']):
        g = g.groupby('Year_from')['Value'].mean().astype(float)
        series = pd.Series(np.interp(years, g.index.to_numpy(float), g.to_numpy()), index=years)
        last = int(g.index.max())
        later = years > last
        series[later] = series[last] * cdd[later] / cdd[last]   # after the projection: with cooling degree days
        demand[key] = series

    sh = read_sheet(s.input_path('hc_shares'), ['Type_lv2', 'Renovation_status', 'System'])
    sh = sh[sh['Parameter'] == 'Cooling system share'].rename(columns={'System': 'Cooling_system'})
    unknown = sorted(set(sh['Cooling_system']) - set(COOLING_SYSTEMS))
    if unknown:
        raise ModelError(f'data_heating_cooling_system_shares.xlsx: unknown cooling system(s) {unknown}; '
                         f'known: {COOLING_SYSTEMS} (mappings.COOLING_TO_MISO)')
    if sh.empty:
        raise ModelError("data_heating_cooling_system_shares.xlsx: no 'Cooling system share' rows")
    sh = sh.groupby(['Type_lv2', 'Renovation_status', 'Cooling_system'], as_index=False)['Value'].sum()
    sh['Share'] = sh['Value'] / sh.groupby(['Type_lv2', 'Renovation_status'])['Value'].transform('sum')

    sy = read_sheet(s.input_path('hc_systems'), ['Service', 'System'])
    sy = sy[sy['Service'] == 'Cooling']
    par = {p: dict(zip(g['System'], g['Value'].astype(float))) for p, g in sy.groupby('Parameter')}
    for p in ('Efficiency', 'Full-load hours'):
        lacking = [x for x in sh['Cooling_system'].unique() if x not in par.get(p, {})]
        if lacking:
            raise ModelError(f'data_heating_cooling_systems.xlsx: no {p!r} for cooling system(s) {lacking}')
    return CoolingInputs(demand, sh[['Type_lv2', 'Renovation_status', 'Cooling_system', 'Share']],
                         par['Efficiency'], par['Full-load hours'])

def _match(keys, t, st):
    """Most specific key for building type t and renovation status st ('All' as fallback)."""
    for k in ((t, st), (t, 'All'), ('All', st), ('All', 'All')):
        if k in keys:
            return k
    return None

def project_cooling(renovation: pd.DataFrame, c: CoolingInputs) -> pd.DataFrame:
    """Space cooling per Year, Type_lv2, Renovation_status and Cooling_system: useful cooling and final
    energy (GWh/a), installed capacity (MW)."""
    area = renovation.groupby(['Year', 'Type_lv2', 'Renovation_status'], as_index=False)['Value'].sum()
    pairs = area[['Type_lv2', 'Renovation_status']].drop_duplicates().itertuples(index=False)
    demand_key = {(t, st): _match(c.demand, t, st) for t, st in pairs}
    missing = sorted(k for k, v in demand_key.items() if v is None)
    if missing:
        raise ModelError(f"data_heating_cooling_demand.xlsx: no 'Cooling demand' for {missing}")
    per_m2 = np.array([c.demand[demand_key[(t, st)]][y]
                       for t, st, y in zip(area['Type_lv2'], area['Renovation_status'], area['Year'])])
    area['Useful'] = area['Value'] * per_m2 / 1e6                                   # GWh

    share_keys = set(zip(c.shares['Type_lv2'], c.shares['Renovation_status']))
    area['Share_key'] = [_match(share_keys, t, st) for t, st in zip(area['Type_lv2'], area['Renovation_status'])]
    if area['Share_key'].isna().any():
        bad = sorted(set(zip(area.loc[area['Share_key'].isna(), 'Type_lv2'], area.loc[area['Share_key'].isna(), 'Renovation_status'])))
        raise ModelError(f"data_heating_cooling_system_shares.xlsx: no 'Cooling system share' for {bad}")
    shares = c.shares.assign(Share_key=list(zip(c.shares['Type_lv2'], c.shares['Renovation_status'])))
    df = area.merge(shares[['Share_key', 'Cooling_system', 'Share']], on='Share_key')
    df['Useful_cooling'] = df['Useful'] * df['Share']
    df['Final_energy'] = df['Useful_cooling'] / df['Cooling_system'].map(c.efficiency)
    df['Capacity'] = df['Useful_cooling'] * 1000 / df['Cooling_system'].map(c.hours)    # MW
    df = df[df['Useful_cooling'] > 0]
    return df[['Year', 'Type_lv2', 'Renovation_status', 'Cooling_system', 'Useful_cooling', 'Final_energy',
               'Capacity']].sort_values(['Year', 'Type_lv2', 'Renovation_status']).reset_index(drop=True)
