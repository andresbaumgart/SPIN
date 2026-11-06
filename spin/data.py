"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Input data (drivers)
"""

from __future__ import annotations
import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from .config import ModelError, Settings

log = logging.getLogger(__name__)

# Population years replaced by a PCHIP spline (used for buildings only)
POPULATION_SMOOTHING = (2022, 2030)

def require_columns(df, columns, source):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ModelError(f'{source}: missing column(s) {missing}. Found: {list(df.columns)}')

def read_sheet(path, required=(), sheet_name='input') -> pd.DataFrame:
    """Standard input sheet: keep columns 'Parameter' .. 'Value'."""
    path = Path(path)
    if not path.exists():
        raise ModelError(f'Input file not found: {path}')
    df = pd.read_excel(path, sheet_name=sheet_name)
    require_columns(df, ['Parameter', 'Value', *required], f'{path.name}[{sheet_name}]')
    return df.loc[:, 'Parameter':'Value']

def read_statcube_csv(path) -> pd.DataFrame:
    """StatCube CSV export (6 header lines), trying several encodings."""
    path = Path(path)
    if not path.exists():
        folder = path.parent
        found = sorted(p.name for p in folder.glob('*.csv')) if folder.exists() else []
        raise ModelError(f'StatCube file not found: {path}\n'
                         f'CSV files in {folder}: {found or "none (folder missing or empty)"}\n'
                         'Copy the file there.')
    raw = path.read_bytes()
    for encoding in ['utf-8-sig', 'cp1252', 'latin1']:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = [line.strip() for line in text.splitlines()]

    header = next((i for i, l in enumerate(lines) if l.lstrip('"').startswith('Year') and 'Number' in l), None)
    if header is None:
        raise ModelError(f'{path.name}: no table header (line starting with "Year" and containing "Number"). '
                         'First lines:\n  ' + '\n  '.join(lines[:10]))

    if lines[header].startswith('"Year,'):
        lines = [l[1:-1].replace('""', '"') if len(l) > 1 and l[0] == l[-1] == '"' else l for l in lines]
    sep = max([',', ';', '\t'], key=lines[header].count)
    german = sep == ';'
    df = pd.read_csv(io.StringIO('\n'.join(lines[header:])), sep=sep, low_memory=False, on_bad_lines='skip',
                     thousands='.' if german else ',', decimal=',' if german else '.')

    df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')].drop(columns='Annotations', errors='ignore')
    n_lines = len(df)
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    df = df[df['Year'].notna()].copy()           # drops footer / annotation lines
    df['Year'] = df['Year'].astype(int)
    if 'Number' in df.columns:
        number = df['Number']
        df['Number'] = pd.to_numeric(number, errors='coerce')
        bad = df['Number'].isna() & number.notna() & (number.astype(str).str.strip() != '-')
        if bad.any():
            raise ModelError(f'{path.name}: {bad.sum()} values in "Number" are not numbers, e.g. '
                             f'{number[bad].head(3).tolist()}')
    log.info('%s: %d rows read (separator %r, %d footer lines ignored)', path.name, len(df), sep, n_lines - len(df))
    return df

# ÖKS15 gives future changes relative to 1971-2000 but no Austrian mean for that period:
# the observed mean of the current period (1986-2010) is taken as the 1971-2000 reference.
DEGREE_DAY_REFERENCE = (1971, 2000)

def degree_days(s: Settings, kind: str) -> pd.Series:
    """Heating or cooling degree days (Kd) per year, base year .. end year, for the climate scenario on the
    settings sheet: reference value + change per period (data_degree_days.xlsx), placed at the period
    midpoints, linear in between, constant after the last period."""
    s.require('degree_days')
    dd = read_sheet(s.input_path('degree_days'), ['Climate_scenario', 'Year_from', 'Year_to', 'Unit'])
    obs = dd[dd['Parameter'] == f'{kind} degree days']
    chg = dd[(dd['Parameter'] == f'{kind} degree days change') & (dd['Climate_scenario'] == s.climate_scenario)]
    if obs.empty or chg.empty:
        raise ModelError(f"data_degree_days.xlsx: needs '{kind} degree days' and '{kind} degree days change' rows "
                         f'for climate scenario {s.climate_scenario!r}')
    ref = float(obs['Value'].iloc[0])
    pct = chg['Unit'].astype(str).str.contains('%')
    value = chg['Value'].astype(float)
    future = ref * (1 + value / 100) if pct.all() else ref + value
    mid = list((chg['Year_from'] + chg['Year_to']) / 2)
    points = sorted([(sum(DEGREE_DAY_REFERENCE) / 2, ref)] + list(zip(mid, future)))
    years = np.arange(s.base_year, s.end_year + 1)
    return pd.Series(np.interp(years, [p[0] for p in points], [p[1] for p in points]), index=years)

def fuel_label(series: pd.Series) -> pd.Series:
    return series.fillna('NA').astype(str).replace({'nan': 'NA', 'NAN': 'NA', '': 'NA'})

@dataclass
class Drivers:
    pop:            pd.Series       # Year -> population (mobility)
    pop_smooth:     pd.Series       # Year -> population, smoothed (buildings)
    gdp:            pd.Series       # Year -> GDP per capita
    traffic:        pd.DataFrame    # Type_lv2, Year, Value (billion pkm / tkm)
    fleet:          pd.DataFrame    # Type_lv2, Year_from, Value (vehicles)
    fuel_shares:    pd.DataFrame    # Type_lv2, Fuel_type, Share (base year)
    occupancy:      dict = None     # Type_lv2 -> Series Year -> pkm/vkm or tkm/vkm (types without data: constant)

def smooth_population(pop: pd.DataFrame, years) -> pd.Series:
    """Replace the given year range by a PCHIP spline through the other years."""
    pop = pop[pop['Year_to'].between(2000, 2100)].copy()
    y, v = pop['Year_to'].values, pop['Value'].values
    mask = (y >= years[0]) & (y <= years[1])
    pop['Smooth'] = v.astype(float)
    pop.loc[mask, 'Smooth'] = PchipInterpolator(y[~mask], v[~mask])(y[mask])
    return pop.set_index('Year_to')['Smooth']

def load_fuel_shares(s: Settings) -> pd.DataFrame:
    path = s.input_path('vehicle_fuel_shares')
    if not os.path.exists(path):
        return pd.DataFrame(columns=['Type_lv2', 'Fuel_type', 'Share'])
    df = read_sheet(path, ['Type_lv2', 'Fuel_type', 'Year_from'])
    df = df[df['Year_from'] == s.base_year].copy()
    df['Fuel_type'] = fuel_label(df['Fuel_type'])
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce').fillna(0)
    df['Share'] = df['Value'] / df.groupby('Type_lv2')['Value'].transform('sum')
    return df[df['Share'] > 0][['Type_lv2', 'Fuel_type', 'Share']].reset_index(drop=True)

def load_occupancy(s: Settings) -> dict:
    """Occupancy (pkm/vkm) or load factor (tkm/vkm) per vehicle type and year: linear between the given years,
    constant outside (data_vehicle_occupancy.xlsx)."""
    s.require('vehicle_occupancy')
    d = read_sheet(s.input_path('vehicle_occupancy'), ['Type_lv2', 'Year_from'])
    years = np.arange(1990, s.end_year + 1)
    out = {}
    for t, g in d.groupby('Type_lv2'):
        g = g.groupby('Year_from')['Value'].mean().astype(float)
        if (g <= 0).any():
            raise ModelError(f'data_vehicle_occupancy.xlsx: occupancy of {t} must be > 0')
        out[t] = pd.Series(np.interp(years, g.index.to_numpy(float), g.to_numpy()), index=years)
    return out

def load_drivers(s: Settings) -> Drivers:
    s.require('population', 'gdp', 'traffic', 'vehicle_fleet')
    pop = read_sheet(s.input_path('population'), ['Year_to'])
    gdp = read_sheet(s.input_path('gdp'), ['Year_from'])
    traffic = read_sheet(s.input_path('traffic'), ['Type_lv2', 'Year'])
    fleet = read_sheet(s.input_path('vehicle_fleet'), ['Type_lv2', 'Year_from'])

    pop_smooth = smooth_population(pop, POPULATION_SMOOTHING)
    for df in (pop, gdp, traffic, fleet):
        df['Value'] = df['Value'].astype(float)
    return Drivers(
        pop=pop[pop['Year_to'] <= 2100].set_index('Year_to')['Value'],
        pop_smooth=pop_smooth,
        gdp=gdp.set_index('Year_from')['Value'],
        traffic=traffic,
        fleet=fleet,
        fuel_shares=load_fuel_shares(s),
        occupancy=load_occupancy(s))

def _sources_by(path, key) -> dict:
    """{key value: 'source 1; source 2'} from the Source column of an input sheet."""
    if not os.path.exists(path):
        return {}
    df = pd.read_excel(path, sheet_name='input')
    if 'Source' not in df.columns:
        return {}
    df = df[df['Source'].notna()]
    if key is None:
        return {'all': '; '.join(dict.fromkeys(df['Source'].astype(str).str.strip()))}
    return {k: '; '.join(dict.fromkeys(g['Source'].astype(str).str.strip())) for k, g in df.groupby(key)}

def load_sources(s: Settings) -> dict:
    """Data sources per input file (and per type), for the 'sources' sheets of the MISO2 files."""
    return {
        'population': _sources_by(s.input_path('population'), None).get('all', ''),
        'gdp': _sources_by(s.input_path('gdp'), None).get('all', ''),
        'traffic': _sources_by(s.input_path('traffic'), 'Type_lv2'),
        'fleet': _sources_by(s.input_path('vehicle_fleet'), 'Type_lv2'),
        'fuel': _sources_by(s.input_path('vehicle_fuel_shares'), 'Type_lv2'),
        'appliances': _sources_by(s.input_path('appliance_penetration'), 'Appliance'),
        'capacity': _sources_by(s.input_path('installed_capacity'), 'Type_lv2'),
    }
