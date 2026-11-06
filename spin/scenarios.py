"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Measures and scenarios

Sheets 'buildings' (incl. heating) and 'mobility': one row = one measure (blank cell = no change),
identified by its 'Code' (e.g. reduced_office).
Sheet 'scenarios': matrix, one row = one scenario (identified by its 'Code', e.g. sc_baseline), one column
per measure code; 'x' = the scenario uses that measure (applied in column order). 'Run' = yes/no.
Scenario codes are used for all outputs (MISO2 folders, csv, summary, figures).
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
import pandas as pd
from .config import ModelError
from .mappings import BUILDING_TYPES, HEATING_SYSTEMS

log = logging.getLogger(__name__)

BASELINE = 'sc_baseline'                 # code of the Baseline scenario (required)
CODE = re.compile(r'[a-z][a-z0-9_]*')    # allowed codes: lower case letters, digits, underscores

#%% Phase-in

def phase_in_factor(year, start, end, target):
    """1.0 until start, then linearly to `target` at end."""
    if year <= start:
        return 1.0
    if year >= end:
        return target
    progress = (year - start) / (end - start)
    return 1.0 - (1.0 - target) * progress

def phase_in_share(year, start, end, target):
    """0.0 until start, then linearly to `target` at end."""
    if year <= start:
        return 0.0
    if year >= end:
        return target
    return target * ((year - start) / (end - start))

#%% Parameters

@dataclass
class Timed:
    value: float
    start: int
    end: int

@dataclass
class Conversion:
    sources: list
    targets: list
    rate: float
    mode: str  # 'type' or 'vacant'
    start: int
    end: int

@dataclass
class BuildingParams:
    floor_space: dict = field(default_factory=dict)
    urban_share: float | None = None
    conversions: list = field(default_factory=list)
    sharing: Timed | None = None
    households_follow: str = 'floor area'
    renovation: dict | None = None      # {year: thermal renovation rate} (settings sheet), interpolated in between
    renovation_target: int | None = None   # year by which all renovatable historic stock is renovated

    def renovation_rate(self, year):
        """Thermal renovation rate in a year: linear between the given years, constant outside."""
        if not self.renovation:
            return 0.0
        years = sorted(self.renovation)
        if year <= years[0]:
            return self.renovation[years[0]]
        if year >= years[-1]:
            return self.renovation[years[-1]]
        for y0, y1 in zip(years, years[1:]):
            if y0 <= year <= y1:
                return self.renovation[y0] + (self.renovation[y1] - self.renovation[y0]) * (year - y0) / (y1 - y0)

    def floor_space_factor(self, btype, year):
        f = 1.0
        for t in self.floor_space.get(btype, []):
            f = f * phase_in_factor(year, t.start, t.end, t.value)
        return f

@dataclass
class MobilityParams:
    demand: list = field(default_factory=list)
    pkm_shift: Timed | None = None
    tkm_shift: Timed | None = None
    electrification: dict = field(default_factory=dict)
    occupancy: dict = field(default_factory=dict)   # vehicle type -> [Timed]: occupancy / load factor change (multiply)
    mileage: dict = field(default_factory=dict)     # vehicle type -> [Timed]: change of km per vehicle (multiply)

    def mileage_factor(self, vtype, year):
        f = 1.0
        for t in self.mileage.get(vtype, []):
            f = f * phase_in_factor(year, t.start, t.end, t.value)
        return f

    def occupancy_factor(self, vtype, year):
        f = 1.0
        for t in self.occupancy.get(vtype, []):
            f = f * phase_in_factor(year, t.start, t.end, t.value)
        return f

    def demand_factor(self, year):
        f = 1.0
        for t in self.demand:
            f = f * phase_in_factor(year, t.start, t.end, t.value)
        return f

@dataclass
class HeatingMeasure:
    targets: dict          # {heating system: target share}; systems not listed share the rest (base-year proportions)
    statuses: list         # renovation statuses it applies to ([] = all)
    types: list            # building types it applies to ([] = all)
    start: int
    end: int

@dataclass
class HeatingParams:
    measures: list = field(default_factory=list)   # HeatingMeasure (heating system shares)

