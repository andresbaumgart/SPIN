#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Mobility infrastructure projections
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

def load_vehicle_projections(scenario_name):
    """Load vehicle projections for a given scenario"""
    file_path = os.path.join(main_path, 'output', 'interim', f'stocks_vehicles_proj_fuel_{scenario_name}.parquet')
    if os.path.exists(file_path):
        return pd.read_parquet(file_path)
    else:
        return pd.DataFrame()

######################################################################################################################################################
#%% Scenarios

def load_scenario_parameters(file_path, scenario_name):
    try:
        df_scenarios = pd.read_excel(file_path, sheet_name='mobility')
    except:
        return {
            'demand_reduction': 1.0,
            'start_year': 2024,
            'end_year': 2024,
            'pkm_shift_to_rail': 0.0,
            'tkm_shift_to_rail': 0.0
        }
    
    df_scenarios = df_scenarios[~df_scenarios['Scenario Name'].str.startswith(('Parameter', 'Percenrage'), na=False) & 
                                df_scenarios['Scenario Name'].notna() & 
                                (df_scenarios['Scenario Name'] != '')]
    scenario = df_scenarios[df_scenarios['Scenario Name'] == scenario_name]
    
    if scenario.empty:
        return {
            'demand_reduction': 1.0,
            'start_year': 2024,
            'end_year': 2024,
            'pkm_shift_to_rail': 0.0,
            'tkm_shift_to_rail': 0.0
        }
    
    scenario = scenario.iloc[0]
    
    def get_param(col_name, default):
        if col_name in df_scenarios.columns:
            val = scenario.get(col_name, default)
            if isinstance(val, str):
                val = val.replace(',', '.').strip()
                if val == '-' or val == '':
                    return default
                try:
                    return float(val)
                except:
                    return default
            return float(val) if pd.notna(val) else default
        return default
    
    return {
        'demand_reduction': get_param('Demand Reduction', 1.0),
        'start_year': int(get_param('Start Year', 2024)),
        'end_year': int(get_param('End Year', 2060)),
        'pkm_shift_to_rail': get_param('PKM Shift to Rail', 0.0),
        'tkm_shift_to_rail': get_param('TKM Shift to Rail', 0.0)
    }

######################################################################################################################################################
#%% Infrastructure projection

def get_phase_in_factor(year, start_year, end_year, target_factor):
    if year <= start_year:
        return 1.0
    elif year >= end_year:
        return target_factor
    else:
        progress = (year - start_year) / (end_year - start_year)
        return 1.0 - (1.0 - target_factor) * progress

def get_elasticity(mode_type, mode_data, gdp_by_year, pop_by_year):
    type_data = mode_data[mode_data['Type_lv2'] == mode_type].copy()
    hist_years = type_data['Year'].values
    hist_values = type_data['Value'].values
    valid = ~np.isnan(hist_values) & (hist_values > 0)
    hist_years, hist_values = hist_years[valid], hist_values[valid]
    
    if len(hist_years) < 3:
        return 0.5
    
    hist_gdp, hist_pop = [], []
    for y in hist_years:
        hist_gdp.append(gdp_by_year.get(y, gdp_by_year.iloc[np.abs(gdp_by_year.index - y).argmin()]))
        hist_pop.append(pop_by_year.get(y, pop_by_year.iloc[np.abs(pop_by_year.index - y).argmin()]))
    
    per_capita = np.array(hist_values) / np.array(hist_pop)
    log_gdp, log_mode = np.log(hist_gdp), np.log(per_capita)
    
    try:
        slope, _, _, _, _ = linregress(log_gdp, log_mode)
        return slope if abs(slope) < 2 else 0.5
    except:
        return 0.5

