#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Vehicle fleet projections with scenario analysis
'''

#%% Notes

# Vehicle fleet projections based on:
# - Historical correlation between vehicle stock and PKM/TKM
# - GDP-driven projection of PKM/TKM
# - Demand reduction scenarios (Mobility Reduction)

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df.loc[:, 'Parameter':'Value']

######################################################################################################################################################
######################################################################################################################################################
#%% Scenarios

def load_scenario_parameters(file_path, scenario_name):
    """
    Load scenario parameters from 'vehicles' sheet
    """
    try:
        df_scenarios = pd.read_excel(file_path, sheet_name='vehicles')
    except:
        # If sheet doesn't exist, return default parameters
        if 'Mobility Reduction' in scenario_name:
            return {'demand_reduction': 0.8, 'start_year': 2024, 'end_year': 2060}
        else:
            return {'demand_reduction': 1.0, 'start_year': 2024, 'end_year': 2024}
    
    df_scenarios = df_scenarios[~df_scenarios['Scenario Name'].str.startswith(('Parameter', 'Percenrage'), na=False) & 
                                df_scenarios['Scenario Name'].notna() & 
                                (df_scenarios['Scenario Name'] != '')]
    scenario = df_scenarios[df_scenarios['Scenario Name'] == scenario_name]
    
    if scenario.empty:
        if 'Mobility Reduction' in scenario_name:
            return {'demand_reduction': 0.8, 'start_year': 2024, 'end_year': 2060}
        else:
            return {'demand_reduction': 1.0, 'start_year': 2024, 'end_year': 2024}
    
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
    
    demand_reduction = get_param('Demand Reduction', 1.0)
    start_year = int(get_param('Start Year', 2024))
    end_year = int(get_param('End Year', 2060))
    
    return {
        'demand_reduction': demand_reduction,
        'start_year': start_year,
        'end_year': end_year
    }

######################################################################################################################################################
######################################################################################################################################################
#%% Vehicle projection

def get_phase_in_factor(year, start_year, end_year, target_factor):
    """
    Calculate the phase-in factor for policies.
    Starts at 1.0 at start_year, reaches target_factor by end_year.
    """
    if year <= start_year:
        return 1.0
    elif year >= end_year:
        return target_factor
    else:
        progress = (year - start_year) / (end_year - start_year)
        return 1.0 - (1.0 - target_factor) * progress

def get_elasticity(pkm_type, pkm_data, gdp_by_year, pop_by_year):
    """
    Calculate GDP elasticity for a given PKM type using historical data.
    """
    type_data = pkm_data[pkm_data['Type_lv2'] == pkm_type].copy()
    hist_years = type_data['Year'].values
    hist_pkm = type_data['Value'].values
    
    valid = ~np.isnan(hist_pkm)
    hist_years = hist_years[valid]
    hist_pkm = hist_pkm[valid]
    
    if len(hist_years) < 3:
        return 0.5
    
    hist_gdp = []
    hist_pop = []
    for y in hist_years:
        if y in gdp_by_year.index:
            hist_gdp.append(gdp_by_year[y])
        else:
            closest = min(gdp_by_year.index, key=lambda x: abs(x - y))
            hist_gdp.append(gdp_by_year[closest])
        
        if y in pop_by_year.index:
            hist_pop.append(pop_by_year[y])
        else:
            closest = min(pop_by_year.index, key=lambda x: abs(x - y))
            hist_pop.append(pop_by_year[closest])
    
    pkm_per_capita = np.array(hist_pkm) / np.array(hist_pop)
    gdp_values = np.array(hist_gdp)
    
    log_gdp = np.log(gdp_values)
    log_pkm = np.log(pkm_per_capita)
    
    try:
        slope, _, r_value, _, _ = linregress(log_gdp, log_pkm)
        return slope if abs(slope) < 2 else 0.5  # Cap elasticity at reasonable range
    except:
        return 0.5

def project_pkm(pkm_type, pkm_data, gdp_by_year, pop_by_year, scenario_params):
    """
    Project PKM for a single type using GDP elasticity.
    """
    type_data = pkm_data[pkm_data['Type_lv2'] == pkm_type].copy()
    hist_years = type_data['Year'].values
    hist_pkm = type_data['Value'].values
    
    valid = ~np.isnan(hist_pkm)
    hist_years = hist_years[valid]
    hist_pkm = hist_pkm[valid]
    
    if len(hist_years) < 3:
        return pd.DataFrame()
    
    # Get base year data
    base_year = hist_years[-1]
    base_pop = pop_by_year.get(base_year, pop_by_year.iloc[0])
    base_gdp = gdp_by_year.get(base_year, gdp_by_year.iloc[0])
    base_pkm = hist_pkm[-1]
    
    # Calculate elasticity
    elasticity = get_elasticity(pkm_type, pkm_data, gdp_by_year, pop_by_year)
    
    # Project future years
    future_years = [y for y in range(base_year + 1, 2101) 
                   if y in gdp_by_year.index and y in pop_by_year.index]
    
    projections = []
    for year in future_years:
        gdp_ratio = gdp_by_year[year] / base_gdp
        pop_cur = pop_by_year[year]
        
        # GDP elasticity model
        pkm_proj = base_pkm * (pop_cur / base_pop) * (gdp_ratio ** elasticity)
        
        # Apply demand reduction
        reduction_factor = get_phase_in_factor(
            year,
            scenario_params['start_year'],
            scenario_params['end_year'],
            scenario_params['demand_reduction']
        )
        pkm_proj = pkm_proj * reduction_factor
        
        projections.append({'Year': year, 'PKM': pkm_proj})
    
    return pd.DataFrame(projections)

def get_correlation_factors(vehicle_data, pkm_data):
    """
    Calculate correlation factors between vehicle types and PKM types.
    """
    vehicle_to_pkm = {
        'Cars': 'Cars',
        'Buses': 'Buses',
        'Railway_passenger_train_electric': 'Rail',
        'Railway_passenger_train_fossil': 'Rail',
        'Railway_passenger_car': 'Rail',
        'Railway_freight_train_electric': 'Rail',
        'Railway_freight_train_fossil': 'Rail',
        'Railway_freight_car': 'Rail',
        'Tram_train': 'Subway/tram',
        'Tram_car': 'Subway/tram',
        'Subway_car': 'Subway/tram',
        'Subway_train': 'Subway/tram',
        'Trucks': 'Road',
        'Vehicles_other': 'Road',
        'Moped': 'Cars',
        'Motorcycles': 'Cars',
        'Trailers': 'Road'
    }
    
    correlation_factors = {}
    
    for vehicle_type, pkm_type in vehicle_to_pkm.items():
        vehicle_type_data = vehicle_data[vehicle_data['Type_lv2'] == vehicle_type]
        if vehicle_type_data.empty:
            continue
        
        pkm_type_data = pkm_data[pkm_data['Type_lv2'] == pkm_type]
        if pkm_type_data.empty:
            continue
        
        merged = pd.merge(
            vehicle_type_data[['Year_from', 'Value']].rename(columns={'Year_from': 'Year', 'Value': 'Vehicles'}),
            pkm_type_data[['Year', 'Value']].rename(columns={'Value': 'PKM'}),
            on='Year',
            how='inner'
        )
        
        if len(merged) < 3:
            continue
        
        merged['Vehicles_per_PKM'] = merged['Vehicles'] / merged['PKM']
        correlation_factor = merged['Vehicles_per_PKM'].median()
        
        correlation_factors[vehicle_type] = {
            'pkm_type': pkm_type,
            'factor': correlation_factor
        }
    
    # Handle Bicycles and E-bikes separately (only 1 datapoint each)
    bicycle_data = vehicle_data[vehicle_data['Type_lv2'] == 'Bicycles']
    e_bike_data = vehicle_data[vehicle_data['Type_lv2'] == 'E_bikes']
    cycling_pkm = pkm_data[pkm_data['Type_lv2'] == 'Cycling']
    
    if not bicycle_data.empty and not cycling_pkm.empty:
        year = bicycle_data['Year_from'].iloc[0]
        vehicles = bicycle_data['Value'].iloc[0]
        pkm = cycling_pkm[cycling_pkm['Year'] == year]['Value'].iloc[0] if year in cycling_pkm['Year'].values else cycling_pkm['Value'].iloc[0]
        correlation_factors['Bicycles'] = {'pkm_type': 'Cycling', 'factor': vehicles / pkm}
    
    if not e_bike_data.empty and not cycling_pkm.empty:
        year = e_bike_data['Year_from'].iloc[0]
        vehicles = e_bike_data['Value'].iloc[0]
        pkm = cycling_pkm[cycling_pkm['Year'] == year]['Value'].iloc[0] if year in cycling_pkm['Year'].values else cycling_pkm['Value'].iloc[0]
        correlation_factors['E_bikes'] = {'pkm_type': 'Cycling', 'factor': vehicles / pkm}
    
    return correlation_factors

def run_scenario(scenario_name, scenario_params, vehicle_data, pkm_data, gdp_data, pop_data):
    """
    Run vehicle scenario projection for a single scenario.
    """
    print(f"\nRunning {scenario_name}...")
    print(f"  Demand reduction: {scenario_params['demand_reduction']:.2f} (target by {scenario_params['end_year']})")
    
    # Prepare time series
    gdp_by_year = gdp_data.set_index('Year_from')['Value']
    pop_by_year = pop_data[pop_data['Year_to'] <= 2100].set_index('Year_to')['Value']
    
    # Get PKM types to project (skip Active, Walking, Cycling, Road)
    pkm_types = [t for t in pkm_data['Type_lv2'].unique() 
                 if t not in ['Active', 'Walking', 'Cycling', 'Road']]
    
    print(f"  Projecting {len(pkm_types)} PKM types...")
    
    # Project PKM for each type
    pkm_projections = {}
    for pkm_type in pkm_types:
        df = project_pkm(pkm_type, pkm_data, gdp_by_year, pop_by_year, scenario_params)
        if not df.empty:
            pkm_projections[pkm_type] = df
    
    # Handle Cycling separately
    cycling_data = pkm_data[pkm_data['Type_lv2'] == 'Cycling']
    if not cycling_data.empty:
        df = project_pkm('Cycling', pkm_data, gdp_by_year, pop_by_year, scenario_params)
        if not df.empty:
            pkm_projections['Cycling'] = df
    
    print(f"  Generated PKM projections for {len(pkm_projections)} types")
    
    # Get correlation factors
    correlation_factors = get_correlation_factors(vehicle_data, pkm_data)
    print(f"  Found {len(correlation_factors)} vehicle-PKM correlations")
    
    # Project vehicles from PKM
    all_vehicles = []
    for vehicle_type, corr_info in correlation_factors.items():
        pkm_type = corr_info['pkm_type']
        factor = corr_info['factor']
        
        if pkm_type not in pkm_projections:
            continue
        
        pkm_df = pkm_projections[pkm_type]
        if pkm_df.empty:
            continue
        
        for _, row in pkm_df.iterrows():
            all_vehicles.append({
                'Type_lv2': vehicle_type,
                'Year': row['Year'],
                'Value': row['PKM'] * factor
            })
    
    vehicles_df = pd.DataFrame(all_vehicles)
    
    if vehicles_df.empty:
        print("  ✗ No vehicle projections generated!")
        return pd.DataFrame(), pd.DataFrame(), {}
    
    # Create summary
    summary = vehicles_df.groupby('Year').agg({'Value': 'sum'}).reset_index()
    summary['Vehicles_per_1000'] = summary['Value'] / pop_by_year.reindex(summary['Year']).fillna(0) * 1000
    summary['Vehicles_per_1000'] = summary['Vehicles_per_1000'].replace([np.inf, -np.inf], 0)
    
    # Save results
    os.makedirs(f'output/scenarios/{scenario_name}', exist_ok=True)
    vehicles_df.to_parquet(f'output/scenarios/{scenario_name}/vehicles_projected.parquet', index=False)
    summary.to_csv(f'output/scenarios/{scenario_name}/vehicle_summary.csv', index=False)
    
    # Also save PKM projections
    pkm_combined = pd.DataFrame()
    for pkm_type, df in pkm_projections.items():
        if not df.empty:
            df_copy = df.copy()
            df_copy['Type'] = pkm_type
            pkm_combined = pd.concat([pkm_combined, df_copy], ignore_index=True)
    
    if not pkm_combined.empty:
        pkm_combined.to_parquet(f'output/scenarios/{scenario_name}/pkm_projected.parquet', index=False)
    
    print(f"  ✓ Generated {len(vehicles_df):,} vehicle records")
    print(f"  ✓ Total vehicles in {summary['Year'].max()}: {summary['Value'].iloc[-1]:,.0f}")
    
    return vehicles_df, summary, pkm_projections

######################################################################################################################################################
######################################################################################################################################################
#%% Projection execution

print("\n" + "="*80)
print("RUNNING VEHICLE SCENARIOS")
print("="*80)

# Define scenarios to run
scenarios_to_run = ['Baseline', 'Mobility Reduction']

# Load data
print("\nLoading data...")
data_vehicles = read_excel(os.path.join(main_path, 'input', 'data_vehicle_fleet.xlsx'), sheet_name='input')
data_PKM = read_excel(os.path.join(main_path, 'input', 'data_pkm_tkm.xlsx'), sheet_name='input')
data_GDP = read_excel(os.path.join(main_path, 'input', 'data_GDP.xlsx'), sheet_name='input')
data_POP = read_excel(os.path.join(main_path, 'input', 'data_POP.xlsx'), sheet_name='input')

print(f"  Vehicles: {len(data_vehicles)} records")
print(f"  PKM/TKM: {len(data_PKM)} records")
print(f"  GDP: {len(data_GDP)} records")
print(f"  Population: {len(data_POP)} records")

# Process data
print("\nProcessing data...")
data_vehicles['Value'] = data_vehicles['Value'].astype(float)
data_PKM['Value'] = data_PKM['Value'].astype(float)
data_GDP['Value'] = data_GDP['Value'].astype(float)
data_POP['Value'] = data_POP['Value'].astype(float)
print("  ✓ Data processed")

# Load scenario parameters
scenario_params_path = os.path.join(main_path, 'input', 'scenario_parameters.xlsx')

# Run all scenarios
all_results = {}
all_summaries = {}
all_pkm = {}

for scenario_name in scenarios_to_run:
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name)
    vehicles_df, summary, pkm_projections = run_scenario(
        scenario_name, scenario_params, data_vehicles, data_PKM, data_GDP, data_POP
    )
    all_results[scenario_name] = vehicles_df
    all_summaries[scenario_name] = summary
    all_pkm[scenario_name] = pkm_projections

######################################################################################################################################################
######################################################################################################################################################
#%% Results

#%%% Vehicle fleet comparison

print("\n" + "="*80)
print("GENERATING PLOTS")
print("="*80)

# Figure 1: Vehicle fleet comparison (2 subplots)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Subplot 1: Total vehicle fleet
ax = axes[0]
for name, df in all_summaries.items():
    if not df.empty:
        ax.plot(df['Year'], df['Value'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Total Vehicles (millions)')
ax.set_title('Vehicle Fleet Comparison')
ax.legend()
ax.grid(True, alpha=0.3)

# Subplot 2: Total vehicles indexed (Baseline = 1)
ax = axes[1]
for name, df in all_summaries.items():
    if not df.empty:
        base_value = df['Value'].iloc[0]
        if base_value > 0:
            ax.plot(df['Year'], df['Value'] / base_value, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Total Vehicles (Indexed to base year)')
ax.set_title('Vehicle Fleet Growth (Indexed)')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

plt.tight_layout()
os.makedirs('output/scenarios', exist_ok=True)
plt.savefig('output/scenarios/vehicle_comparison.png', dpi=150, bbox_inches='tight')
plt.show()
print("  ✓ Saved vehicle_comparison.png")

#%%% PKM comparison (indexed)

print("\n" + "="*80)
print("GENERATING PKM PLOTS")
print("="*80)

fig, axes = plt.subplots(2, 2, figsize=(16, 10))

# PKM types to plot
pkm_types_to_plot = ['Cars', 'Rail', 'Buses', 'Subway/tram']

# Subplot 1: Cars PKM
ax = axes[0, 0]
for scenario_name, pkm_dict in all_pkm.items():
    if 'Cars' in pkm_dict:
        df = pkm_dict['Cars']
        if not df.empty:
            base_value = df['PKM'].iloc[0] if not df.empty else 1
            ax.plot(df['Year'], df['PKM'] / base_value, label=scenario_name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Cars PKM (Indexed)')
ax.set_title('Cars PKM Growth')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

# Subplot 2: Rail PKM
ax = axes[0, 1]
for scenario_name, pkm_dict in all_pkm.items():
    if 'Rail' in pkm_dict:
        df = pkm_dict['Rail']
        if not df.empty:
            base_value = df['PKM'].iloc[0] if not df.empty else 1
            ax.plot(df['Year'], df['PKM'] / base_value, label=scenario_name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Rail PKM (Indexed)')
ax.set_title('Rail PKM Growth')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

# Subplot 3: Buses PKM
ax = axes[1, 0]
for scenario_name, pkm_dict in all_pkm.items():
    if 'Buses' in pkm_dict:
        df = pkm_dict['Buses']
        if not df.empty:
            base_value = df['PKM'].iloc[0] if not df.empty else 1
            ax.plot(df['Year'], df['PKM'] / base_value, label=scenario_name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Buses PKM (Indexed)')
ax.set_title('Buses PKM Growth')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

# Subplot 4: Subway/tram PKM
ax = axes[1, 1]
for scenario_name, pkm_dict in all_pkm.items():
    if 'Subway/tram' in pkm_dict:
        df = pkm_dict['Subway/tram']
        if not df.empty:
            base_value = df['PKM'].iloc[0] if not df.empty else 1
            ax.plot(df['Year'], df['PKM'] / base_value, label=scenario_name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Subway/Tram PKM (Indexed)')
ax.set_title('Subway/Tram PKM Growth')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('output/scenarios/pkm_comparison.png', dpi=150, bbox_inches='tight')
plt.show()
print("  ✓ Saved pkm_comparison.png")

#%%% Scenario summary

print("\n" + "="*80)
print("SCENARIO SUMMARY")
print("="*80)

for scenario_name, df in all_summaries.items():
    if not df.empty:
        last_year = df['Year'].max()
        last_row = df[df['Year'] == last_year].iloc[0]
        first_row = df.iloc[0]
        
        growth = ((last_row['Value'] / first_row['Value']) - 1) * 100 if first_row['Value'] > 0 else 0
        
        print(f"\n{scenario_name}:")
        print(f"  Base year ({first_row['Year']}): {first_row['Value']/1e6:.2f}M vehicles")
        print(f"  Final year ({last_year}): {last_row['Value']/1e6:.2f}M vehicles")
        print(f"  Growth: {growth:.1f}%")
        if 'Vehicles_per_1000' in last_row:
            print(f"  Ownership rate: {last_row['Vehicles_per_1000']:.1f} per 1,000")

# Calculate reduction percentages
if 'Baseline' in all_summaries and 'Mobility Reduction' in all_summaries:
    base_df = all_summaries['Baseline']
    red_df = all_summaries['Mobility Reduction']
    
    if not base_df.empty and not red_df.empty:
        # Align years
        merged = pd.merge(
            base_df[['Year', 'Value']].rename(columns={'Value': 'Baseline'}),
            red_df[['Year', 'Value']].rename(columns={'Value': 'Reduced'}),
            on='Year',
            how='inner'
        )
        merged['Reduction'] = (1 - merged['Reduced'] / merged['Baseline']) * 100
        
        last_year = merged['Year'].max()
        last_row = merged[merged['Year'] == last_year].iloc[0]
        
        print(f"\n{'-'*50}")
        print(f"Mobility Reduction vs Baseline:")
        print(f"  Final year reduction: {last_row['Reduction']:.1f}%")
        print(f"  Baseline: {last_row['Baseline']/1e6:.2f}M vehicles")
        print(f"  Reduced: {last_row['Reduced']/1e6:.2f}M vehicles")

print("\n" + "="*80)
print("VEHICLE PROJECTION COMPLETE")
print("="*80)