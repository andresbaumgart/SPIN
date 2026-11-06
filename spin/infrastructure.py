"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Mobility infrastructure projection

Each infrastructure type grows with the vehicle-km of the modes using it (traffic / occupancy,
relative to the base year) and is never demolished (running maximum).
Charging stations follow the electric road fleet; fuelling stations follow the
fossil + hybrid road fleet but stay at least at a minimum share of the base year.
"""

from __future__ import annotations
import pandas as pd
from .mappings import INFRA_FUEL_LINK, INFRA_TO_TRAFFIC, STATION_VEHICLES

def project_infrastructure(base: pd.DataFrame, vkm: dict, by_fuel: pd.DataFrame, base_year=2024,
                           end_year=2100, station_floor=0.3) -> pd.DataFrame:
    years = list(range(base_year, end_year + 1))
    road = by_fuel[by_fuel['Type_lv2'].isin(STATION_VEHICLES)] if len(by_fuel) else by_fuel
    fleet = road.groupby(['Fuel_type', 'Year'])['Value'].sum() if len(road) else pd.Series(dtype=float)
    base = base.groupby('Type_lv2', as_index=False)['Value'].sum()   # national total per type
    rows = []
    for _, b in base.iterrows():
        itype, base_value = b['Type_lv2'], b['Value']
        modes = [m for m in INFRA_TO_TRAFFIC.get(itype, []) if m in vkm]
        if not modes:
            continue
        driver = sum(vkm[m].reindex(years) for m in modes)
        values = (base_value * driver / driver[base_year]).cummax()

        fuels = INFRA_FUEL_LINK.get(itype)
        if fuels and len(fleet):
            vehicles = sum(fleet.get(f, pd.Series(0.0, index=years)).reindex(years, fill_value=0) for f in fuels)
            if vehicles[base_year] > 0:
                values = base_value * vehicles / vehicles[base_year]
                if itype == 'gas_station_building':
                    values = values.clip(lower=base_value * station_floor)
        rows += [{'Type_lv2': itype, 'Year': y, 'Value': v, 'Driver': '+'.join(modes)} for y, v in values.items()]
    return pd.DataFrame(rows)