def get_mobility_growth_rates(pkm_data, gdp_by_year, pop_by_year):
    mobility_types = pkm_data['Type_lv2'].unique()
    growth_rates = {}
    
    for mob_type in mobility_types:
        type_data = pkm_data[pkm_data['Type_lv2'] == mob_type].copy()
        if type_data.empty:
            continue
        
        if len(type_data) > type_data['Year'].nunique():
            type_data = type_data.groupby('Year').agg({'Value': 'sum'}).reset_index()
        
        hist_years = type_data['Year'].values
        hist_values = type_data['Value'].values
        valid = ~np.isnan(hist_values) & (hist_values > 0)
        hist_years, hist_values = hist_years[valid], hist_values[valid]
        
        if len(hist_years) < 3:
            base_year = 2024
            if base_year in gdp_by_year.index and base_year in pop_by_year.index:
                base_gdp = gdp_by_year[base_year]
                base_pop = pop_by_year[base_year]
                future_years = [y for y in range(base_year + 1, 2101) if y in gdp_by_year.index and y in pop_by_year.index]
                growth_factors = {year: (pop_by_year[year] / base_pop) * (gdp_by_year[year] / base_gdp) for year in future_years}
                growth_rates[mob_type] = growth_factors
                continue
            else:
                continue
        
        base_year = hist_years[-1]
        base_pop = pop_by_year.get(base_year, pop_by_year.iloc[0])
        base_gdp = gdp_by_year.get(base_year, gdp_by_year.iloc[0])
        elasticity = get_elasticity(mob_type, pkm_data, gdp_by_year, pop_by_year)
        
        future_years = [y for y in range(2025, 2101) if y in gdp_by_year.index and y in pop_by_year.index]
        growth_factors = {year: (pop_by_year[year] / base_pop) * ((gdp_by_year[year] / base_gdp) ** elasticity) for year in future_years}
        growth_rates[mob_type] = growth_factors
    
    return growth_rates

def apply_monotonic_constraint(projections_df):
    if projections_df.empty:
        return projections_df
    
    constrained_dfs = []
    for infra_type in projections_df['Type_lv2'].unique():
        type_data = projections_df[projections_df['Type_lv2'] == infra_type].copy().sort_values('Year')
        type_data['Value'] = type_data['Value'].cummax()
        constrained_dfs.append(type_data)
    
    return pd.concat(constrained_dfs, ignore_index=True)

def apply_vehicle_based_infrastructure(infra_projections, vehicle_fuel_data, scenario_name):
    """
    Apply vehicle fuel type projections to infrastructure:
    - charging_station: Follow Electric vehicle growth
    - gas_station_building: Follow Fossil vehicle growth (with minimum threshold)
    """
    if vehicle_fuel_data.empty:
        print(f"  ⚠️ No vehicle fuel data for {scenario_name}, using default projection")
        return infra_projections
    
    base_year = 2024
    infra_base = infra_projections[infra_projections['Year'] == base_year].copy()
    
    veh_base = vehicle_fuel_data[vehicle_fuel_data['Year'] == base_year]
    veh_base_by_fuel = veh_base.groupby('Fuel_type')['Value'].sum()
    
    veh_future = vehicle_fuel_data[vehicle_fuel_data['Year'] >= base_year]
    veh_by_fuel_year = veh_future.groupby(['Year', 'Fuel_type'])['Value'].sum().reset_index()
    
    veh_pivot = veh_by_fuel_year.pivot(index='Year', columns='Fuel_type', values='Value').fillna(0)
    
    growth_factors = {}
    for fuel in veh_pivot.columns:
        if fuel in veh_base_by_fuel.index and veh_base_by_fuel[fuel] > 0:
            growth_factors[fuel] = veh_pivot[fuel] / veh_base_by_fuel[fuel]
        else:
            growth_factors[fuel] = 1.0
    
    shifted_projections = infra_projections.copy()
    
    for idx, row in shifted_projections.iterrows():
        year = row['Year']
        infra_type = row['Type_lv2']
        
        base_val = infra_base[infra_base['Type_lv2'] == infra_type]['Value'].iloc[0] if not infra_base.empty and not infra_base[infra_base['Type_lv2'] == infra_type].empty else row['Value']
        
        if year == base_year:
            continue
        
        if infra_type == 'charging_station':
            if 'Electric' in growth_factors:
                factor = growth_factors['Electric'].get(year, 1.0)
                shifted_projections.loc[idx, 'Value'] = base_val * factor
            else:
                shifted_projections.loc[idx, 'Value'] = row['Value']
                
        elif infra_type == 'gas_station_building':
            if 'Fossil' in growth_factors:
                factor = growth_factors['Fossil'].get(year, 1.0)
                shifted_projections.loc[idx, 'Value'] = base_val * factor
            else:
                shifted_projections.loc[idx, 'Value'] = row['Value']
        else:
            shifted_projections.loc[idx, 'Value'] = row['Value']
    
    for idx, row in shifted_projections.iterrows():
        if row['Type_lv2'] == 'gas_station_building':
            base_val = infra_base[infra_base['Type_lv2'] == row['Type_lv2']]['Value'].iloc[0] if not infra_base.empty and not infra_base[infra_base['Type_lv2'] == row['Type_lv2']].empty else row['Value']
            shifted_projections.loc[idx, 'Value'] = max(row['Value'], base_val * 0.3)
    
    return shifted_projections