@dataclass
class Scenario:
    name: str                       # code, e.g. sc_baseline (used in all outputs)
    title: str = ''                 # readable name, e.g. Baseline
    description: str = ''
    measures: list = field(default_factory=list)
    run: bool = True
    buildings: BuildingParams = field(default_factory=BuildingParams)
    mobility: MobilityParams = field(default_factory=MobilityParams)
    heating: HeatingParams = field(default_factory=HeatingParams)

    @property
    def sectors(self):
        """Sectors this scenario changes compared to the Baseline: subset of {'buildings', 'mobility'}."""
        out = set()
        if self.buildings != BuildingParams(renovation=self.buildings.renovation):
            out.add('buildings')
        if self.mobility != MobilityParams():
            out.add('mobility')
        if self.heating != HeatingParams():
            out.add('heating')
        return out

#%% Read excel

def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        v = v.strip().replace(',', '.')
        if v in ('', '-'):
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ModelError(f'Not a number: {v!r}') from None

def _text(v):
    return '' if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()

def _list(v):
    return [x.strip() for x in _text(v).split(';') if x.strip() and x.strip() != '-']

def _sheet(path, name):
    """Rows of a sheet that have a code; codes are checked (format, unique)."""
    df = pd.read_excel(path, sheet_name=name)
    df.columns = [str(c).strip() for c in df.columns]
    if 'Code' not in df.columns:
        raise ModelError(f'{path.name}[{name}]: column "Code" missing')
    df = df[df['Code'].map(_text) != ''].copy()
    df['Code'] = df['Code'].map(_text)
    bad = [c for c in df['Code'] if not CODE.fullmatch(c)]
    if bad:
        raise ModelError(f'{path.name}[{name}]: invalid code(s) {bad}: use lower case letters, digits and "_" only')
    twice = sorted(df['Code'][df['Code'].duplicated()].unique())
    if twice:
        raise ModelError(f'{path.name}[{name}]: code(s) used twice: {twice}')
    return df

def _apply_building_row(r, p: BuildingParams, label):
    start, end = int(_num(r.get('Start Year')) or 2024), int(_num(r.get('End Year')) or 2060)
    for t in BUILDING_TYPES:
        f = _num(r.get(t))
        if f is not None and f != 1:
            p.floor_space.setdefault(t, []).append(Timed(f, start, end))
    u = _num(r.get('Urban Share'))
    if u is not None:
        p.urban_share = u
    sources = _list(r.get('Conversion Source'))
    if sources:
        mode = _text(r.get('Conversion Mode')).lower() or 'type'
        targets = _list(r.get('Conversion Target'))
        if mode not in ('type', 'vacant'):
            raise ModelError(f"{label}: Conversion Mode must be 'type' or 'vacant'")
        if mode == 'type' and not targets:
            raise ModelError(f'{label}: Conversion Target is required for mode "type"')
        bad = [t for t in sources + targets if t not in BUILDING_TYPES]
        if bad:
            raise ModelError(f'{label}: unknown building type(s) {bad}')
        p.conversions.append(Conversion(sources, targets, _num(r.get('Conversion Rate')) or 0.0, mode, start, end))
    share = _num(r.get('Appliance Sharing'))
    if share:
        p.sharing = Timed(share, start, end)
    target = _num(r.get('Renovation Target Year'))
    if target is not None:
        p.renovation_target = int(target)
    follow = _text(r.get('Households Follow')).lower()
    if follow == 'population':
        p.households_follow = 'population'
    elif follow not in ('', 'floor area'):
        raise ModelError(f"{label}: Households Follow must be 'floor area' or 'population'")

# Occupancy / load factor measures: column -> vehicle type (factor on the occupancy in End Year, e.g. 1.3 = +30 %)
OCCUPANCY_COLUMNS = {'Car Occupancy Factor': 'Cars', 'Bus Occupancy Factor': 'Buses', 'Truck Load Factor': 'Trucks'}
# Mileage measures: column -> vehicle type (factor on km per vehicle and year in End Year, e.g. 1.5 = +50 %)
MILEAGE_COLUMNS = {'Car Mileage Factor': 'Cars'}

ELECTRIFICATION_COLUMNS = {'car': 'Car Electrification', 'motorcycle': 'Motorcycle Electrification',
                           'bus': 'Bus Electrification', 'truck': 'Truck Electrification'}

