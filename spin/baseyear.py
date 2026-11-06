"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Base-year product stocks
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass
import pandas as pd
from .config import ModelError, Settings
from .data import read_statcube_csv, require_columns
from .mappings import (BUILDING_TYPE_NAMES, BUILDING_TYPES, CONSTRUCTION_PERIODS, OWNERSHIP_NAMES, RESIDENTIAL_TYPES, STATCUBE_COLUMNS, UFA_TO_NFA, URBAN_CENTRE)

log = logging.getLogger(__name__)

@dataclass
class BaseYear:
    buildings:      pd.DataFrame  # Floor area (m2) by region, type, ownership, occupancy, density, construction year
    appliances:     pd.DataFrame  # Appliance units
    households:     pd.DataFrame  # Households by type / region / density class
    infrastructure: pd.DataFrame  # Infrastructure area (m2) by type

def get_base_year(s: Settings) -> BaseYear:
    """Build the base year from the input files."""
    log.info('Base year: building from StatCube / GLOMIS')
    detail = floor_area_detail(s)
    buildings = floor_area_stock(detail)
    appliances, households = households_and_appliances(s, buildings)
    base = BaseYear(buildings, appliances, households, infrastructure_base(s))
    return base

#%% Buildings

def floor_area_detail(s: Settings) -> pd.DataFrame:
    """StatCube floor area, split into Vienna / Rest of Austria, spread over construction years."""
    # All StatCube floor area CSVs are read: the one whose 2nd column contains
    # 'Vienna' is the table by federal state, all others are Austria by urban-rural typology.
    s.require('statcube')
    austria, regions = [], []
    for path in s.input_path('statcube'):
        df = read_statcube_csv(path)
        if (df.iloc[:, 1] == 'Vienna').any():
            regions.append((path.name, df.rename(columns={df.columns[1]: 'Region'})))
        else:
            austria.append((path.name, df.rename(columns={df.columns[1]: 'Urban_rural'})))
    log.info('StatCube Austria tables: %s | federal-state table: %s',
             [n for n, _ in austria], [n for n, _ in regions])
    if len(regions) != 1 or not austria:
        raise ModelError(f'{s.input_path("statcube")[0].parent} needs one CSV by federal state (with Vienna) and at least one '
                         f'CSV by urban-rural typology. Found federal-state: {[n for n, _ in regions]}, '
                         f'urban-rural: {[n for n, _ in austria]}')
    austria = pd.concat([df for _, df in austria], ignore_index=True)
    regions = regions[0][1]

    # Vienna is entirely 'Urban centre (large)': deduct it from Austria's urban centres
    austria.insert(1, 'Region', 'Austria')
    vienna = regions[regions['Region'] == 'Vienna'].copy()
    if vienna.empty:
        raise ModelError('StatCube regional data contains no Vienna rows')
    vienna.insert(2, 'Urban_rural', URBAN_CENTRE)
    urban = austria[austria['Urban_rural'] == URBAN_CENTRE]
    rest = austria[austria['Urban_rural'] != URBAN_CENTRE]
    keys = [c for c in urban.columns if c not in ['Year', 'Region', 'Urban_rural', 'Number']]
    merged = urban.merge(vienna, on=keys, how='left', suffixes=('', '_vienna'))
    merged['Number'] = merged['Number'] - merged['Number_vienna'].fillna(0)
    rest_of_austria = pd.concat([merged[['Year', 'Region', 'Urban_rural'] + keys + ['Number']], rest], ignore_index=True)
    rest_of_austria['Region'] = 'Rest of Austria'

    # Vienna gets explicit zero rows for all non-urban combinations
    zero = rest_of_austria[rest_of_austria['Urban_rural'] != URBAN_CENTRE][['Urban_rural'] + keys].drop_duplicates()
    zero.insert(0, 'Number', 0)
    zero.insert(0, 'Region', 'Vienna')
    zero.insert(0, 'Year', s.base_year)
    df = pd.concat([rest_of_austria, vienna, zero.reset_index(drop=True)], ignore_index=True)

    require_columns(df, list(STATCUBE_COLUMNS), 'StatCube building data')
    df = df.rename(columns=STATCUBE_COLUMNS)
    df.insert(0, 'Parameter', 'Function')
    df.insert(0, 'Type_lv1', 'Buildings')
    df['Value'] = df['Value'].fillna(0).astype(int)

    # Spread each construction period evenly over its single years
    df = df[df['Value'] > 0].reset_index(drop=True)
    unknown = sorted(set(df['Cohort']) - set(CONSTRUCTION_PERIODS))
    if unknown:
        raise ModelError(f'Unknown construction period(s) in StatCube data: {unknown}')
    first = df['Cohort'].map(lambda c: CONSTRUCTION_PERIODS[c][0])
    n = df['Cohort'].map(lambda c: CONSTRUCTION_PERIODS[c][1]) - first + 1
    out = df.loc[df.index.repeat(n)].copy()
    out['Value'] = out['Value'] / n.loc[out.index]
    out['Year_from'] = (first.loc[out.index] + out.groupby(level=0).cumcount()).astype('int64')
    out['Year_to'] = out['Year_from']
    out = out.reset_index(drop=True)
    out['Value'] = out['Value'].round().astype(int)
    out['Unit'] = 'm2 UFA'
    out = out[['Parameter', 'Region_lv1', 'Region_lv2', 'Type_lv1', 'Type_lv2', 'Ownership', 'Occupancy', 'Cohort',
               'Density', 'Year_from', 'Year_to', 'Year', 'Unit', 'Value']].copy()
    out['Source'] = 'Statistik Austria housing census'
    out['DOI'] = 'http://statcube.at/statcube/opendatabase?id=derzgwz_gwz_zr_geb'
    out['Notes'] = ''
    return out