def project_infrastructure_from_mobility(infra_data, mobility_growth_rates, scenario_params, infra_to_mobility_map, pkm_data):
    infra_types = infra_data['Type_lv2'].unique()
    base_year = 2024
    infra_base = infra_data[infra_data['Year'] == base_year].copy()
    
    if infra_base.empty:
        return pd.DataFrame()
    
    all_projections = []
    for infra_type in infra_types:
        type_base = infra_base[infra_base['Type_lv2'] == infra_type]
        if type_base.empty:
            continue
        
        base_value = type_base['Value'].iloc[0]
        mobility_types = infra_to_mobility_map.get(infra_type, None)
        
        if mobility_types is None:
            continue
        
        if isinstance(mobility_types, str):
            mobility_types = [mobility_types]
        
        valid_mobility_types = [mt for mt in mobility_types if mt in mobility_growth_rates]
        if not valid_mobility_types:
            continue
        
        growth_factors_list = [mobility_growth_rates[mt] for mt in valid_mobility_types]
        
        weights = []
        for mob_type in valid_mobility_types:
            mob_base_value = pkm_data[(pkm_data['Type_lv2'] == mob_type) & (pkm_data['Year'] == base_year)]['Value'].sum()
            weights.append(mob_base_value)
        
        total_weight = sum(weights)
        if total_weight == 0:
            weights = [1.0 / len(valid_mobility_types)] * len(valid_mobility_types)
        else:
            weights = [w / total_weight for w in weights]
        
        common_years = set(growth_factors_list[0].keys())
        for gf in growth_factors_list[1:]:
            common_years = common_years.intersection(gf.keys())
        
        if not common_years:
            continue
        
        growth_factors = {}
        for year in sorted(common_years):
            weighted_growth = sum(gf[year] * weights[i] for i, gf in enumerate(growth_factors_list))
            growth_factors[year] = weighted_growth
        
        # Base year row (growth factor 1.0)
        all_projections.append({
            'Type_lv2': infra_type,
            'Year': base_year,
            'Value': base_value,
            'Mobility_Type': '+'.join(valid_mobility_types),
            'Growth_Factor': 1.0,
            'Reduction_Factor': 1.0
        })
        
        for year, growth_factor in growth_factors.items():
            reduction_factor = get_phase_in_factor(year, scenario_params['start_year'], scenario_params['end_year'], scenario_params['demand_reduction'])
            projected_value = base_value * growth_factor * reduction_factor
            all_projections.append({
                'Type_lv2': infra_type,
                'Year': year,
                'Value': projected_value,
                'Mobility_Type': '+'.join(valid_mobility_types),
                'Growth_Factor': growth_factor,
                'Reduction_Factor': reduction_factor
            })
    
    result_df = pd.DataFrame(all_projections)
    result_df = apply_monotonic_constraint(result_df)
    
    return result_df