def _apply_mobility_row(r, p: MobilityParams, label):
    start, end = int(_num(r.get('Start Year')) or 2024), int(_num(r.get('End Year')) or 2060)
    d = _num(r.get('Demand Reduction'))
    if d is not None and d != 1:
        p.demand.append(Timed(d, start, end))
    for attr, col in (('pkm_shift', 'PKM Shift to Rail'), ('tkm_shift', 'TKM Shift to Rail')):
        v = _num(r.get(col))
        if v:
            setattr(p, attr, Timed(v, start, end))
    for group, col in ELECTRIFICATION_COLUMNS.items():
        v = _num(r.get(col))
        if v:
            p.electrification[group] = Timed(v, start, end)
    for col, vtype in OCCUPANCY_COLUMNS.items():
        v = _num(r.get(col))
        if v is not None and v != 1:
            if v <= 0:
                raise ModelError(f'{label}: {col} must be > 0')
            p.occupancy.setdefault(vtype, []).append(Timed(v, start, end))
    for col, vtype in MILEAGE_COLUMNS.items():
        v = _num(r.get(col))
        if v is not None and v != 1:
            if v <= 0:
                raise ModelError(f'{label}: {col} must be > 0')
            p.mileage.setdefault(vtype, []).append(Timed(v, start, end))

HEATING_STATUSES = ('Not renovated', 'Thermally renovated', 'New construction')

def _apply_heating_row(r, p: HeatingParams, label):
    start, end = int(_num(r.get('Start Year')) or 2024), int(_num(r.get('End Year')) or 2060)
    targets = {}
    for system in HEATING_SYSTEMS:
        v = _num(r.get(system))
        if v is not None:
            targets[system] = v / 100 if v > 1 else v      # 40 means 40 %
    if not targets:
        return
    if sum(targets.values()) > 1 + 1e-6:
        raise ModelError(f'{label}: target shares add up to more than 100 %')
    statuses, types = _list(r.get('Renovation Status')), _list(r.get('Building Types'))
    bad = [x for x in statuses if x not in HEATING_STATUSES] + [x for x in types if x not in BUILDING_TYPES]
    if bad:
        raise ModelError(f'{label}: unknown renovation status / building type {bad}')
    p.measures.append(HeatingMeasure(targets, statuses, types, start, end))

def load_scenarios(path) -> dict[str, Scenario]:
    """All scenarios on the 'scenarios' sheet, with their parameters resolved."""
    if not path.exists():
        raise ModelError(f'Scenario workbook not found: {path}')
    measures = {}
    for sheet, apply in (('buildings', _apply_building_row), ('mobility', _apply_mobility_row)):
        for _, r in _sheet(path, sheet).iterrows():
            if r['Code'] in measures:
                raise ModelError(f"Measure code {r['Code']!r} used on both the buildings and the mobility sheet")
            measures[r['Code']] = (sheet, apply, r)

    # Scenarios sheet = matrix: one row per scenario, one column per measure code, 'x' = measure is used
    sheet = _sheet(path, 'scenarios')
    fixed = {'Code', 'Scenario', 'Run', 'Description'}
    columns = [c for c in sheet.columns if c not in fixed and not c.startswith('Unnamed')]
    unknown = [c for c in columns if c not in measures]
    if unknown:
        raise ModelError(f"'scenarios' sheet: column(s) {unknown} are not measure codes on the buildings or "
                         'mobility sheet (check the spelling)')
    rows = {r['Code']: r for _, r in sheet.iterrows()}
    if BASELINE not in rows:
        raise ModelError(f"The 'scenarios' sheet needs a row with code {BASELINE!r}")

    def ticked(v):
        return _text(v).lower() in ('x', 'yes', 'y', '1', '1.0', 'true')

    scenarios = {}
    for code, r in rows.items():
        run = _text(r.get('Run')).lower() in ('yes', 'y', 'x', 'true', '1', '1.0')
        used = [c for c in columns if ticked(r.get(c))]     # in column order
        s = Scenario(code, _text(r.get('Scenario')), _text(r.get('Description')), used, run)
        for m in s.measures:
            sheet, apply, row = measures[m]
            if sheet == 'buildings':    # building measures can also set the heating system mix
                apply(row, s.buildings, f'Measure {m!r}')
                _apply_heating_row(row, s.heating, f'Measure {m!r}')
            else:
                apply(row, s.mobility, f'Measure {m!r}')
        scenarios[code] = s

    return scenarios
