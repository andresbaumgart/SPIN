"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Model run (base year -> scenarios -> outputs)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from .baseyear import BaseYear, get_base_year
from .buildings import BuildingResult, project_appliances, project_buildings
from .config import ModelError, Settings
from .data import load_drivers
from .cooling import load_cooling_inputs, project_cooling
from .heating import load_heating_inputs, project_heating
from .export import sector_tables, write_outputs
from .infrastructure import project_infrastructure
from .scenarios import BASELINE, Scenario, load_scenarios
from .vehicles import VehicleResult, project_vehicles

log = logging.getLogger(__name__)

@dataclass
class ScenarioResult:
    scenario: Scenario
    buildings: BuildingResult
    vehicles: VehicleResult
    infrastructure: object             # DataFrame: Type_lv2, Year, Value
    heating: object = None             # DataFrame: Year, Type_lv2, Renovation_status, Heating_system, GWh / MW
    cooling: object = None             # DataFrame: Year, Type_lv2, Renovation_status, Cooling_system, GWh / MW
    energy: object = None              # DataFrame: End_use_sector, Energy_carrier, Year, Value (GJ/FU/yr) - set by export
    tables: dict = field(default_factory=dict)   # wide MISO-format tables per sector

class Model:
    def __init__(self, root):
        self.settings = Settings(root)
        self.scenarios = load_scenarios(self.settings.parameter_file)
        if not self.settings.renovation_rates:
            log.warning("No 'Renovation rate <year>' rows on the settings sheet: no thermal renovation in the baseline")
        for sc in self.scenarios.values():     # reference renovation rates (settings sheet) apply to all scenarios
            sc.buildings.renovation = self.settings.renovation_rates
        self.drivers = load_drivers(self.settings)
        self.heating_inputs = load_heating_inputs(self.settings)
        self.cooling_inputs = load_cooling_inputs(self.settings)
        self._base = None

    def base_year(self) -> BaseYear:
        if self._base is None:
            self._base = get_base_year(self.settings)
        return self._base

    def run_scenario(self, scenario) -> ScenarioResult:
        sc = self.scenarios[scenario] if isinstance(scenario, str) else scenario
        s, d, base = self.settings, self.drivers, self.base_year()
        log.info('Scenario: %s', sc.name)

        bld = project_buildings(sc.buildings, base.buildings, d.pop_smooth, s.end_year, s.renovated_share,
                                s.non_renovatable)
        bld.appliances = project_appliances(sc.buildings, bld.annual, base.appliances, base.households)
        veh = project_vehicles(sc.mobility, d, s.base_year, s.end_year)
        infra = project_infrastructure(base.infrastructure, veh.vkm, veh.by_fuel, s.base_year, s.end_year,
                                       s.station_floor)
        heat = project_heating(bld.renovation, sc.heating, self.heating_inputs, s)
        cool = project_cooling(bld.renovation, self.cooling_inputs)
        r = ScenarioResult(sc, bld, veh, infra, heat, cool)
        r.tables = sector_tables(r, s)
        return r

    def run(self) -> dict:
        """Run the scenarios marked Run = yes on the 'scenarios' sheet."""
        names = [n for n, sc in self.scenarios.items() if sc.run]
        if not names:
            raise ModelError("No scenario has Run = yes on the 'scenarios' sheet")
        return {n: self.run_scenario(n) for n in names}

    def export(self, results):
        write_outputs(results, self.base_year(), self.settings)

    def plot(self, results):
        from .plots import plot_all
        plot_all(results, self.settings)

def run(root) -> dict:
    """Run everything: scenarios marked Run = yes, all outputs and figures."""
    import time
    logging.basicConfig(level=logging.INFO, format='%(levelname)-7s %(message)s', force=True)
    t0 = time.time()
    model = Model(root)
    results = model.run()
    model.export(results)
    model.plot(results)

    w = max(32, max(len(n) for n in results) + 2)
    print(f"\n{'Scenario':<{w}}{'Floor area 2100':>16}{'Vehicles 2100':>15}{'Infra 2100':>13}{'Heating 2050':>14}{'Cooling 2050':>14}")
    print(f"{'':<{w}}{'(million m2)':>16}{'(million)':>15}{'(mill. m2)':>13}{'(TWh final)':>14}{'(GW)':>14}")
    for name, r in results.items():
        fa = r.buildings.annual['Cumulative_Stock'].iloc[-1] / 1e6
        veh = r.vehicles.vehicles.groupby('Year')['Value'].sum().iloc[-1] / 1e6
        inf = r.infrastructure.groupby('Year')['Value'].sum().iloc[-1] / 1e6
        heat = r.heating.query('Year == 2050')['Final_energy'].sum() / 1000
        cool = r.cooling.query('Year == 2050')['Capacity'].sum() / 1000
        print(f'{name:<{w}}{fa:>16.1f}{veh:>15.2f}{inf:>13.1f}{heat:>14.1f}{cool:>14.2f}')
    print(f'\nDone in {time.time() - t0:.0f} s. Outputs in {model.settings.output_dir}')
    return results