def floor_area_stock(detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to model building types, in m2 net floor area."""
    df = detail.copy()
    df['Year_from'] = df['Year_from'].astype(float)
    df['Year_to'] = df['Year_to'].astype(float)
    df['Type_lv2'] = df['Type_lv2'].replace(BUILDING_TYPE_NAMES)
    df['Ownership'] = df['Ownership'].replace(OWNERSHIP_NAMES)
    group_cols = df.loc[:, 'Parameter':'Unit'].columns.tolist()
    base = df.groupby(group_cols, as_index=False).agg({'Value': 'sum'})
    base['Value'] = base['Value'] * base['Type_lv2'].map(UFA_TO_NFA)
    log.info('Base-year floor area: %s m2', f"{base['Value'].sum():,.0f}")
    return base

#%% Appliances

def density_midpoint(density_class, under=0.80, over=1.20):
    """Representative m2 per occupant for a StatCube density class."""
    if density_class == 'Not applicable':
        return None
    numbers = re.findall(r'[\d.]+', density_class)
    if not numbers:
        return None
    if len(numbers) == 1:
        if 'Under' in density_class:
            return float(numbers[0]) * under
        if 'and over' in density_class:
            return float(numbers[0]) * over
        return float(numbers[0])
    return (float(numbers[0]) + float(numbers[1])) / 2

def households_and_appliances(s: Settings, buildings: pd.DataFrame):
    """Households = floor area / (m2 per occupant) / household size; appliances = households x penetration."""
    s.require('household_size', 'appliance_penetration')
    hh = pd.read_excel(s.input_path('household_size'), sheet_name='input', header=None)
    hh_size = {}
    for t in BUILDING_TYPES:
        if t in RESIDENTIAL_TYPES:
            match = hh[hh.iloc[:, 0] == t]
            if match.empty:
                raise ModelError(f'Household size table: no value for {t}')
            hh_size[t] = float(match.iloc[0, 1])
    pen = pd.read_excel(s.input_path('appliance_penetration'), sheet_name='input')
    require_columns(pen, ['Appliance', 'Value'], 'appliance penetration rates')
    penetration = dict(zip(pen['Appliance'], pen['Value']))
    under, over = s.density_under, s.density_over

    app_rows, hh_rows = [], []
    for year in buildings['Year'].unique():
        year_data = buildings[buildings['Year'] == year]
        for btype, size in hh_size.items():
            type_data = year_data[year_data['Type_lv2'] == btype]
            for region in type_data['Region_lv2'].unique():
                region_data = type_data[type_data['Region_lv2'] == region]
                for density_class in region_data['Density'].unique():
                    ufa = region_data[region_data['Density'] == density_class]['Value'].sum()
                    density = density_midpoint(density_class, under, over)
                    if ufa == 0 or density is None or density <= 0:
                        continue
                    occupants = ufa / density
                    households = occupants / size
                    hh_rows.append({'Year': year, 'Region_lv2': region, 'Building_Type': btype,
                                    'Density_Class': density_class, 'Total_UFA_m2': ufa,
                                    'Density_m2_per_person': density, 'Occupants': occupants,
                                    'Household_Size': size, 'Households': households})
                    for appliance, rate in penetration.items():
                        n = households * rate
                        if n > 0.1:
                            app_rows.append({'Parameter': 'Function', 'Type_lv1': 'Appliances', 'Type_lv2': appliance,
                                             'Building_Type': btype, 'Density_Class': density_class,
                                             'Region_lv1': s.region, 'Region_lv2': region, 'Year_from': year,
                                             'Year_to': year, 'Year': year, 'Unit': 'Units', 'Value': n,
                                             'Source': 'Derived from building stock',
                                             'Notes': f'Based on {households:.0f} households'})
    return pd.DataFrame(app_rows), pd.DataFrame(hh_rows)

#%% Infrastructure

def infrastructure_base(s: Settings) -> pd.DataFrame:
    s.require('glomis')
    df = pd.read_parquet(s.input_path('glomis'))
    require_columns(df, ['area', 'country', 'category'], 'GLOMIS')
    df = df[df['country'] == s.country_code]
    n_rows = len(df)
    df = df.groupby('category', as_index=False)['area'].sum()
    log.info('GLOMIS: %d rows summed to %d categories, total %s m2', n_rows, len(df), f"{df['area'].sum():,.0f}")
    y = s.base_year
    return pd.DataFrame({'Region_lv1': s.region, 'Region_lv2': 'NA', 'Type_lv1': 'Mobility infrastructure',
                         'Type_lv2': df['category'], 'Year_from': y, 'Year_to': y, 'Year': y, 'Unit': 'm2',
                         'Value': df['area']}).reset_index(drop=True)