def run_scenario(scenario_name, scenario_params, infra_data, pkm_data, gdp_data, pop_data):
    gdp_by_year = gdp_data.set_index('Year_from')['Value']
    pop_by_year = pop_data[pop_data['Year_to'] <= 2100].set_index('Year_to')['Value']
    
    infra_to_mobility = {
        'motorway': ['Cars', 'Buses'],
        'motorway_bridge': ['Cars', 'Buses'],
        'motorway_tunnel': ['Cars', 'Buses'],
        'primary': ['Cars', 'Buses'],
        'primary_bridge': ['Cars', 'Buses'],
        'primary_tunnel': ['Cars', 'Buses'],
        'secondary_bridge': ['Cars', 'Buses'],
        'secondary_tunnel': ['Cars', 'Buses'],
        'tertiary_bridge': ['Cars', 'Buses'],
        'tertiary_tunnel': ['Cars', 'Buses'],
        'local': ['Cars', 'Buses'],
        'local_bridge': ['Cars', 'Buses'],
        'local_tunnel': ['Cars', 'Buses'],
        'secondary': ['Cars', 'Buses'],
        'tertiary': ['Cars', 'Buses'],
        'track': ['Cars', 'Buses'],
        'track_bridge': ['Cars', 'Buses'],
        'track_tunnel': ['Cars', 'Buses'],
        'parking_surface': ['Cars', 'Buses'],
        'parking_underground': ['Cars', 'Buses'],
        'parking_building': ['Cars', 'Buses'],
        'gas_station_building': ['Cars', 'Buses'],
        'charging_station': ['Cars', 'Buses'],
        'railway': ['Railway', 'Rail'],
        'railway_bridge': ['Railway', 'Rail'],
        'railway_tunnel': ['Railway', 'Rail'],
        'railway_building': ['Railway', 'Rail'],
        'railway_building_platform': ['Railway', 'Rail'],
        'rail_other': ['Railway', 'Rail'],
        'subway': ['Subway/tram'],
        'subway_bridge': ['Subway/tram'],
        'subway_tunnel': ['Subway/tram'],
        'subway_building': ['Subway/tram'],
        'tram': ['Subway/tram'],
    }
    
    mobility_growth_rates = get_mobility_growth_rates(pkm_data, gdp_by_year, pop_by_year)
    base_year = 2024
    infra_base = infra_data[infra_data['Year'] == base_year].copy()
    base_total = infra_base['Value'].sum()
    
    infra_projections = project_infrastructure_from_mobility(
        infra_data, mobility_growth_rates, scenario_params, infra_to_mobility, pkm_data
    )
    
    if infra_projections.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    
    vehicle_fuel_data = load_vehicle_projections(scenario_name)
    if not vehicle_fuel_data.empty:
        print(f"  Applying vehicle-based infrastructure for {scenario_name}")
        infra_projections = apply_vehicle_based_infrastructure(infra_projections, vehicle_fuel_data, scenario_name)
    
    summary = infra_projections.groupby('Year').agg({'Value': 'sum'}).reset_index()
    pop_for_years = pop_by_year.reindex(summary['Year'])
    summary['Infra_per_capita'] = summary['Value'] / pop_for_years
    summary['Infra_per_capita'] = summary['Infra_per_capita'].replace([np.inf, -np.inf], np.nan)
    
    return infra_projections, summary, {'projections': infra_projections, 'growth_rates': mobility_growth_rates}

######################################################################################################################################################
#%% Wide-format export (MISO2_country x End_use_sector x Year)

def make_wide_export(infra_projections, base_year, end_year=2100):
    """
    Wide format: MISO2_country | End_use_sector | Unit | 2024 | 2025 | ... | 2100
    Infrastructure area in m2 by type.
    """
    years = list(range(base_year, end_year + 1))

    if len(infra_projections) > 0:
        wide = (infra_projections
                .groupby(['Type_lv2', 'Year'])['Value'].sum()
                .unstack('Year'))
    else:
        wide = pd.DataFrame()

    wide = wide.reindex(columns=years)

    wide = wide.copy().fillna(0)
    wide.insert(0, 'MISO2_country', 'Austria')
    wide.insert(1, 'End_use_sector', wide.index)
    wide.insert(2, 'Unit', 'm2')
    wide.columns = ['MISO2_country', 'End_use_sector', 'Unit'] + [str(y) for y in years]
    wide = wide.reset_index(drop=True)

    return wide

