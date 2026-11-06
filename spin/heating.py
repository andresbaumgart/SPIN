"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Space heating and hot water (useful heat, final energy, installed capacity)

Per year, building type, construction period and renovation status:
  space heating = floor area x space heating demand (kWh/m2) x calibration factor x degree-day factor
  hot water     = floor area x hot water demand (kWh/m2)
  useful heat   = space heating + hot water
  per system    = useful heat x heating system share (by type and renovation status, incl. solar thermal)
  final energy  = useful heat / efficiency (heat pumps: electricity; ambient heat = the rest)
  capacity (MW) = useful heat / full-load hours x oversizing factor

Calibration factor: base-year final energy for space heating of residential buildings = 'Heating calibration target'
(settings sheet). Degree-day factor: heating degree days of the year / base year (data_degree_days.xlsx,
climate scenario on the settings sheet). Heating measures ('heating' sheet) move the system shares
linearly from the base-year mix to a target mix.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .config import ModelError, Settings
from .data import degree_days, read_sheet
from .mappings import BUILDING_TYPES, HEATING_SYSTEMS
from .scenarios import HeatingParams

log = logging.getLogger(__name__)
_logged = set()
STATUSES = ['Not renovated', 'Thermally renovated', 'New construction']

@dataclass
class HeatingInputs:
    demand:     pd.Series   # (Type_lv2, Construction_period, Renovation_status) -> space heating kWh/m2/a
    hot_water:  pd.Series   # Type_lv2 -> hot water kWh/m2/a
    shares:     pd.Series   # (Type_lv2, Renovation_status, Heating_system) -> share of useful heat (base year)
    efficiency: dict        # Heating_system -> useful heat / final energy
    hours:      dict        # Heating_system -> full-load hours (h/a)
    hdd:        pd.Series   # Year -> heating degree days relative to the base year

def load_heating_inputs(s: Settings) -> HeatingInputs:
    s.require('hc_demand', 'hc_shares', 'hc_systems', 'degree_days')
    d = read_sheet(s.input_path('hc_demand'), ['Type_lv2', 'Construction_period', 'Renovation_status'])
    space = d[d['Parameter'] == 'Space heating demand']
    demand = space.set_index(['Type_lv2', 'Construction_period', 'Renovation_status'])['Value'].astype(float)
    hw = d[d['Parameter'] == 'Hot water demand'].groupby('Type_lv2')['Value'].mean().astype(float)
    missing = [t for t in BUILDING_TYPES if t not in hw.index]
    if missing:
        raise ModelError(f"data_heating_cooling_demand.xlsx: no 'Hot water demand' for {missing}")

    sh = read_sheet(s.input_path('hc_shares'), ['Type_lv2', 'Renovation_status', 'System'])
    sh = sh[sh['Parameter'] == 'Heating system share'].rename(columns={'System': 'Heating_system'})
    unknown = sorted(set(sh['Heating_system']) - set(HEATING_SYSTEMS))
    if unknown:
        raise ModelError(f'data_heating_cooling_system_shares.xlsx: unknown heating system(s) {unknown}; '
                         f'known: {HEATING_SYSTEMS} (mappings.HEATING_TO_MISO)')
    shares = sh.groupby(['Type_lv2', 'Renovation_status', 'Heating_system'])['Value'].sum().astype(float)
    total = shares.groupby(level=[0, 1]).transform('sum')
    off = total[(total - 1).abs() > 0.01]
    if len(off):
        log.warning('Heating system shares do not add up to 1 for %s; normalised', sorted(set(off.index.droplevel(2))))
    shares = shares / total
    missing = [(t, st) for t in BUILDING_TYPES for st in STATUSES if (t, st) not in total.index]
    if missing:
        raise ModelError(f'data_heating_cooling_system_shares.xlsx: no shares for {missing}')

    sy = read_sheet(s.input_path('hc_systems'), ['Service', 'System'])
    sy = sy[sy['Service'] == 'Heating'].rename(columns={'System': 'Heating_system'})
    par = {p: dict(zip(g['Heating_system'], g['Value'].astype(float))) for p, g in sy.groupby('Parameter')}
    for p in ('Efficiency', 'Full-load hours'):
        lacking = [x for x in HEATING_SYSTEMS if x not in par.get(p, {})]
        if lacking:
            raise ModelError(f'data_heating_cooling_systems.xlsx: no {p!r} for {lacking}')

    hdd = degree_days(s, 'Heating')
    return HeatingInputs(demand, hw, shares, par['Efficiency'], par['Full-load hours'], hdd / hdd[s.base_year])

