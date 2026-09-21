#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Combine building, appliance, vehicle, and infrastructure scenario
         outputs into a single MISO2-ready table per scenario.
'''

import os
import pandas as pd
from openpyxl import load_workbook

#%% Universal settings

main_path = os.getcwd()

#%% Import configuration

# Input files (manually specified, Baseline only)
input_files = [
    os.path.join('output', 'scenarios', 'buildings',      'MISO2_Baseline.csv'),
    os.path.join('output', 'scenarios', 'vehicles',       'MISO2_Baseline.csv'),
    os.path.join('output', 'scenarios', 'infrastructure', 'MISO2_Baseline.csv'),
]

# MISO2 end-use renaming
build_rename = {
    'R_SFH':                            'build_r_sfh',
    'R_MFH':                            'build_r_mfh',
    'R_APB':                            'build_r_apb',
    'R_IHH':                            'build_nr',
    'NR_public':                        'build_nr',
    'NR_indust':                        'build_nr',
    'NR_trafcom':                       'build_nr',
    'NR_retail':                        'build_nr',
    'NR_office':                        'build_nr',
    'NR_hotels':                        'build_nr',
}

hha_rename = {
    'Fridge':                           'hha_fridge',
    'Refrigerator':                     'hha_fridge',
    'Tumble Dryer':                     'hha_dryer',
    'Dishwasher':                       'hha_dishwasher',
    'Washing Machine':                  'hha_washing_machine',
    'TV':                               'hha_tv',
    'Freezer':                          'hha_freezer',
}

veh_rename = {
    'Cars_electric':                    'veh_car_bev',
    'Cars_fossil':                      'veh_car_icev',
    'Cars_hybrid':                      'veh_car_hev',
    'Motorcycles_electric':             'veh_motorcycles_icev',
    'Motorcycles_fossil':               'veh_motorcycles_bev',
    'Moped_fossil':                     'veh_moped_icev',
    'Moped_electric':                   'veh_moped_bev',
    'Trucks_fossil':                    'veh_trucks_icev',
    'Trucks_electric':                  'veh_trucks_bev',
    'Trucks_hybrid':                    'veh_trucks_hev',
    'Buses_fossil':                     'veh_buses_icev',
    'Buses_electric':                   'veh_buses_bev',
    'Vehicles_other_fossil':            'veh_other_icev',
    'Vehicles_other_electric':          'veh_other_bev',
    'Vehicles_other_hybrid':            'veh_other_hev',
    'Trailers':                         'veh_trailer',
    'Bicycles':                         'veh_bicycles',
    'E_bikes_electric':                 'veh_e_bikes',
    'Railway_passenger_train_electric': 'veh_railway_passenger_train_electric',
    'Railway_passenger_train_fossil':   'veh_railway_passenger_train_fossil',
    'Railway_passenger_car':            'veh_railway_passenger_car',
    'Railway_freight_train_electric':   'veh_railway_freight_train_electric',
    'Railway_freight_train_fossil':     'veh_railway_freight_train_fossil',
    'Railway_freight_car':              'veh_railway_freight_car',
    'Subway_car':                       'veh_subway_car',
    'Subway_train_electric':            'veh_subway_train_electric',
    'Tram_car':                         'veh_tram_car',
    'Tram_train_electric':              'veh_tram_train_electric',
}

infra_rename = {
    'motorway':                         'infra_motorway',
    'motorway_bridge':                  'infra_motorway_bridge',
    'motorway_tunnel':                  'infra_motorway_tunnel',
    'primary':                          'infra_primary',
    'primary_bridge':                   'infra_primary_bridge',
    'primary_tunnel':                   'infra_primary_tunnel',
    'secondary':                        'infra_secondary',
    'secondary_bridge':                 'infra_secondary_bridge',
    'secondary_tunnel':                 'infra_secondary_tunnel',
    'tertiary':                         'infra_tertiary',
    'tertiary_bridge':                  'infra_tertiary_bridge',
    'tertiary_tunnel':                  'infra_tertiary_tunnel',
    'local':                            'infra_local',
    'local_bridge':                     'infra_local_bridge',
    'local_tunnel':                     'infra_local_tunnel',
    'track':                            'infra_rural',
    'track_bridge':                     'infra_rural_bridge',
    'track_tunnel':                     'infra_rural_tunnel',
    'parking_surface':                  'infra_parking_surface',
    'parking_underground':              'infra_parking_underground',
    'parking_building':                 'infra_parking_building',
    'gas_station_building':             'infra_fueling_station',
    'charging_station':                 'infra_charging_station',
    'railway':                          'infra_railway',
    'railway_bridge':                   'infra_railway_bridge',
    'railway_tunnel':                   'infra_railway_tunnel',
    'railway_building':                 'infra_railway_station',
    'railway_building_platform':        'infra_railway_station_platform',
    'rail_other':                       'infra_rail_other',
    'subway':                           'infra_subway_groundlevel',
    'subway_bridge':                    'infra_subway_elevated',
    'subway_tunnel':                    'infra_subway_underground',
    'subway_building':                  'infra_subway_station',
    'tram':                             'infra_tram',
}

combined_rename = {**build_rename, **hha_rename, **veh_rename, **infra_rename}

# End-use sectors to aggregate into one row (sum across years)
aggregate_groups = {
    'infra_railway': ['infra_railway', 'infra_rail_other'],
}

combined_path = os.path.join('output', 'scenarios', 'combined')
os.makedirs(combined_path, exist_ok=True)

#%% Read and combine

def load_file(path):
    if not os.path.exists(path):
        print(f"  ! Missing: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, sep=';', decimal=',')

frames = []
for path in input_files:
    df = load_file(path)
    if not df.empty:
        frames.append(df)

if frames:
    combined = pd.concat(frames, ignore_index=True)
    combined['End_use_sector'] = combined['End_use_sector'].replace(combined_rename)

    # Aggregate selected end-use sectors (sum their values across all year columns)
    for target, members in aggregate_groups.items():
        rows = combined[combined['End_use_sector'].isin(members)]
        if rows.empty:
            continue

        numeric_cols = [c for c in combined.columns if c not in ('MISO2_country', 'End_use_sector')]
        aggregated = rows.groupby('MISO2_country', as_index=False)[numeric_cols].sum()
        aggregated['End_use_sector'] = target

        # Drop original members, append aggregated row
        combined = combined[~combined['End_use_sector'].isin(members)]
        combined = pd.concat([combined, aggregated], ignore_index=True)

    # Group all non-residential building rows into a single 'build_nr' row
    build_nr_members = ['build_nr']
    rows = combined[combined['End_use_sector'].isin(build_nr_members)]
    if not rows.empty:
        numeric_cols = [c for c in combined.columns if c not in ('MISO2_country', 'End_use_sector')]
        aggregated = rows.groupby('MISO2_country', as_index=False)[numeric_cols].sum()
        aggregated['End_use_sector'] = 'build_nr'

        if len(rows) > 1:
            combined = combined[~combined['End_use_sector'].isin(build_nr_members)]
            combined = pd.concat([combined, aggregated], ignore_index=True)

    if 'Unit' in combined.columns:
        combined = combined.drop(columns=['Unit'])

    # Sort alphabetically by End_use_sector before export
    combined = combined.sort_values('End_use_sector').reset_index(drop=True)

    # Append one dummy row for 'power_plants' (value 1 in every year column)
    year_cols = [c for c in combined.columns if c not in ('MISO2_country', 'End_use_sector')]
    power_row = {'MISO2_country': 'Austria', 'End_use_sector': 'power_plants'}
    for c in year_cols:
        power_row[c] = 1
    combined = pd.concat([combined, pd.DataFrame([power_row])], ignore_index=True)

    # Re-sort so 'power_plants' lands in its alphabetical position
    combined = combined.sort_values('End_use_sector').reset_index(drop=True)

    print(f"[Baseline] {len(combined)} rows, {combined['End_use_sector'].nunique()} sectors")
else:
    combined = pd.DataFrame()
    print("[Baseline] No input files found.")

#%% Export

if not combined.empty:
    target_xlsx = os.path.join('output', 'MISO_inputs', 'MISO2_Function_Stock_v1.xlsx')
    sheet_name  = 'values'

    if not os.path.exists(target_xlsx):
        raise FileNotFoundError(f"Target workbook not found: {target_xlsx}")

    wb = load_workbook(target_xlsx)
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"Sheet '{sheet_name}' not found in {target_xlsx}")
    ws = wb[sheet_name]

    # Clear only the data area (rows 2 onward). Row 1 (headers) and all
    # cell/column formatting on the sheet are preserved.
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.value = None

    # Write data rows starting at row 2, column 1
    for r_idx, row in enumerate(combined.itertuples(index=False), start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    wb.save(target_xlsx)
    print(f"  ✓ Wrote '{sheet_name}' sheet in {target_xlsx}")

print("\nCOMBINED EXPORT COMPLETE")