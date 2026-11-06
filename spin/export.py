"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Output files
"""

from __future__ import annotations
import logging
from datetime import date
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from .config import Settings
from .scenarios import BASELINE
from .data import load_sources, require_columns
from .energy import energy_sheets, load_energy_inputs, operational_energy
from .mappings import (BUILD_TO_MISO, COOLING_TO_MISO, HEATING_TO_MISO, HHA_TO_MISO, INFRA_TO_MISO, INFRA_TO_TRAFFIC, MISO_AGGREGATE_GROUPS, POWERPLANT_TYPES, RENOVATION_SUFFIX, STOCK_DUMMY, VEHICLE_TO_TRAFFIC, VEH_TO_MISO, miso_cohort_sector)

log = logging.getLogger(__name__)

STOCK_FILE  = 'MISO2_Function_Stock_v1.xlsx'
INIT_FILE   = 'MISO2_Stock_Initialization_v1.xlsx'
ENERGY_FILE = 'MISO2_Energy_Operational_v1.xlsx'
SHEET_NAMES = {'values': ('values', 'value'), 'sources': ('sources', 'source'), 'units': ('units', 'unit')}

def find_existing(main: Path, kind: str) -> Path | None:
    """An existing MISO2 file of this kind to start from (keeps its Cover and other sheets)."""
    for folder in (main / 'Scenarios' / BASELINE, main / 'Scenarios' / 'Baseline', main):
        if not folder.exists():
            continue
        for p in sorted(folder.glob('*.xlsx')):
            name = p.name.lower()
            if p.name.startswith(('~$', '.')):
                continue
            if ((kind == 'init' and 'initiali' in name) or (kind == 'energy' and 'energy' in name)
                    or (kind == 'stock' and 'stock' in name and 'initiali' not in name)):
                return p
    return None

#%% Sector tables

def wide(df: pd.DataFrame, key: str, unit: str, s: Settings) -> pd.DataFrame:
    """Long (key, Year, Value) -> MISO2_country | End_use_sector | Unit | <years>."""
    years = list(range(s.base_year, s.end_year + 1))
    if len(df) == 0:
        return pd.DataFrame(columns=['MISO2_country', 'End_use_sector', 'Unit'] + [str(y) for y in years])
    t = df.groupby([key, 'Year'])['Value'].sum().unstack('Year').reindex(columns=years).fillna(0)
    t.columns = [str(y) for y in years]
    t.insert(0, 'Unit', unit)
    t.insert(0, 'End_use_sector', t.index)
    t.insert(0, 'MISO2_country', s.region)
    return t.reset_index(drop=True)

def building_end_use(btype, status):
    """'R_SFH', 'Not renovated' -> 'build_r_sfh_unr'."""
    return BUILD_TO_MISO.get(btype, btype) + RENOVATION_SUFFIX[status]

def sector_tables(r, s: Settings) -> dict:
    # Buildings: floor area stock per year, split into _unr / _tr_his / _tr (see RENOVATION_SUFFIX)
    ren = r.buildings.renovation
    bld = ren.assign(End_use_sector=[building_end_use(t, st) for t, st in zip(ren['Type_lv2'], ren['Renovation_status'])])
    app = r.buildings.appliances.assign(End_use_sector=lambda d: d['Type_lv2'].map(HHA_TO_MISO).fillna(d['Type_lv2']))
    fuel = r.vehicles.by_fuel.copy()
    has_fuel = fuel['Type_lv2'].str.endswith(('_electric', '_fossil')) | (fuel['Fuel_type'] == 'NA')
    fuel['End_use_sector'] = fuel['Type_lv2'].where(has_fuel, fuel['Type_lv2'] + '_' + fuel['Fuel_type'].str.lower())
    return {
        'buildings': pd.concat([wide(bld, 'End_use_sector', 'm2 NFA', s), wide(app, 'End_use_sector', 'units', s)],
                               ignore_index=True),
        'vehicles': wide(fuel, 'End_use_sector', 'units', s),
        'infrastructure': wide(r.infrastructure, 'Type_lv2', 'm2', s),
        'heating': wide(r.heating.assign(End_use_sector=r.heating['Heating_system'].map(HEATING_TO_MISO),
                                         Value=r.heating['Capacity']), 'End_use_sector', 'MW', s),
        'cooling': wide(r.cooling.assign(End_use_sector=r.cooling['Cooling_system'].map(COOLING_TO_MISO),
                                         Value=r.cooling['Capacity']), 'End_use_sector', 'MW', s),
    }

#%% Sources

def _join(*parts):
    return '; '.join(dict.fromkeys(p for p in parts if p))

def _vehicle_type(end_use):
    """'Cars_fossil' -> 'Cars', 'Railway_passenger_car' -> 'Railway_passenger_car'."""
    for t in sorted(VEHICLE_TO_TRAFFIC, key=len, reverse=True):
        if end_use == t or end_use.startswith(t + '_'):
            return t
    return end_use

def row_source(sector, end_use, src, s: Settings) -> str:
    """Source text for one row of a sector table (before MISO2 renaming)."""
    traffic = src['traffic']
    if sector == 'buildings' and end_use.startswith('build_'):
        census = f'floor area stock {s.base_year}: Statistik Austria housing census (StatCube)'
        if end_use.endswith('_tr_his'):
            return (f'Historic floor area stock, thermally renovated: {census}; renovation rates / target year '
                    f'from scenario_parameters (buildings sheet); incl. floor area added by conversions')
        if end_use.endswith('_unr'):
            return (f'Historic floor area stock, not thermally renovated: {census}; minus thermal renovation '
                    f'and conversions')
        return (f'New construction since {s.base_year + 1} (thermally renovated standard): population growth '
                f"({src['population']}) x base-year floor area per capita ({census})")
    if sector == 'buildings':
        apps = [a for a, m in HHA_TO_MISO.items() if m == end_use and a in src['appliances']]
        pen = _join(*(src['appliances'][a] for a in apps))
        return (f"Households from floor area (Statistik Austria housing census, StatCube) x appliance "
                f"penetration rates ({pen})")
    if sector == 'vehicles':
        vt = _vehicle_type(end_use)
        tt = VEHICLE_TO_TRAFFIC.get(vt, '')
        return _join(f"Fleet {s.base_year}: {src['fleet'].get(vt, 'n/a')}",
                     f"growth with {tt} traffic: {_join(traffic.get(tt, ''), src['population'], src['gdp'])}",
                     f"fuel shares: {src['fuel'].get(vt, 'n/a')}")
    if sector == 'heating':
        return ('Installed heating capacity (space heating and hot water) = useful heat / full-load hours x '
                'oversizing factor; space heating from floor area stock by type, construction period and renovation '
                'status (Statistik Austria housing census, StatCube) x space heating demand (TABULA AT, OIB RL 6) x '
                'heating degree days (ÖKS15), calibrated to Statistik Austria Energieeinsatz der Haushalte; hot water '
                'from floor area x OIB RL 6 standard value; heating system shares (incl. solar thermal): '
                'data_heating_system_shares.xlsx and heating measures (scenario_parameters)')
    if sector == 'cooling':
        return ('Installed space cooling capacity = useful cooling / full-load hours; useful cooling = floor area '
                '(Statistik Austria housing census, StatCube) x cooling demand per m2 derived from BMK 2024, '
                'Umfassende Bewertung des Potenzials für eine effiziente Wärme- und Kälteversorgung (Table 3); '
                'after 2050 with cooling degree days (ÖKS15); room air conditioners')
    if sector == 'infrastructure':
        modes = INFRA_TO_TRAFFIC.get(end_use, [])
        return _join('Base-year area: GLOMIS',
                     f"growth with {' + '.join(modes)} vehicle-km (traffic / occupancy, data_vehicle_occupancy.xlsx): "
                     f"{_join(*(traffic.get(m, '') for m in modes), src['population'], src['gdp'])}")
    return ''

#%% Stock-driven MISO

def function_stock(tables: dict, s: Settings, src: dict, scenario: str):
    """All end uses with MISO2 names, plus installed power plant capacity (constant)."""
    df = pd.concat([t.assign(Source=[row_source(sector, e, src, s) for e in t['End_use_sector']])
                    for sector, t in tables.items()], ignore_index=True)
    df['End_use_sector'] = df['End_use_sector'].replace({**BUILD_TO_MISO, **HHA_TO_MISO, **VEH_TO_MISO, **INFRA_TO_MISO})
    for target, members in MISO_AGGREGATE_GROUPS.items():
        df.loc[df['End_use_sector'].isin(members), 'End_use_sector'] = target
    source = df.groupby('End_use_sector')['Source'].agg(lambda x: _join(*x))
    unit = df.groupby('End_use_sector')['Unit'].agg(lambda x: _join(*x))
    df = df.drop(columns=['Source', 'Unit']).groupby(['MISO2_country', 'End_use_sector'], as_index=False, sort=True).sum()
    unmapped = [e for e in df['End_use_sector'] if not e.startswith(('build_', 'hha_', 'veh_', 'infra_', 'heat_'))]
    if unmapped:
        log.warning('End uses without MISO2 name (exported as is): %s', unmapped)

    cap = pd.read_excel(s.input_path('installed_capacity'), sheet_name='input')
    require_columns(cap, ['Type_lv2', 'Year_from', 'Value'], 'installed capacity')
    cap['Type_lv2'] = cap['Type_lv2'].astype(str).str.strip()
    cap = cap[pd.to_numeric(cap['Year_from'], errors='coerce') == s.base_year]
    mw = pd.to_numeric(cap.set_index('Type_lv2')['Value'], errors='coerce')
    years = [c for c in df.columns if c not in ('MISO2_country', 'End_use_sector')]
    power = pd.DataFrame([{'MISO2_country': s.region, 'End_use_sector': p,
                           **dict.fromkeys(years, float(mw.get(p, 0)) if pd.notna(mw.get(p, 0)) else 0.0)}
                          for p in POWERPLANT_TYPES])
    values = pd.concat([df, power], ignore_index=True)
    for e, dummy in STOCK_DUMMY.items():          # MISO2 cannot take 0 for these end uses
        rows = values['End_use_sector'] == e
        values.loc[rows, years] = values.loc[rows, years].mask(values.loc[rows, years] == 0, dummy)

    prefix = f"SPIN (Service-driven Product Stock Inventory), scenario '{scenario}'. "
    for p in POWERPLANT_TYPES:
        source[p] = f"Installed capacity {s.base_year}, kept constant: {src['capacity'].get(p, 'n/a')}"
    for p in POWERPLANT_TYPES:
        unit[p] = 'MW'
    for e, dummy in STOCK_DUMMY.items():
        source[e] = _join(source.get(e, ''), f'0 replaced by dummy value {dummy} (MISO2 cannot take 0)')
    sources = values.copy().astype(object)
    sources[years] = [[prefix + source.get(e, '')] * len(years) for e in values['End_use_sector']]
    units = values.copy().astype(object)
    units[years] = [[unit.get(e, '')] * len(years) for e in values['End_use_sector']]
    return {'values': values, 'sources': sources, 'units': units}

def cohort_shares(s: Settings) -> pd.DataFrame:
    """Age-cohort shares (%) per MISO2 sector, from the MISO2 stock of the reference year."""
    year = s.cohort_year
    s.require('miso2_cohorts')
    df = pd.read_parquet(s.input_path('miso2_cohorts')).reset_index()
    df = df[df['time'] == year]
    keys = [c for c in ['type', 'region', 'name', 'sector', 'time'] if c in df.columns]
    cols = [c for c in df.columns if str(c).isdigit() and 1820 <= int(c) <= year]
    df = df.melt(id_vars=keys, value_vars=cols, var_name='cohort', value_name='value')
    df['cohort'] = df['cohort'].astype(int).clip(lower=1900)
    # one share profile per sector (summed over materials etc., so each sector's shares add up to 1)
    df = df.groupby(['sector', 'cohort'], as_index=False)['value'].sum()
    last = df[df['cohort'] == year]
    df = pd.concat([df] + [last.assign(cohort=y) for y in range(year + 1, s.base_year + 1)], ignore_index=True)
    df['share'] = df['value'] / df.groupby('sector')['value'].transform('sum')
    df['sector'] = df['sector'].str.strip()
    return df.rename(columns={'sector': 'cohort_sector'})[['cohort_sector', 'cohort', 'share']]

def initialization(stock: pd.DataFrame, floor_area: pd.DataFrame, shares: pd.DataFrame, s: Settings,
                   additions: pd.DataFrame | None = None) -> pd.DataFrame:
    """Base-year stock by end use and age cohort. Buildings: census construction years; everything else: MISO2 cohort shares of the matching MISO2 sector."""
    by = str(s.base_year)
    # Heating systems: base-year capacity spread evenly over the last <Heating system lifetime> years (settings)
    heating = stock['End_use_sector'].isin(HEATING_TO_MISO.values())    # heating systems only (not heat_ac)
    heat = stock[heating][['MISO2_country', 'End_use_sector', by]]
    n = max(1, int(s.heating_lifetime))
    heat = pd.concat([heat.assign(cohort=y, **{by: heat[by] / n}) for y in range(s.base_year - n + 1, s.base_year + 1)],
                     ignore_index=True)

    other = stock[~stock['End_use_sector'].str.startswith('build_') & ~heating][['MISO2_country', 'End_use_sector', by]].copy()
    other['cohort_sector'] = other['End_use_sector'].map(miso_cohort_sector)
    other = other.dropna(subset=['cohort_sector'])
    missing = sorted(set(other['cohort_sector']) - set(shares['cohort_sector']))
    if missing:
        log.warning('MISO2 cohort file has no sector %s; end uses %s are left out of the stock initialisation',
                    missing, sorted(other.loc[other['cohort_sector'].isin(missing), 'End_use_sector']))
    other = other.merge(shares, on='cohort_sector')
    other[by] = other[by] * other['share']

    # Buildings: census stock by construction year (+ base-year new construction as cohort base year),
    # '_unr', or '_tr_his' for the share already renovated in the base year (settings sheet)
    fa = floor_area[['Type_lv2', 'Cohort', 'Year_from', 'Value']].rename(columns={'Year_from': 'cohort'})
    if additions is not None and len(additions):
        early = additions[additions['Year'] <= s.base_year]
        fa = pd.concat([fa, pd.DataFrame({'Type_lv2': early['Type_lv2'], 'Cohort': '2016 or later',
                                          'cohort': s.base_year, 'Value': early['Value']})], ignore_index=True)
    share = fa['Cohort'].map(lambda c: s.renovated_share.get(c, 0.0)).astype(float)
    bld = pd.concat([fa.assign(Value=fa['Value'] * (1 - share), status='Not renovated'),
                     fa.assign(Value=fa['Value'] * share, status='Thermally renovated')], ignore_index=True)
    bld = bld[bld['Value'] > 0]
    bld['End_use_sector'] = [building_end_use(t, st) for t, st in zip(bld['Type_lv2'], bld['status'])]
    bld = bld[bld['cohort'].between(1900, s.base_year)]
    bld = bld.groupby(['End_use_sector', 'cohort'], as_index=False)['Value'].sum().rename(columns={'Value': by})
    bld.insert(0, 'MISO2_country', s.region)

    cols = ['MISO2_country', 'End_use_sector', 'cohort', by]
    out = pd.concat([other[cols], bld[cols], heat[cols]], ignore_index=True)
    out['cohort'] = out['cohort'].astype(int)
    return out.sort_values(['End_use_sector', 'cohort']).reset_index(drop=True)

def initialization_sheets(init: pd.DataFrame, stock_sheets: dict, s: Settings) -> dict:
    """'values', 'sources' and 'units' for the initialisation file (same shape each)."""
    by = str(s.base_year)
    stock_src = stock_sheets['sources'].set_index('End_use_sector')[by]
    stock_unit = stock_sheets['units'].set_index('End_use_sector')[by]
    prefix = stock_src.iloc[0].split('. ')[0] + '. ' if len(stock_src) else ''
    bld = (f'{prefix}Floor area stock {s.base_year}: Statistik Austria housing census (StatCube), incl. new '
           f'construction {s.base_year}; age structure: construction periods, spread evenly over single years; '
           'renovation status: share already renovated in the base year (settings sheet)')
    out = init.copy().astype(object)
    heat = f'age structure: evenly over the last {int(s.heating_lifetime)} years (settings: Heating system lifetime)'
    out[by] = [bld if e.startswith('build_') else
               _join(stock_src.get(e, ''), heat) if e in HEATING_TO_MISO.values() else
               _join(stock_src.get(e, ''), f'age structure: MISO2 stock {s.cohort_year} by cohort, '
                                           f'sector {miso_cohort_sector(e)}')
               for e in init['End_use_sector']]
    units = init.copy().astype(object)
    units[by] = [stock_unit.get(e, '') for e in init['End_use_sector']]
    return {'values': init, 'sources': out, 'units': units}

def _sheet(wb, name):
    """Sheet by name, case-insensitive; created if missing."""
    for ws in wb.worksheets:
        if ws.title.lower() == name.lower():
            return ws
    return wb.create_sheet(name)

def _replace_rows(ws, df):
    """Keep the header row, replace all rows below it with df."""
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)
    if ws.max_row == 1 and ws.cell(1, 1).value is None:
        for j, c in enumerate(df.columns, start=1):
            ws.cell(1, j, str(c))
    for row in df.itertuples(index=False):
        ws.append(list(row))

def write_miso_file(path: Path, sheets: dict, base: Path | None = None):
    """Write the 'values', 'sources' and 'units' sheets of a MISO2 input file and date the Cover."""
    from openpyxl import Workbook
    source_file = path if path.exists() else base if base is not None and base.exists() else None
    wb = load_workbook(source_file) if source_file else Workbook()
    new = source_file is None
    for key, df in sheets.items():
        ws = next((w for w in wb.worksheets if w.title.lower() in SHEET_NAMES[key]), None)
        if ws is None:
            if not (new or key == 'values'):
                log.info('%s has no %s sheet; skipped', path.name, key)
                continue
            ws = wb.active if new and key == 'values' else wb.create_sheet(key)
            ws.title = key
        _replace_rows(ws, df)
    cover = next((ws for ws in wb.worksheets if ws.title.lower() == 'cover'), None)
    if cover is not None:
        cover['B12'] = date.today()
        cover['B12'].number_format = 'DD.MM.YY'
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

def _column_widths(path: Path) -> dict:
    """{sheet name: [(first col, last col, width)]} read directly from the xlsx (fast, no full load)."""
    import re
    import zipfile
    out = {}
    with zipfile.ZipFile(path) as z:
        wbx = z.read('xl/workbook.xml').decode('utf8')
        rels = z.read('xl/_rels/workbook.xml.rels').decode('utf8')
        targets = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
        targets.update({k: v for v, k in re.findall(r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
        for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbx):
            target = targets.get(rid, '').lstrip('/')
            target = target if target.startswith('xl/') else 'xl/' + target
            try:
                xml = z.read(target).decode('utf8')
            except KeyError:
                continue
            out[name] = [(int(a), int(b), float(w)) for a, b, w in
                         re.findall(r'<col [^>]*min="(\d+)"[^>]*max="(\d+)"[^>]*width="([\d.]+)"', xml)]
    return out

def write_large_miso_file(path: Path, sheets: dict, base: Path | None = None, cover_from_base: bool = False):
    """Like write_miso_file, for large files: the Cover (and other non-data sheets) are copied from the existing
    file or the base file cell by cell (values, formulas, styles, column widths) without loading the large data
    sheets, and everything is written in streaming mode. Data sheets get frozen panes at the first year column."""
    from copy import copy
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.utils import get_column_letter
    has_base = base is not None and base.exists()
    source = base if cover_from_base and has_base else path if path.exists() else base if has_base else None
    widths = _column_widths(source) if source else {}
    wb = Workbook(write_only=True)
    done = set()

    def data_sheet(title, df):
        ws = wb.create_sheet(title)
        for a, b, w in widths.get(title, []):
            for i in range(a, b + 1):
                ws.column_dimensions[get_column_letter(i)].width = w
        first_year = next((i for i, c in enumerate(df.columns) if str(c).isdigit()), 0)
        ws.freeze_panes = f'{get_column_letter(first_year + 1)}2'
        ws.append([str(c) for c in df.columns])
        for row in df.itertuples(index=False):
            ws.append(list(row))

    if source:
        ro = load_workbook(source, read_only=True)
        for name in ro.sheetnames:
            key = next((k for k, v in SHEET_NAMES.items() if name.lower() in v), None)
            if key in sheets:
                data_sheet(name, sheets[key])
                done.add(key)
                continue
            ws = wb.create_sheet(name)
            for a, b, w in widths.get(name, []):
                for i in range(a, b + 1):
                    ws.column_dimensions[get_column_letter(i)].width = w
            cover = name.lower() == 'cover'
            for r, row in enumerate(ro[name].iter_rows(), start=1):
                cells = []
                for c in row:
                    value = getattr(c, 'value', None)
                    wc = WriteOnlyCell(ws, value=date.today() if cover and (r, getattr(c, 'column', 0)) == (12, 2) else value)
                    if getattr(c, 'has_style', False):
                        for attr in ('font', 'fill', 'border', 'alignment', 'protection'):
                            setattr(wc, attr, copy(getattr(c, attr)))
                        wc.number_format = c.number_format
                    if cover and (r, getattr(c, 'column', 0)) == (12, 2):
                        wc.number_format = 'DD.MM.YY'
                    cells.append(wc)
                ws.append(cells)
        ro.close()
    for key, df in sheets.items():
        if key not in done:
            data_sheet(key, df)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

#%% Write all

def _safe(name):
    return ''.join(c if c.isalnum() or c in ' -_+' else '_' for c in name).strip()

def write_outputs(results: dict, base, s: Settings) -> None:
    out = s.output_dir
    shares = cohort_shares(s)
    src = load_sources(s)
    main = out / 'MISO_inputs'
    stock_base, init_base = find_existing(main, 'stock'), find_existing(main, 'init')
    energy_base = find_existing(main, 'energy')
    energy_inputs = load_energy_inputs(s)
    log.info('New MISO2 files are copied from: %s, %s, %s', stock_base or '-', init_base or '-', energy_base or '-')
    if stock_base is None or init_base is None:
        log.warning('No existing MISO2 file found in %s/Scenarios/sc_baseline/ or %s/: files of new scenarios '
                    'are created without Cover sheet', main, main)
    long, energy_totals = [], []
    for name, r in results.items():
        for sector, table in r.tables.items():
            long.append(table.melt(id_vars=['MISO2_country', 'End_use_sector', 'Unit'], var_name='Year',
                                   value_name='Value').assign(Scenario=name, Sector=sector))
        stock = function_stock(r.tables, s, src, name)
        init = initialization(stock['values'], base.buildings, shares, s, r.buildings.new_floor_area)
        init = initialization_sheets(init, stock, s)
        # One folder per scenario; files are updated in place, or created from an existing
        # MISO2 file (Cover and other sheets kept)
        folder = main / 'Scenarios' / _safe(name)
        write_miso_file(folder / STOCK_FILE, stock, base=stock_base)
        write_miso_file(folder / INIT_FILE, init, base=init_base)
        # Operational energy: MISO2 file = GJ per functional unit (MISO2 multiplies by the function stock);
        # totals (GJ per FU x stock) go to results/operational_energy.csv
        values = stock['values']
        op = operational_energy(r, energy_inputs, list(values['End_use_sector']), s)
        units = values.set_index('End_use_sector')
        n = units.reindex(op['End_use_sector'])[[str(y) for y in range(s.base_year, s.end_year + 1)]]
        op['Stock'] = [n.iat[i, y - s.base_year] for i, y in enumerate(op['Year'])]
        write_large_miso_file(folder / ENERGY_FILE, energy_sheets(op, s.region, s, name), base=energy_base,
                              cover_from_base=True)
        energy_totals.append(op.assign(Scenario=name, Total_PJ=op['Value'] * op['Stock'] / 1e6))
        r.energy = op
        log.info('Outputs written for %s', name)

    (out / 'results').mkdir(parents=True, exist_ok=True)
    long = pd.concat(long, ignore_index=True)
    long['Year'] = long['Year'].astype(int)
    long[['Scenario', 'Sector', 'End_use_sector', 'Unit', 'Year', 'Value']].to_csv(
        out / 'results' / 'results_long.csv', index=False)
    energy = pd.concat(energy_totals, ignore_index=True)
    energy.assign(Total_GJ=energy['Value'] * energy['Stock']).rename(columns={'Value': 'GJ_per_FU'})[
        ['Scenario', 'End_use_sector', 'Energy_carrier', 'Year', 'GJ_per_FU', 'Stock', 'Total_GJ']].to_csv(
        out / 'results' / 'operational_energy.csv', index=False)
    write_summary(results, out / 'results' / 'summary.xlsx', energy)

def write_summary(results: dict, path: Path, energy: pd.DataFrame | None = None):
    def stack(get):
        return pd.concat([get(r).assign(Scenario=n) for n, r in results.items()], ignore_index=True)

    key = []
    for n, r in results.items():
        a = r.buildings.annual.set_index('Year')
        series = {('Floor area stock', 'million m2'): a['Cumulative_Stock'] / 1e6,
                  ('Floor area per capita', 'm2/cap'): a['Per_Capita'],
                  ('Historic stock, not renovated', 'million m2'): a['Not_Renovated_Stock'] / 1e6,
                  ('Historic stock, thermally renovated', 'million m2'): a['Renovated_Stock'] / 1e6,
                  ('New construction stock', 'million m2'): a['New_Construction_Stock'] / 1e6,
                  ('Thermally renovated share of historic stock', '%'):
                      a['Renovated_Stock'] / (a['Renovated_Stock'] + a['Not_Renovated_Stock']) * 100,
                  ('Thermally renovated share of total stock (incl. new)', '%'):
                      (a['Renovated_Stock'] + a['New_Construction_Stock']) / a['Cumulative_Stock'] * 100,
                  ('Space heating useful heat', 'TWh'): r.heating.groupby('Year')['Space_heating'].sum() / 1000,
                  ('Hot water useful heat', 'TWh'): r.heating.groupby('Year')['Hot_water'].sum() / 1000,
                  ('Heating final energy (space heating and hot water)', 'TWh'):
                      r.heating.groupby('Year')['Final_energy'].sum() / 1000,
                  ('Heating capacity', 'GW'): r.heating.groupby('Year')['Capacity'].sum() / 1000,
                  ('Space cooling useful energy', 'TWh'): r.cooling.groupby('Year')['Useful_cooling'].sum() / 1000,
                  ('Space cooling final energy', 'TWh'): r.cooling.groupby('Year')['Final_energy'].sum() / 1000,
                  ('Space cooling capacity', 'GW'): r.cooling.groupby('Year')['Capacity'].sum() / 1000,
                  **({('Operational energy (all end uses)', 'PJ'):
                      energy[energy['Scenario'] == n].groupby('Year')['Total_PJ'].sum()} if energy is not None else {}),
                  ('Appliances', 'million units'): r.buildings.appliances.groupby('Year')['Value'].sum() / 1e6,
                  ('Vehicles', 'million units'): r.vehicles.vehicles.groupby('Year')['Value'].sum() / 1e6,
                  ('Electric vehicles', 'million units'):
                      r.vehicles.by_fuel.query("Fuel_type == 'Electric'").groupby('Year')['Value'].sum() / 1e6,
                  ('Infrastructure area', 'million m2'): r.infrastructure.groupby('Year')['Value'].sum() / 1e6}
        for (label, unit), v in series.items():
            key.append({'Scenario': n, 'Indicator': label, 'Unit': unit,
                        **{str(y): v.get(y) for y in (2024, 2030, 2040, 2050, 2060, 2100)}})

    traffic = pd.concat([pd.DataFrame({'Scenario': n, 'Type': t, 'Year': v.index, 'Billion pkm/tkm': v.values})
                         for n, r in results.items() for t, v in r.vehicles.traffic.items()], ignore_index=True)
    sheets = {
        'Scenarios': pd.DataFrame([{'Scenario': n, 'Name': r.scenario.title, 'Description': r.scenario.description,
                                    'Measures': '; '.join(r.scenario.measures)} for n, r in results.items()]),
        'Key figures': pd.DataFrame(key),
        'Buildings': stack(lambda r: r.buildings.annual),
        'Building renovation': stack(lambda r: r.buildings.renovation.groupby(
            ['Year', 'Type_lv2', 'Renovation_status'], as_index=False)['Value'].sum()),
        'Heating': stack(lambda r: r.heating.groupby(['Year', 'Heating_system'], as_index=False)[
            ['Space_heating', 'Hot_water', 'Useful_heat', 'Final_energy', 'Ambient_heat', 'Capacity']].sum().rename(columns={
            'Space_heating': 'Space_heating_GWh', 'Hot_water': 'Hot_water_GWh', 'Useful_heat': 'Useful_heat_GWh', 'Final_energy': 'Final_energy_GWh', 'Ambient_heat': 'Ambient_heat_GWh',
            'Capacity': 'Capacity_MW'})),
        'Cooling': stack(lambda r: r.cooling.groupby(['Year', 'Cooling_system'], as_index=False)[
            ['Useful_cooling', 'Final_energy', 'Capacity']].sum().rename(columns={
            'Useful_cooling': 'Useful_cooling_GWh', 'Final_energy': 'Final_energy_GWh', 'Capacity': 'Capacity_MW'})),
        'Operational energy': (energy.assign(Group=energy['End_use_sector'].str.split('_').str[0])
                               .groupby(['Scenario', 'Year', 'Group', 'Energy_carrier'], as_index=False)['Total_PJ'].sum()
                               if energy is not None else pd.DataFrame()),
        'Appliances': stack(lambda r: r.buildings.appliances),
        'Traffic': traffic,
        'Vehicles by fuel': stack(lambda r: r.vehicles.by_fuel),
        'Infrastructure': stack(lambda r: r.infrastructure),
    }
    with pd.ExcelWriter(path, engine='openpyxl') as xw:
        for name, df in sheets.items():
            if 'Scenario' in df.columns:
                df = df[['Scenario'] + [c for c in df.columns if c != 'Scenario']]
            if len(df) >= 1_048_576:   # Excel row limit: write as CSV instead
                csv = path.with_name(f'summary_{name.replace(" ", "_").lower()}.csv')
                df.to_csv(csv, index=False)
                df = pd.DataFrame({'Note': [f'Too many rows for Excel ({len(df):,}); written to {csv.name}']})
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes = 'B2'
            for col in ws.columns:
                width = max(len(str(c.value or '')) for c in list(col)[:100])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