def _demand_per_m2(stock: pd.DataFrame, demand: pd.Series) -> np.ndarray:
    """kWh/m2 per row: exact construction period, else the 'All' row of that type and status."""
    keys = list(zip(stock['Type_lv2'], stock['Construction_period'], stock['Renovation_status']))
    exact = demand.reindex(keys).to_numpy()
    fallback = demand.reindex([(t, 'All', st) for t, _, st in keys]).to_numpy()
    out = np.where(np.isnan(exact), fallback, exact)
    if np.isnan(out).any():
        missing = sorted({k for k, x in zip(keys, out) if np.isnan(x)})
        raise ModelError(f'data_heating_cooling_demand.xlsx: no space heating demand for {missing[:10]}')
    return out

def system_shares(p: HeatingParams, base: pd.Series, years) -> pd.DataFrame:
    """Shares per Year, Type_lv2, Renovation_status, Heating_system. A measure moves the shares linearly
    from the base-year mix (Start Year) to its target mix (End Year); systems without a target share the
    rest in their base-year proportions. If several measures cover the same type and status, the last wins."""
    base = base.unstack('Heating_system').reindex(columns=HEATING_SYSTEMS, fill_value=0).fillna(0)
    years = np.asarray(list(years))
    rows = []
    for (t, st), b in base.iterrows():
        b = b.to_numpy(float)
        shares = np.tile(b, (len(years), 1))
        for m in p.measures:
            if (m.types and t not in m.types) or (m.statuses and st not in m.statuses):
                continue
            target = np.array([m.targets.get(x, np.nan) for x in HEATING_SYSTEMS])
            free = np.isnan(target)
            rest = max(0.0, 1 - np.nansum(target))
            if b[free].sum() > 0:
                target[free] = b[free] / b[free].sum() * rest
            else:   # nothing left to share the rest: spread it over the systems with a target
                target[free] = 0
                target = target / target.sum() if target.sum() > 0 else target
            progress = np.clip((years - m.start) / max(m.end - m.start, 1), 0, 1)[:, None]
            shares = b + (target - b) * progress
        for i, y in enumerate(years):
            for j, x in enumerate(HEATING_SYSTEMS):
                if shares[i, j] > 0:
                    rows.append((y, t, st, x, shares[i, j]))
    return pd.DataFrame(rows, columns=['Year', 'Type_lv2', 'Renovation_status', 'Heating_system', 'Share'])

def project_heating(renovation: pd.DataFrame, p: HeatingParams, h: HeatingInputs, s: Settings) -> pd.DataFrame:
    """Space heating and hot water per Year, Type_lv2, Renovation_status and Heating_system: useful heat
    (space heating, hot water, total), final energy, ambient heat (GWh/a) and installed capacity (MW)."""
    st = renovation[renovation['Value'] > 0].copy()
    st['Space'] = st['Value'] * _demand_per_m2(st, h.demand) * st['Year'].map(h.hdd).to_numpy() / 1e6   # GWh
    st['Hot_water'] = st['Value'] * st['Type_lv2'].map(h.hot_water) / 1e6                                 # GWh
    useful = st.groupby(['Year', 'Type_lv2', 'Renovation_status'], as_index=False)[['Space', 'Hot_water']].sum()

    # calibration: base-year final energy for space heating of residential buildings (base-year mix) = target
    if s.heating_target > 0:
        b = useful[(useful['Year'] == s.base_year) & useful['Type_lv2'].str.startswith('R_')]
        b = b.merge(h.shares.rename('Share').reset_index(), on=['Type_lv2', 'Renovation_status'])
        res = (b['Space'] * b['Share'] / b['Heating_system'].map(h.efficiency)).sum()
        factor = s.heating_target * 1000 / res
        if round(factor, 4) not in _logged:
            _logged.add(round(factor, 4))
            log.info('Space heating calibration factor: %.3f (modelled %.1f TWh, target %.1f TWh)',
                     factor, res / 1000, s.heating_target)
        useful['Space'] *= factor

    df = useful.merge(system_shares(p, h.shares, range(s.base_year, s.end_year + 1)),
                      on=['Year', 'Type_lv2', 'Renovation_status'])
    df['Space_heating'] = df['Space'] * df['Share']
    df['Hot_water'] = df['Hot_water'] * df['Share']
    df['Useful_heat'] = df['Space_heating'] + df['Hot_water']
    df['Final_energy'] = df['Useful_heat'] / df['Heating_system'].map(h.efficiency)
    df['Ambient_heat'] = np.where(df['Heating_system'] == 'Heat pump', df['Useful_heat'] - df['Final_energy'], 0.0)
    df['Capacity'] = df['Useful_heat'] * 1000 / df['Heating_system'].map(h.hours) * s.heating_oversizing   # MW
    return df[['Year', 'Type_lv2', 'Renovation_status', 'Heating_system', 'Space_heating', 'Hot_water',
               'Useful_heat', 'Final_energy', 'Ambient_heat', 'Capacity']].reset_index(drop=True)
