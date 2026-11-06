"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Settings and input file locations
"""

from __future__ import annotations
import re
from pathlib import Path
import pandas as pd

class ModelError(ValueError):
    """Missing or invalid settings, input files or scenario definitions."""

# File locations
FILES = {
    'population':            'data_POP.xlsx',
    'gdp':                   'data_GDP.xlsx',
    'traffic':               'data_pkm_tkm.xlsx',
    'vehicle_fleet':         'data_vehicle_fleet.xlsx',
    'vehicle_fuel_shares':   'data_vehicle_fleet_fuel_type.xlsx',
    'vehicle_occupancy':     'data_vehicle_occupancy.xlsx',              # pkm/vkm, tkm/vkm -> vehicle-km
    'appliance_penetration': 'data_appliance_penetration_rates.xlsx',
    'hc_demand':             'data_heating_cooling_demand.xlsx',         # space heating, hot water, cooling (per m2)
    'hc_shares':             'data_heating_cooling_system_shares.xlsx',  # heating / cooling system mix
    'hc_systems':            'data_heating_cooling_systems.xlsx',        # efficiency, full-load hours
    'degree_days':           'data_degree_days.xlsx',
    'operational_energy':    'data_operational_energy.xlsx',            # energy use per functional unit
    'installed_capacity':    'data_installed_capacity.xlsx',
    'statcube':              ('StatCube/Floor_area', '*.csv', 'all'),   
    'household_size':        ('StatCube/Households', '*.xlsx', 'one'), 
    'glomis':                ('GLOMIS', '*.parquet', 'one'),
    'miso2_cohorts':         ('MISO2', '*.parquet', 'one'),
}

# Setting name on the 'settings' sheet -> (attribute, default)
SETTINGS = {
    'Region':                     ('region',		'Austria'),
    'Country code':               ('country_code',	'AUT'),
    'Base year':                  ('base_year', 	2024),
    'End year':                   ('end_year', 		2100),
    'Density factor "Under"':     ('density_under', 	0.80),
    'Density factor "and over"':  ('density_over', 	1.20),
    'Fuelling station minimum':   ('station_floor', 	0.3),
    'MISO2 cohort year':          ('cohort_year', 	2022),
    'Non-renovatable share':      ('non_renovatable', 	0.05),
    'Climate scenario':           ('climate_scenario', 	'RCP4.5'),
    'Heating calibration target': ('heating_target', 	0.0),
    'Heating oversizing factor':  ('heating_oversizing', 1.2),
    'Heating system lifetime':    ('heating_lifetime', 	20),
    'Cooling demand scenario':    ('cooling_scenario', 	'WEM'),
}


class Settings:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.input_dir = self.root / 'input'
        self.data_dir = self.input_dir / 'data'
        self.output_dir = self.root / 'output'
        self.parameter_file = self.input_dir / 'scenario_parameters.xlsx'
        if not self.parameter_file.exists():
            raise ModelError(f'Parameter file not found: {self.parameter_file}')

        values = {}
        with pd.ExcelFile(self.parameter_file) as xf:
            if 'settings' in xf.sheet_names:
                sheet = pd.read_excel(xf, 'settings')
                values = {str(k).strip(): v for k, v in zip(sheet['Setting'], sheet['Value']) if pd.notna(v)}
        for name, (attr, default) in SETTINGS.items():
            value = values.get(name, default)
            setattr(self, attr, type(default)(value))
        # text settings may carry an explanation after the key word, e.g. 'WEM (with existing measures, ...)'
        self.cooling_scenario = re.split(r'[\s(–-]', self.cooling_scenario.strip(), maxsplit=1)[0]
        # 'Renovation rate <year>' -> reference thermal renovation rate (all scenarios)
        self.renovation_rates = {int(m.group(1)): (float(v) / 100 if float(v) > 1 else float(v))
                                 for k, v in values.items()
                                 if (m := re.fullmatch(r'renovation rate (\d{4})', k.strip().lower()))}
        # 'Renovated share 2024: <construction period>' -> share of floor area thermally renovated in the base year
        prefix = 'renovated share'
        self.renovated_share = {k.split(':', 1)[1].strip(): float(v) for k, v in values.items()
                                if k.lower().startswith(prefix) and ':' in k}

    def input_path(self, key):
        """Path of an input file (or list of paths for 'all')."""
        spec = FILES[key]
        if isinstance(spec, str):
            return self.data_dir / spec
        folder, pattern, how = spec
        folder = self.data_dir / folder
        found = sorted(p for p in folder.glob(pattern) if not p.name.startswith(('~$', '.')))
        if not found:
            raise ModelError(f'No {pattern} file found in {folder}')
        if how == 'one':
            if len(found) > 1:
                raise ModelError(f'Expected one {pattern} file in {folder}, found {[p.name for p in found]}')
            return found[0]
        return found

    def require(self, *keys):
        """Fail early with one message listing every missing input file."""
        missing = []
        for key in keys:
            try:
                paths = self.input_path(key)
            except ModelError as exc:
                missing.append(f'  - {exc}')
                continue
            for p in paths if isinstance(paths, list) else [paths]:
                if not p.exists():
                    missing.append(f'  - {key}: {p}')
        if missing:
            raise ModelError('Missing input files:\n' + '\n'.join(missing))