######################################################################################################################################################
#%% Projection execution

scenarios_to_run = ['Baseline', 'Mobility Reduction', 'Modal Shift', 'Fleet Electrification']

infra_path = os.path.join(main_path, 'output', 'interim', 'stocks_infra_base.parquet')
data_infrastructure = pd.read_parquet(infra_path)
data_PKM = read_excel(os.path.join(main_path, 'input', 'data_pkm_tkm.xlsx'), sheet_name='input')
data_GDP = read_excel(os.path.join(main_path, 'input', 'data_GDP.xlsx'), sheet_name='input')
data_POP = read_excel(os.path.join(main_path, 'input', 'data_POP.xlsx'), sheet_name='input')

for df in [data_infrastructure, data_PKM, data_GDP, data_POP]:
    df['Value'] = df['Value'].astype(float)

scenario_params_path = os.path.join(main_path, 'input', 'scenario_parameters.xlsx')
base_year = int(data_infrastructure['Year'].min())

all_results, all_summaries, all_proj = {}, {}, {}

scenarios_path = os.path.join('output', 'scenarios', 'infrastructure')
os.makedirs(scenarios_path, exist_ok=True)

for scenario_name in scenarios_to_run:
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name)
    infra_df, summary, proj_dict = run_scenario(
        scenario_name, scenario_params, data_infrastructure, data_PKM, data_GDP, data_POP
    )
    all_results[scenario_name], all_summaries[scenario_name], all_proj[scenario_name] = infra_df, summary, proj_dict

    wide = make_wide_export(infra_df, base_year=base_year, end_year=2100)
    wide.to_csv(os.path.join(scenarios_path, f'MISO2_{scenario_name}.csv'), index=False, sep=';', decimal=',')

######################################################################################################################################################
#%% Results

figures_path = os.path.join('output', 'scenarios', 'infrastructure', 'figures')
os.makedirs(figures_path, exist_ok=True)

#%%% Infrastructure comparison
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

ax = axes[0]
for name, df in all_summaries.items():
    if df is not None and not df.empty:
        ax.plot(df['Year'], df['Value'] / 1e6, label=name, linewidth=2)

ax.set_xlabel('Year')
ax.set_ylabel('Total infrastructure area (million m²)')
ax.set_title('Infrastructure area per scenario')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5, label='Base year (2024)')
ax.legend()

ax = axes[1]
for name, df in all_summaries.items():
    if df is not None and not df.empty:
        base_value = df[df['Year'] == 2024]['Value'].iloc[0] if 2024 in df['Year'].values else df['Value'].iloc[0]
        if base_value > 0:
            ax.plot(df['Year'], df['Value'] / base_value, label=name, linewidth=2)

ax.set_xlabel('Year')
ax.set_ylabel('Total infrastructure (Index 2024=1)')
ax.set_title('Infrastructure growth per scenario')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5, label='Base year')
ax.legend()

plt.tight_layout()
plt.savefig(os.path.join(figures_path, 'infrastructure_comparison.png'), dpi=150, bbox_inches='tight')
plt.show()

#%%% Infrastructure by scenario - All types (similar to vehicle plots)

infra_types_path = os.path.join(figures_path, 'Infrastructure_Types')
os.makedirs(infra_types_path, exist_ok=True)

all_infra_types = []
for scenario_name in scenarios_to_run:
    if scenario_name in all_results:
        df = all_results[scenario_name]
        all_infra_types.extend(df['Type_lv2'].unique().tolist())

unique_infra_types = sorted(list(set(all_infra_types)))
print(f"  Found {len(unique_infra_types)} infrastructure types: {unique_infra_types}")

