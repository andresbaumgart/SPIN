#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Vehicle fleet projections
'''

#%% General
#%%% Packages

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import linregress

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df.loc[:, 'Parameter':'Value']

def load_vehicle_data_with_fuel():
    # Vehicle counts by type and year (total fleet, no fuel split)
    file_path = os.path.join(main_path, 'output', 'interim', 'stocks_vehicles_base.parquet')
    if os.path.exists(file_path):
        return pd.read_parquet(file_path)
    return read_excel(os.path.join(main_path, 'input', 'data_vehicle_fleet.xlsx'), sheet_name='input')

def load_vehicle_fuel_shares():
    # Fuel shares for the base year (2024), one row per Type_lv2 x Fuel_type
    file_path = os.path.join(main_path, 'input', 'data_vehicle_fleet_fuel_type.xlsx')
    if not os.path.exists(file_path):
        return pd.DataFrame()
    df = read_excel(file_path, sheet_name='input')
    df = df[df['Year_from'] == 2024].copy()
    # Normalise NA labelling: blank cells -> 'NA'
    df['Fuel_type'] = df['Fuel_type'].fillna('NA').astype(str).replace({'nan': 'NA', 'NAN': 'NA', '': 'NA'})
    return df

######################################################################################################################################################
#%% Scenarios

def load_scenario_parameters(file_path, scenario_name):
    try:
        df_scenarios = pd.read_excel(file_path, sheet_name='mobility')
    except:
        return {'demand_reduction': 1.0, 'start_year': 2024, 'end_year': 2024, 
                'pkm_shift_to_rail': 0.0, 'tkm_shift_to_rail': 0.0,
                'car_electrification': 0.0, 'motorcycle_electrification': 0.0,
                'bus_electrification': 0.0, 'truck_electrification': 0.0}
    
    df_scenarios = df_scenarios[~df_scenarios['Scenario Name'].str.startswith(('Parameter', 'Percenrage'), na=False) & 
                                 df_scenarios['Scenario Name'].notna() & (df_scenarios['Scenario Name'] != '')]
    scenario = df_scenarios[df_scenarios['Scenario Name'] == scenario_name]
    
    if scenario.empty:
        return {'demand_reduction': 1.0, 'start_year': 2024, 'end_year': 2024, 
                'pkm_shift_to_rail': 0.0, 'tkm_shift_to_rail': 0.0,
                'car_electrification': 0.0, 'motorcycle_electrification': 0.0,
                'bus_electrification': 0.0, 'truck_electrification': 0.0}
    
    scenario = scenario.iloc[0]
    
    def get_param(col_name, default):
        if col_name in df_scenarios.columns:
            val = scenario.get(col_name, default)
            if isinstance(val, str):
                val = val.replace(',', '.').strip()
                if val == '-' or val == '': return default
                try: return float(val)
                except: return default
            return float(val) if pd.notna(val) else default
        return default
    
    return {
        'demand_reduction': get_param('Demand Reduction', 1.0),
        'start_year': int(get_param('Start Year', 2024)),
        'end_year': int(get_param('End Year', 2060)),
        'pkm_shift_to_rail': get_param('PKM Shift to Rail', 0.0),
        'tkm_shift_to_rail': get_param('TKM Shift to Rail', 0.0),
        'car_electrification': get_param('Car electrification', 0.0),
        'motorcycle_electrification': get_param('Motorcycle electrification', 0.0),
        'bus_electrification': get_param('Bus electrification', 0.0),
        'truck_electrification': get_param('Truck electrification', 0.0)
    }

######################################################################################################################################################
#%% Vehicle projection

def get_phase_in_factor(year, start_year, end_year, target_factor):
    if year <= start_year:
        return 1.0
    elif year >= end_year:
        return target_factor
    else:
        progress = (year - start_year) / (end_year - start_year)
        return 1.0 - (1.0 - target_factor) * progress

def get_elasticity(pkm_type, pkm_data, gdp_by_year, pop_by_year):
    type_data = pkm_data[pkm_data['Type_lv2'] == pkm_type].copy()
    hist_years = type_data['Year'].values
    hist_pkm = type_data['Value'].values
    valid = ~np.isnan(hist_pkm) & (hist_pkm > 0)
    hist_years, hist_pkm = hist_years[valid], hist_pkm[valid]
    
    if len(hist_years) < 3:
        return 0.5
    
    hist_gdp, hist_pop = [], []
    for y in hist_years:
        hist_gdp.append(gdp_by_year.get(y, gdp_by_year.iloc[np.abs(gdp_by_year.index - y).argmin()]))
        hist_pop.append(pop_by_year.get(y, pop_by_year.iloc[np.abs(pop_by_year.index - y).argmin()]))
    
    pkm_per_capita = np.array(hist_pkm) / np.array(hist_pop)
    log_gdp, log_pkm = np.log(hist_gdp), np.log(pkm_per_capita)
    
    try:
        slope, _, _, _, _ = linregress(log_gdp, log_pkm)
        return slope if abs(slope) < 2 else 0.5
    except:
        return 0.5

def project_pkm(pkm_type, pkm_data, gdp_by_year, pop_by_year, scenario_params):
    type_data = pkm_data[pkm_data['Type_lv2'] == pkm_type].copy()
    hist_years = type_data['Year'].values
    hist_pkm = type_data['Value'].values
    valid = ~np.isnan(hist_pkm) & (hist_pkm > 0)
    hist_years, hist_pkm = hist_years[valid], hist_pkm[valid]
    
    if pkm_type in ['Cycling', 'Walking']:
        if len(hist_years) >= 1:
            base_year = hist_years[-1]
            base_pkm = hist_pkm[-1]
            base_pop = pop_by_year.get(base_year, pop_by_year.iloc[0])
            
            future_years = [y for y in range(base_year + 1, 2101) if y in pop_by_year.index]
            
            projections = []
            for year in future_years:
                pkm_proj = base_pkm * (pop_by_year[year] / base_pop)
                reduction_factor = get_phase_in_factor(year, scenario_params['start_year'], 
                                                       scenario_params['end_year'], 
                                                       scenario_params['demand_reduction'])
                projections.append({'Year': year, 'PKM': pkm_proj * reduction_factor})
            
            return pd.DataFrame(projections)
        else:
            return pd.DataFrame()
    
    if len(hist_years) < 3:
        return pd.DataFrame()
    
    base_year, base_pkm = hist_years[-1], hist_pkm[-1]
    base_pop = pop_by_year.get(base_year, pop_by_year.iloc[0])
    base_gdp = gdp_by_year.get(base_year, gdp_by_year.iloc[0])
    elasticity = get_elasticity(pkm_type, pkm_data, gdp_by_year, pop_by_year)
    
    future_years = [y for y in range(base_year + 1, 2101) if y in gdp_by_year.index and y in pop_by_year.index]
    
    projections = []
    for year in future_years:
        pkm_proj = base_pkm * (pop_by_year[year] / base_pop) * ((gdp_by_year[year] / base_gdp) ** elasticity)
        reduction_factor = get_phase_in_factor(year, scenario_params['start_year'], scenario_params['end_year'], scenario_params['demand_reduction'])
        projections.append({'Year': year, 'PKM': pkm_proj * reduction_factor})
    
    return pd.DataFrame(projections)

def apply_modal_shift_to_pkm(pkm_projections, scenario_params):
    if scenario_params['pkm_shift_to_rail'] == 0 or 'Cars' not in pkm_projections:
        return pkm_projections
    
    base_year, shift_target = 2024, scenario_params['pkm_shift_to_rail']
    start_year, end_year = scenario_params['start_year'], scenario_params['end_year']
    rail_types = [t for t in ['Rail', 'Subway/tram'] if t in pkm_projections]
    
    if not rail_types:
        return pkm_projections
    
    rail_base = {rt: pkm_projections[rt][pkm_projections[rt]['Year'] == base_year]['PKM'].iloc[0] if base_year in pkm_projections[rt]['Year'].values else pkm_projections[rt]['PKM'].iloc[0] for rt in rail_types}
    total_rail_base = sum(rail_base.values())
    
    cars_shifted = pkm_projections['Cars'].copy()
    rail_shifted = {rt: pkm_projections[rt].copy() for rt in rail_types}
    
    for idx, row in cars_shifted.iterrows():
        year = row['Year']
        if year <= base_year:
            continue
        
        phase_in = 0.0 if year <= start_year else (1.0 if year >= end_year else (year - start_year) / (end_year - start_year))
        shift_amount = row['PKM'] * shift_target * phase_in
        
        cars_shifted.loc[idx, 'PKM'] = row['PKM'] - shift_amount
        
        for rt in rail_types:
            rail_share = rail_base[rt] / total_rail_base if total_rail_base > 0 else 1.0 / len(rail_types)
            rail_idx = rail_shifted[rt][rail_shifted[rt]['Year'] == year].index
            if len(rail_idx) > 0:
                rail_shifted[rt].loc[rail_idx[0], 'PKM'] += shift_amount * rail_share
    
    pkm_projections['Cars'] = cars_shifted
    for rt in rail_types:
        pkm_projections[rt] = rail_shifted[rt]
    
    return pkm_projections

def get_correlation_factors(vehicle_data, pkm_data):
    vehicle_to_pkm = {
        'Cars':                             'Cars', 
        'Buses':                            'Buses',
        'Railway_passenger_train_electric': 'Rail', 
        'Railway_passenger_train_fossil':   'Rail',
        'Railway_passenger_car':            'Rail', 
        'Railway_freight_train_electric':   'Rail',
        'Railway_freight_train_fossil':     'Rail', 
        'Railway_freight_car':              'Rail',
        'Tram_train':                       'Subway/tram', 
        'Tram_car':                         'Subway/tram',
        'Subway_car':                       'Subway/tram', 
        'Subway_train':                     'Subway/tram',
        'Trucks':                           'Road', 
        'Vehicles_other':                   'Road',
        'Moped':                            'Cars', 
        'Motorcycles':                      'Cars', 
        'Trailers':                         'Road'
    }
    
    correlation_factors = {}
    for vehicle_type, pkm_type in vehicle_to_pkm.items():
        vt_data = vehicle_data[vehicle_data['Type_lv2'] == vehicle_type]
        pt_data = pkm_data[pkm_data['Type_lv2'] == pkm_type]
        if vt_data.empty or pt_data.empty:
            continue
        
        merged = pd.merge(vt_data[['Year_from', 'Value']].rename(columns={'Year_from': 'Year', 'Value': 'Vehicles'}),
                          pt_data[['Year', 'Value']].rename(columns={'Value': 'PKM'}), on='Year', how='inner')
        
        if len(merged) >= 3 and (merged['PKM'] > 0).any():
            merged['Vehicles_per_PKM'] = merged['Vehicles'] / merged['PKM']
            factor = merged['Vehicles_per_PKM'].median()
            if pd.notna(factor) and np.isfinite(factor):
                correlation_factors[vehicle_type] = {'pkm_type': pkm_type, 'factor': factor}
    
    for vt in ['Bicycles', 'E_bikes']:
        vt_data = vehicle_data[vehicle_data['Type_lv2'] == vt]
        if vt_data.empty:
            continue
        
        cycling_pkm = pkm_data[pkm_data['Type_lv2'] == 'Cycling']
        
        if not cycling_pkm.empty:
            cycling_valid = cycling_pkm[cycling_pkm['Value'] > 0]
            
            if not cycling_valid.empty:
                merged = pd.merge(vt_data[['Year_from', 'Value']].rename(columns={'Year_from': 'Year', 'Value': 'Vehicles'}),
                                  cycling_valid[['Year', 'Value']].rename(columns={'Value': 'PKM'}), on='Year', how='inner')
                
                if not merged.empty and (merged['PKM'] > 0).any():
                    merged['Vehicles_per_PKM'] = merged['Vehicles'] / merged['PKM']
                    factor = merged['Vehicles_per_PKM'].median()
                    if pd.notna(factor) and np.isfinite(factor):
                        correlation_factors[vt] = {'pkm_type': 'Cycling', 'factor': factor}
                    else:
                        default_factor = 3530000.0 if vt == 'Bicycles' else 640000.0
                        correlation_factors[vt] = {'pkm_type': 'Cycling', 'factor': default_factor}
                else:
                    default_factor = 3530000.0 if vt == 'Bicycles' else 640000.0
                    correlation_factors[vt] = {'pkm_type': 'Cycling', 'factor': default_factor}
            else:
                default_factor = 3530000.0 if vt == 'Bicycles' else 640000.0
                correlation_factors[vt] = {'pkm_type': 'Cycling', 'factor': default_factor}
        else:
            default_factor = 3530000.0 if vt == 'Bicycles' else 640000.0
            correlation_factors[vt] = {'pkm_type': 'Cycling', 'factor': default_factor}
    
    return correlation_factors

def apply_fuel_types_to_vehicles(vehicles_df, fuel_shares, scenario_params):
    base_year = 2024

    if fuel_shares.empty:
        # No split available: emit a single NA row per type
        projected_with_fuel = []
        for _, row in vehicles_df.iterrows():
            projected_with_fuel.append({'Type_lv2': row['Type_lv2'], 'Fuel_type': 'NA',
                                        'Year': row['Year'], 'Value': row['Value']})
        return pd.DataFrame(projected_with_fuel)

    electrification_mapping = {'Cars': 'car_electrification', 'Motorcycles': 'motorcycle_electrification',
                               'Moped': 'motorcycle_electrification', 'Buses': 'bus_electrification',
                               'Trucks': 'truck_electrification'}

    fuel_shares_list = []
    for vt in fuel_shares['Type_lv2'].unique():
        vt_data = fuel_shares[fuel_shares['Type_lv2'] == vt].copy()
        vt_data['Value'] = pd.to_numeric(vt_data['Value'], errors='coerce').fillna(0)
        vt_data['Fuel_type'] = vt_data['Fuel_type'].fillna('NA').astype(str).replace({'nan': 'NA', 'NAN': 'NA', '': 'NA'})
        total = vt_data['Value'].sum()
        if total > 0:
            for _, row in vt_data.iterrows():
                fuel_shares_list.append({'Type_lv2': vt, 'Fuel_type': row['Fuel_type'],
                                         'Share': row['Value'] / total})

    fuel_shares_df = pd.DataFrame(fuel_shares_list)
    projected_with_fuel = []

    for _, row in vehicles_df.iterrows():
        vt, year, total_vehicles = row['Type_lv2'], row['Year'], row['Value']
        shares = fuel_shares_df[fuel_shares_df['Type_lv2'] == vt].copy()

        if shares.empty:
            projected_with_fuel.append({'Type_lv2': vt, 'Fuel_type': 'NA', 'Year': year, 'Value': total_vehicles})
            continue

        elec_param = electrification_mapping.get(vt)
        if elec_param and scenario_params[elec_param] > 0:
            target_elec = scenario_params[elec_param]
            elec_factor = 0.0 if year <= scenario_params['start_year'] else (target_elec if year >= scenario_params['end_year'] else target_elec * (year - scenario_params['start_year']) / (scenario_params['end_year'] - scenario_params['start_year']))

            if elec_factor > 0:
                electric_share = shares[shares['Fuel_type'] == 'Electric']['Share'].sum()
                fossil_share = shares[shares['Fuel_type'] == 'Fossil']['Share'].sum()
                hybrid_share = shares[shares['Fuel_type'] == 'Hybrid']['Share'].sum()
                total_shiftable = fossil_share + hybrid_share

                if total_shiftable > 0:
                    shift_amount = total_shiftable * elec_factor
                    new_shares = []
                    for _, s in shares.iterrows():
                        if s['Fuel_type'] == 'Electric':
                            new_shares.append({'Fuel_type': 'Electric', 'Share': electric_share + shift_amount})
                        elif s['Fuel_type'] == 'Fossil' and fossil_share * (1 - elec_factor) > 0:
                            new_shares.append({'Fuel_type': 'Fossil', 'Share': fossil_share * (1 - elec_factor)})
                        elif s['Fuel_type'] == 'Hybrid' and hybrid_share * (1 - elec_factor) > 0:
                            new_shares.append({'Fuel_type': 'Hybrid', 'Share': hybrid_share * (1 - elec_factor)})
                        elif s['Fuel_type'] == 'NA':
                            new_shares.append({'Fuel_type': 'NA', 'Share': s['Share']})
                    shares = pd.DataFrame(new_shares)

        for _, s in shares.iterrows():
            if s['Share'] > 0:
                projected_with_fuel.append({'Type_lv2': vt, 'Fuel_type': s['Fuel_type'],
                                            'Year': year, 'Value': total_vehicles * s['Share']})

    return pd.DataFrame(projected_with_fuel)

def run_scenario(scenario_name, scenario_params, vehicle_data, fuel_shares, pkm_data, gdp_data, pop_data):
    gdp_by_year = gdp_data.set_index('Year_from')['Value']
    pop_by_year = pop_data[pop_data['Year_to'] <= 2100].set_index('Year_to')['Value']
    
    # Project all traffic series (passenger modes in PKM, freight modes in TKM).
    # 'Road' is TKM but is projected the same way as PKM here, because Truck /
    # Trailer / Vehicles_other counts are derived from Road TKM via the
    # correlation factors. 'Active' is a container category without values, so
    # it is skipped.
    pkm_types = [t for t in pkm_data['Type_lv2'].unique() if t not in ['Active']]
    
    pkm_projections = {}
    for pkm_type in pkm_types:
        df = project_pkm(pkm_type, pkm_data, gdp_by_year, pop_by_year, scenario_params)
        if not df.empty:
            pkm_projections[pkm_type] = df
    
    for active_mode in ['Cycling', 'Walking']:
        if active_mode in pkm_data['Type_lv2'].unique():
            df = project_pkm(active_mode, pkm_data, gdp_by_year, pop_by_year, scenario_params)
            if not df.empty:
                pkm_projections[active_mode] = df
    
    if scenario_params['pkm_shift_to_rail'] > 0:
        pkm_projections = apply_modal_shift_to_pkm(pkm_projections, scenario_params)
    
    correlation_factors = get_correlation_factors(vehicle_data, pkm_data)
    
    all_vehicles = []
    for vehicle_type, corr_info in correlation_factors.items():
        pkm_type, factor = corr_info['pkm_type'], corr_info['factor']
        if pkm_type in pkm_projections:
            for _, row in pkm_projections[pkm_type].iterrows():
                all_vehicles.append({'Type_lv2': vehicle_type, 'Year': row['Year'], 'Value': row['PKM'] * factor})
    
    vehicles_df = pd.DataFrame(all_vehicles)
    if vehicles_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame()
    
    base_year = 2024
    base_vehicles = (vehicle_data[vehicle_data['Year_from'] == base_year]
                     .groupby('Type_lv2', as_index=False)['Value'].sum())
    if not base_vehicles.empty:
        base_vehicles['Year'] = base_year
        base_vehicles = base_vehicles[['Type_lv2', 'Year', 'Value']]
        vehicles_df = pd.concat([base_vehicles, vehicles_df], ignore_index=True)
    
    vehicles_with_fuel = apply_fuel_types_to_vehicles(vehicles_df, fuel_shares, scenario_params)
    summary = vehicles_df.groupby('Year').agg({'Value': 'sum'}).reset_index()
    summary['Vehicles_per_1000'] = summary['Value'] / pop_by_year.reindex(summary['Year']).fillna(0) * 1000
    fuel_summary = vehicles_with_fuel.groupby(['Year', 'Fuel_type'])['Value'].sum().reset_index()
    
    pkm_combined = pd.concat([df.assign(Type=pkm_type) for pkm_type, df in pkm_projections.items() if not df.empty], ignore_index=True)
    
    return vehicles_df, summary, pkm_projections, vehicles_with_fuel, fuel_summary

######################################################################################################################################################
#%% Wide-format export (MISO2_country x End_use_sector x Year)

def _type_has_fuel_suffix(type_name):
    return type_name.endswith('_electric') or type_name.endswith('_fossil')

def make_wide_export(vehicles_df, fuel_df, base_year=2024, end_year=2100):
    years = list(range(base_year, end_year + 1))

    if len(fuel_df) > 0:
        f = fuel_df.copy()
        f['Year'] = pd.to_numeric(f['Year'], errors='coerce')
        f = f[(f['Year'] >= base_year) & (f['Year'] <= end_year)]
        f['Fuel_type'] = f['Fuel_type'].fillna('NA').astype(str).replace({'nan': 'NA', 'NAN': 'NA', '': 'NA'})

        mask_suffixed = f['Type_lv2'].apply(_type_has_fuel_suffix)
        mask_na = f['Fuel_type'].str.upper() == 'NA'

        # Types that already encode fuel keep their bare name
        f.loc[mask_suffixed, 'End_use_sector'] = f.loc[mask_suffixed, 'Type_lv2']

        # Types with Fuel_type == NA also keep their bare name (no suffix)
        f.loc[~mask_suffixed & mask_na, 'End_use_sector'] = f.loc[~mask_suffixed & mask_na, 'Type_lv2']

        # Everything else gets _<fuel>
        f.loc[~mask_suffixed & ~mask_na, 'End_use_sector'] = (
            f.loc[~mask_suffixed & ~mask_na, 'Type_lv2'].astype(str)
            + '_' + f.loc[~mask_suffixed & ~mask_na, 'Fuel_type'].astype(str).str.lower()
        )

        fuel = (f.groupby(['End_use_sector', 'Year'])['Value'].sum().unstack('Year'))
    else:
        fuel = pd.DataFrame()

    if len(vehicles_df) > 0:
        v = vehicles_df.copy()
        v['Year'] = pd.to_numeric(v['Year'], errors='coerce')
        v = v[(v['Year'] >= base_year) & (v['Year'] <= end_year)]
        v = v[v['Type_lv2'].apply(_type_has_fuel_suffix)]
        veh = (v.groupby(['Type_lv2', 'Year'])['Value'].sum().unstack('Year'))
        veh.insert(0, 'End_use_sector', veh.index)
        veh = veh.set_index('End_use_sector')
    else:
        veh = pd.DataFrame()

    combined = pd.concat([veh, fuel], axis=0)
    combined = combined.groupby(level=0).sum()

    combined = combined.reindex(columns=years)

    combined = combined.fillna(0)
    combined.insert(0, 'MISO2_country', 'Austria')
    combined.insert(1, 'End_use_sector', combined.index)
    combined.insert(2, 'Unit', 'Units')
    combined.columns = ['MISO2_country', 'End_use_sector', 'Unit'] + [str(y) for y in years]
    combined = combined.reset_index(drop=True)

    return combined

######################################################################################################################################################
#%% Projection execution

scenarios_to_run = ['Baseline', 'Mobility Reduction', 'Modal Shift', 'Fleet Electrification']

data_vehicles = load_vehicle_data_with_fuel()
data_fuel_shares = load_vehicle_fuel_shares()
data_PKM = read_excel(os.path.join(main_path, 'input', 'data_pkm_tkm.xlsx'), sheet_name='input')
data_GDP = read_excel(os.path.join(main_path, 'input', 'data_GDP.xlsx'), sheet_name='input')
data_POP = read_excel(os.path.join(main_path, 'input', 'data_POP.xlsx'), sheet_name='input')

for df in [data_vehicles, data_PKM, data_GDP, data_POP]:
    df['Value'] = df['Value'].astype(float)

scenario_params_path = os.path.join(main_path, 'input', 'scenario_parameters.xlsx')
base_year = 2024

all_results, all_summaries, all_pkm, all_fuel, all_fuel_summaries = {}, {}, {}, {}, {}

scenarios_path = os.path.join('output', 'scenarios', 'vehicles')
os.makedirs(scenarios_path, exist_ok=True)

for scenario_name in scenarios_to_run:
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name)
    vehicles_df, summary, pkm_projections, vehicles_fuel, fuel_summary = run_scenario(
        scenario_name, scenario_params, data_vehicles, data_fuel_shares, data_PKM, data_GDP, data_POP)
    all_results[scenario_name], all_summaries[scenario_name], all_pkm[scenario_name] = vehicles_df, summary, pkm_projections
    all_fuel[scenario_name], all_fuel_summaries[scenario_name] = vehicles_fuel, fuel_summary

    wide = make_wide_export(vehicles_df, vehicles_fuel, base_year=base_year, end_year=2100)
    wide.to_csv(os.path.join(scenarios_path, f'MISO2_{scenario_name}.csv'), index=False, sep=';', decimal=',')

######################################################################################################################################################
#%% Results

figures_path = os.path.join('output', 'scenarios', 'vehicles', 'figures')
os.makedirs(figures_path, exist_ok=True)

#%%% Vehicle fleet comparison
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

for ax, idx in [(axes[0], False), (axes[1], True)]:
    for name, df in all_summaries.items():
        df_f = df[df['Year'] >= 2024]
        if not df_f.empty:
            if idx:
                base = df_f[df_f['Year'] == 2024]['Value'].iloc[0] if 2024 in df_f['Year'].values else df_f['Value'].iloc[0]
                ax.plot(df_f['Year'], df_f['Value'] / base if base > 0 else df_f['Value'], label=name, linewidth=2)
            else:
                ax.plot(df_f['Year'], df_f['Value'] / 1e6, label=name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel('Total Vehicles (millions)' if not idx else 'Total vehicles (Index 2024=1)')
    ax.set_title('Vehicle Fleet Comparison' if not idx else 'Vehicle Fleet Growth (Indexed)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
    if idx:
        ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig(os.path.join(figures_path, 'vehicle_comparison.png'), dpi=150, bbox_inches='tight')
plt.show()

#%%% Individual vehicle type plots
individual_path = os.path.join(figures_path, 'Individual_Types')
os.makedirs(individual_path, exist_ok=True)

vehicle_types = sorted(set([vt for s in scenarios_to_run if s in all_results for vt in all_results[s]['Type_lv2'].unique()]))

for vt in vehicle_types:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    for ax, idx in [(axes[0], False), (axes[1], True)]:
        for name in scenarios_to_run:
            if name in all_results:
                df_f = all_results[name][all_results[name]['Year'] >= 2024]
                vt_data = df_f[df_f['Type_lv2'] == vt].groupby('Year')['Value'].sum().reset_index()
                if not vt_data.empty:
                    if idx:
                        base = vt_data[vt_data['Year'] == 2024]['Value'].iloc[0] if 2024 in vt_data['Year'].values else vt_data['Value'].iloc[0]
                        ax.plot(vt_data['Year'], vt_data['Value'] / base if base > 0 else vt_data['Value'], label=name, linewidth=2)
                    else:
                        ax.plot(vt_data['Year'], vt_data['Value'] / 1e6, label=name, linewidth=2)
        
        ax.set_xlabel('Year')
        ax.set_ylabel('Vehicles (millions)' if not idx else 'Vehicles (Index 2024=1)')
        ax.set_title(f'{vt} - {"Absolute Values" if not idx else "Indexed Growth"}')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
        if idx:
            ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    clean_name = vt.replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
    plt.savefig(os.path.join(individual_path, f'vehicle_type_{clean_name}.png'), dpi=150, bbox_inches='tight')
    plt.close()

#%%% PKM/TKM comparison
fig, axes = plt.subplots(2, 3, figsize=(18, 10))

pkm_types = ['Cars', 'Rail', 'Subway/tram']
tkm_types = ['Road', 'Rail']

available_pkm = [t for t in pkm_types if any(t in d for d in all_pkm.values())]
available_tkm = [t for t in tkm_types if t in data_PKM['Type_lv2'].unique()]

for idx, pkm_type in enumerate(available_pkm[:3]):
    ax = axes[0, idx]
    for name, pkm_dict in all_pkm.items():
        if pkm_type in pkm_dict:
            df_f = pkm_dict[pkm_type][pkm_dict[pkm_type]['Year'] >= 2024]
            if not df_f.empty:
                base = df_f[df_f['Year'] == 2024]['PKM'].iloc[0] if 2024 in df_f['Year'].values else df_f['PKM'].iloc[0]
                ax.plot(df_f['Year'], df_f['PKM'] / base if base > 0 else df_f['PKM'], label=name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel(f'{pkm_type} PKM (Index 2024=1)')
    ax.set_title(f'{pkm_type} PKM Growth')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)

for idx, tkm_type in enumerate(available_tkm[:3]):
    ax = axes[1, idx]
    for name in scenarios_to_run:
        sp = load_scenario_parameters(scenario_params_path, name)
        tkm_df = project_pkm(tkm_type, data_PKM, data_GDP.set_index('Year_from')['Value'], 
                            data_POP[data_POP['Year_to'] <= 2100].set_index('Year_to')['Value'], sp)
        if not tkm_df.empty:
            df_f = tkm_df[tkm_df['Year'] >= 2024]
            if not df_f.empty:
                base = df_f[df_f['Year'] == 2024]['PKM'].iloc[0] if 2024 in df_f['Year'].values else df_f['PKM'].iloc[0]
                ax.plot(df_f['Year'], df_f['PKM'] / base if base > 0 else df_f['PKM'], label=name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel(f'{tkm_type} TKM (Index 2024=1)')
    ax.set_title(f'{tkm_type} Freight TKM Growth')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)

for idx in range(len(available_pkm), 3):
    axes[0, idx].axis('off')
for idx in range(len(available_tkm), 3):
    axes[1, idx].axis('off')

plt.tight_layout()
plt.savefig(os.path.join(figures_path, 'pkm_tkm_comparison.png'), dpi=150, bbox_inches='tight')
plt.show()

#%%% Fuel type comparison
fuel_colors = {'Fossil': '#8B4513', 'Electric': '#2E8B57', 'Hybrid': '#4169E1', 'NA': '#808080'}
fuel_path = os.path.join(figures_path, 'Fuel_Types')
os.makedirs(fuel_path, exist_ok=True)

for name in scenarios_to_run:
    if name in all_fuel_summaries:
        df = all_fuel_summaries[name]
        if not df.empty:
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))
            
            for ax, idx in [(axes[0], False), (axes[1], True)]:
                for fuel_type in df['Fuel_type'].unique():
                    fd = df[df['Fuel_type'] == fuel_type]
                    fd_f = fd[fd['Year'] >= 2024]
                    if not fd_f.empty:
                        if idx:
                            base = fd_f[fd_f['Year'] == 2024]['Value'].iloc[0] if 2024 in fd_f['Year'].values else fd_f['Value'].iloc[0]
                            ax.plot(fd_f['Year'], fd_f['Value'] / base if base > 0 else fd_f['Value'], 
                                   label=fuel_type, linewidth=2, color=fuel_colors.get(fuel_type))
                        else:
                            ax.plot(fd_f['Year'], fd_f['Value'] / 1e6, label=fuel_type, linewidth=2, color=fuel_colors.get(fuel_type))
                
                ax.set_xlabel('Year')
                ax.set_ylabel('Vehicles (millions)' if not idx else 'Vehicles (Index 2024=1)')
                ax.set_title(f'Vehicle Fleet by Fuel Type - {name}' if not idx else f'Vehicle Fleet Growth by Fuel Type - {name}')
                ax.legend()
                ax.grid(True, alpha=0.3)
                ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
                if idx:
                    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
            
            plt.tight_layout()
            plt.savefig(os.path.join(fuel_path, f'vehicles_by_fuel_{name}.png'), dpi=150, bbox_inches='tight')
            plt.show()

#%%% Scenario summary

for name, df in all_summaries.items():
    df_f = df[df['Year'] >= 2024]
    if df_f.empty: continue
    
    first_row = df_f[df_f['Year'] == 2024].iloc[0] if 2024 in df_f['Year'].values else df_f.iloc[0]
    last_row = df_f.iloc[-1]
    growth = ((last_row['Value'] / first_row['Value']) - 1) * 100 if first_row['Value'] > 0 else 0
    
    print(f"\n{name}:")
    print(f"  Base year (2024): {first_row['Value']/1e6:.2f}M vehicles")
    print(f"  Final year ({last_row['Year']:.0f}): {last_row['Value']/1e6:.2f}M vehicles")
    print(f"  Growth (2024 to {last_row['Year']:.0f}): {growth:.1f}%")
    
    if name in all_results:
        final = all_results[name][all_results[name]['Year'] == last_row['Year']]
        if not final.empty:
            car_types = ['Cars', 'Moped', 'Motorcycles']
            rail_types = ['Railway_passenger_train_electric', 'Railway_passenger_train_fossil', 
                          'Railway_passenger_car', 'Railway_freight_train_electric',
                          'Railway_freight_train_fossil', 'Railway_freight_car']
            
            car_total = final[final['Type_lv2'].isin(car_types)]['Value'].sum()
            rail_total = final[final['Type_lv2'].isin(rail_types)]['Value'].sum()
            bus_total = final[final['Type_lv2'] == 'Buses']['Value'].sum()
            tram_total = final[final['Type_lv2'].isin(['Tram_train', 'Tram_car'])]['Value'].sum()
            subway_total = final[final['Type_lv2'].isin(['Subway_car', 'Subway_train'])]['Value'].sum()
            
            print(f"\n  Vehicle type breakdown ({last_row['Year']:.0f}):")
            print(f"    Cars (including motorcycles): {car_total/1e6:.2f}M")
            print(f"    Rail vehicles: {rail_total/1e6:.2f}M")
            print(f"    Buses: {bus_total/1e6:.2f}M")
            print(f"    Trams: {tram_total/1e6:.2f}M")
            print(f"    Subway: {subway_total/1e6:.2f}M")
    
    if name in all_fuel:
        final_fuel = all_fuel[name][all_fuel[name]['Year'] == last_row['Year']]
        if not final_fuel.empty:
            fuel_summary = final_fuel.groupby('Fuel_type')['Value'].sum()
            total_fuel = fuel_summary.sum()
            print(f"\n  Fuel type breakdown ({last_row['Year']:.0f}):")
            for fuel_type in ['Fossil', 'Electric', 'Hybrid', 'NA']:
                if fuel_type in fuel_summary.index:
                    val = fuel_summary[fuel_type]
                    print(f"    {fuel_type}: {val/1e6:.2f}M ({val/total_fuel*100:.1f}%)")

# Calculate reduction and shift effects
if 'Baseline' in all_summaries and 'Mobility Reduction' in all_summaries:
    base = all_summaries['Baseline']
    red = all_summaries['Mobility Reduction']
    merged = pd.merge(base[['Year', 'Value']].rename(columns={'Value': 'Baseline'}),
                      red[['Year', 'Value']].rename(columns={'Value': 'Reduced'}), on='Year')
    merged = merged[merged['Year'] >= 2024]
    if not merged.empty:
        last = merged.iloc[-1]
        print(f"\n{'-'*50}")
        print(f"Mobility Reduction vs Baseline:")
        print(f"  Final year reduction: {(1 - last['Reduced'] / last['Baseline']) * 100:.1f}%")
        print(f"  Baseline: {last['Baseline']/1e6:.2f}M vehicles")
        print(f"  Reduced: {last['Reduced']/1e6:.2f}M vehicles")

if 'Baseline' in all_summaries and 'Modal Shift' in all_summaries:
    base = all_summaries['Baseline']
    shift = all_summaries['Modal Shift']
    merged = pd.merge(base[['Year', 'Value']].rename(columns={'Value': 'Baseline'}),
                      shift[['Year', 'Value']].rename(columns={'Value': 'Shifted'}), on='Year')
    merged = merged[merged['Year'] >= 2024]
    if not merged.empty:
        last = merged.iloc[-1]
        print(f"\n{'-'*50}")
        print(f"Modal Shift vs Baseline:")
        print(f"  Final year difference: {(1 - last['Shifted'] / last['Baseline']) * 100:.1f}%")
        print(f"  Baseline: {last['Baseline']/1e6:.2f}M vehicles")
        print(f"  Shifted: {last['Shifted']/1e6:.2f}M vehicles")