for infra_type in unique_infra_types:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    ax1 = axes[0]
    for scenario_name in scenarios_to_run:
        if scenario_name in all_results:
            df = all_results[scenario_name]
            df_f = df[df['Year'] >= 2024]
            infra_data = df_f[df_f['Type_lv2'] == infra_type]
            if not infra_data.empty:
                yearly_data = infra_data.groupby('Year')['Value'].sum().reset_index()
                ax1.plot(yearly_data['Year'], yearly_data['Value'] / 1e6, 
                        label=scenario_name, linewidth=2)
    
    ax1.set_xlabel('Year')
    ax1.set_ylabel('Area (million m²)')
    ax1.set_title(f'{infra_type} - Absolute Values')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
    
    ax2 = axes[1]
    for scenario_name in scenarios_to_run:
        if scenario_name in all_results:
            df = all_results[scenario_name]
            df_f = df[df['Year'] >= 2024]
            infra_data = df_f[df_f['Type_lv2'] == infra_type]
            if not infra_data.empty:
                yearly_data = infra_data.groupby('Year')['Value'].sum().reset_index()
                base_value = yearly_data[yearly_data['Year'] == 2024]['Value'].iloc[0] if 2024 in yearly_data['Year'].values else yearly_data['Value'].iloc[0]
                if base_value > 0:
                    ax2.plot(yearly_data['Year'], yearly_data['Value'] / base_value, 
                            label=scenario_name, linewidth=2)
    
    ax2.set_xlabel('Year')
    ax2.set_ylabel('Area (Index 2024=1)')
    ax2.set_title(f'{infra_type} - Indexed Growth')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax2.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    
    clean_name = infra_type.replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
    plt.savefig(os.path.join(infra_types_path, f'infrastructure_type_{clean_name}.png'), 
               dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ Saved: infrastructure_type_{clean_name}.png")

#%%% Infrastructure by mobility group (Baseline only)

if not all_results['Baseline'].empty:
    baseline_df = all_results['Baseline']
    
    infra_to_mobility_group = {
        'motorway': 'Road', 'motorway_bridge': 'Road', 'motorway_tunnel': 'Road',
        'primary': 'Road', 'primary_bridge': 'Road', 'primary_tunnel': 'Road',
        'secondary_bridge': 'Road', 'secondary_tunnel': 'Road',
        'tertiary_bridge': 'Road', 'tertiary_tunnel': 'Road',
        'local': 'Road', 'local_bridge': 'Road', 'local_tunnel': 'Road',
        'secondary': 'Road', 'tertiary': 'Road',
        'track': 'Road', 'track_bridge': 'Road', 'track_tunnel': 'Road',
        'parking_surface': 'Road', 'parking_underground': 'Road', 'parking_building': 'Road',
        'gas_station_building': 'Road', 'charging_station': 'Road',
        'railway': 'Railway', 'railway_bridge': 'Railway', 'railway_tunnel': 'Railway',
        'railway_building': 'Railway', 'railway_building_platform': 'Railway', 'rail_other': 'Railway',
        'subway': 'Subway/tram', 'subway_bridge': 'Subway/tram', 'subway_tunnel': 'Subway/tram',
        'subway_building': 'Subway/tram', 'tram': 'Subway/tram'
    }
    
    baseline_df['Mobility_Group'] = baseline_df['Type_lv2'].map(infra_to_mobility_group)
    mobility_summary = baseline_df.groupby(['Year', 'Mobility_Group'])['Value'].sum().reset_index()
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    ax1 = axes[0]
    for mob_group in mobility_summary['Mobility_Group'].unique():
        if pd.notna(mob_group):
            mob_data = mobility_summary[mobility_summary['Mobility_Group'] == mob_group]
            ax1.plot(mob_data['Year'], mob_data['Value'] / 1e6, label=mob_group, linewidth=2)
    
    ax1.set_xlabel('Year')
    ax1.set_ylabel('Infrastructure area (million m²)')
    ax1.set_title('Infrastructure area by mode - baseline')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
    
    ax2 = axes[1]
    for mob_group in mobility_summary['Mobility_Group'].unique():
        if pd.notna(mob_group):
            mob_data = mobility_summary[mobility_summary['Mobility_Group'] == mob_group]
            base_value = mob_data[mob_data['Year'] == 2024]['Value'].iloc[0] if 2024 in mob_data['Year'].values else mob_data['Value'].iloc[0]
            if base_value > 0:
                ax2.plot(mob_data['Year'], mob_data['Value'] / base_value, label=mob_group, linewidth=2)
    
    ax2.set_xlabel('Year')
    ax2.set_ylabel('Infrastructure area (Index 2024=1)')
    ax2.set_title('Infrastructure growth by mode - baseline')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax2.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(os.path.join(figures_path, 'infrastructure_by_mode_baseline.png'), dpi=150, bbox_inches='tight')
    plt.show()
    
    if not mobility_summary.empty:
        final_year = mobility_summary['Year'].max()
        final_data = mobility_summary[mobility_summary['Year'] == final_year]
        total = final_data['Value'].sum()
        print(f"\nFinal year ({final_year:.0f}) infrastructure by mobility group:")
        for _, row in final_data.iterrows():
            if pd.notna(row['Mobility_Group']):
                print(f"  {row['Mobility_Group']}: {row['Value']/1e6:.2f}M m² ({row['Value']/total*100:.1f}%)")
        
        print(f"\nGrowth from 2024 to {final_year:.0f} by mobility group:")
        for mob_group in mobility_summary['Mobility_Group'].unique():
            if pd.notna(mob_group):
                mob_data = mobility_summary[mobility_summary['Mobility_Group'] == mob_group]
                base_value = mob_data[mob_data['Year'] == 2024]['Value'].iloc[0] if 2024 in mob_data['Year'].values else mob_data['Value'].iloc[0]
                final_value = mob_data[mob_data['Year'] == final_year]['Value'].iloc[0]
                if base_value > 0:
                    growth = ((final_value / base_value) - 1) * 100
                    print(f"  {mob_group}: {growth:.1f}% growth")

#%%% Scenario summary
print("\n" + "="*80)
print("SCENARIO SUMMARY")
print("="*80)

for scenario_name, df in all_summaries.items():
    if df is not None and not df.empty:
        base_value = df[df['Year'] == 2024]['Value'].iloc[0] if 2024 in df['Year'].values else df['Value'].iloc[0]
        last_row = df.iloc[-1]
        first_row = df.iloc[0]
        growth = ((last_row['Value'] / base_value) - 1) * 100 if base_value > 0 else 0
        
        print(f"\n{scenario_name}:")
        print(f"  Base year (2024): {base_value/1e6:.2f}M m²")
        print(f"  First projection ({first_row['Year']:.0f}): {first_row['Value']/1e6:.2f}M m²")
        print(f"  Final year ({last_row['Year']:.0f}): {last_row['Value']/1e6:.2f}M m²")
        print(f"  Growth (2024 to {last_row['Year']:.0f}): {growth:.1f}%")
        
        if scenario_name in all_results:
            df_scenario = all_results[scenario_name]
            
            charge_last = df_scenario[(df_scenario['Type_lv2'] == 'charging_station') & (df_scenario['Year'] == last_row['Year'])]['Value'].sum()
            charge_base = df_scenario[(df_scenario['Type_lv2'] == 'charging_station') & (df_scenario['Year'] == 2024)]['Value'].sum()
            
            gas_last = df_scenario[(df_scenario['Type_lv2'] == 'gas_station_building') & (df_scenario['Year'] == last_row['Year'])]['Value'].sum()
            gas_base = df_scenario[(df_scenario['Type_lv2'] == 'gas_station_building') & (df_scenario['Year'] == 2024)]['Value'].sum()
            
            print(f"\n  Charging stations:")
            print(f"    2024: {charge_base/1e3:.1f}k")
            print(f"    {last_row['Year']:.0f}: {charge_last/1e3:.1f}k")
            if charge_base > 0:
                print(f"    Growth: {((charge_last/charge_base)-1)*100:.1f}%")
            else:
                print("    No base data")
            
            print(f"\n  Gas stations:")
            print(f"    2024: {gas_base/1e3:.1f}k")
            print(f"    {last_row['Year']:.0f}: {gas_last/1e3:.1f}k")
            if gas_base > 0:
                print(f"    Growth: {((gas_last/gas_base)-1)*100:.1f}%")
            else:
                print("    No base data")

print("\n" + "="*80)
print("INFRASTRUCTURE PROJECTION COMPLETE")
print("="*80)