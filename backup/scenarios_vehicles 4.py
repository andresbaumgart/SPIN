#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Vehicle fleet projections
'''

#%% Notes

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
    
    # Clean the data - remove header rows and empty rows
    df_scenarios = df_scenarios[~df_scenarios['Scenario Name'].str.startswith(('Parameter', 'Percenrage'), na=False) & 
                                df_scenarios['Scenario Name'].notna() & 
                                (df_scenarios['Scenario Name'] != '')]
    
    # Find the scenario
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
    
    demand_reduction = get_param('Demand Reduction', 1.0)
    start_year = int(get_param('Start Year', 2024))
    end_year = int(get_param('End Year', 2060))
    pkm_shift_to_rail = get_param('PKM Shift to Rail', 0.0)
    tkm_shift_to_rail = get_param('TKM Shift to Rail', 0.0)
    
    return {
        'demand_reduction': demand_reduction,
        'start_year': start_year,
        'end_year': end_year,
        'pkm_shift_to_rail': pkm_shift_to_rail,
        'tkm_shift_to_rail': tkm_shift_to_rail
    }

######################################################################################################################################################
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
        return slope if abs(slope) < 2 else 0.5
    except:
        return 0.5

def project_pkm(pkm_type, pkm_data, gdp_by_year, pop_by_year, scenario_params):

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
        
        # Apply demand reduction if specified in Excel
        reduction_factor = get_phase_in_factor(
            year,
            scenario_params['start_year'],
            scenario_params['end_year'],
            scenario_params['demand_reduction']
        )
        pkm_proj = pkm_proj * reduction_factor
        
        projections.append({'Year': year, 'PKM': pkm_proj})
    
    return pd.DataFrame(projections)

def apply_modal_shift_to_pkm(pkm_projections, scenario_params):

    if scenario_params['pkm_shift_to_rail'] == 0:
        return pkm_projections
    
    if 'Cars' not in pkm_projections:
        return pkm_projections
    
    base_year = 2024
    shift_target = scenario_params['pkm_shift_to_rail']
    start_year = scenario_params['start_year']
    end_year = scenario_params['end_year']
    
    # Check which rail types are available
    rail_types_available = []
    if 'Rail' in pkm_projections:
        rail_types_available.append('Rail')
    if 'Subway/tram' in pkm_projections:
        rail_types_available.append('Subway/tram')
    
    if not rail_types_available:
        return pkm_projections
    
    # Calculate base year totals for each rail type to maintain ratio
    rail_base_totals = {}
    for rail_type in rail_types_available:
        rail_type_data = pkm_projections[rail_type]
        rail_base_totals[rail_type] = rail_type_data[rail_type_data['Year'] == base_year]['PKM'].iloc[0] if base_year in rail_type_data['Year'].values else rail_type_data['PKM'].iloc[0]
    
    total_rail_base = sum(rail_base_totals.values())
    
    # Create copies
    cars_shifted = pkm_projections['Cars'].copy()
    rail_shifted = {}
    for rail_type in rail_types_available:
        rail_shifted[rail_type] = pkm_projections[rail_type].copy()
    
    for idx, row in cars_shifted.iterrows():
        year = row['Year']
        
        # No shift in base year or before
        if year <= base_year:
            continue
        
        # Phase-in the shift GRADUALLY
        if year <= start_year:
            phase_in = 0.0
        elif year >= end_year:
            phase_in = 1.0
        else:
            progress = (year - start_year) / (end_year - start_year)
            phase_in = progress
        
        # Calculate total shift amount from Cars
        shift_amount = row['PKM'] * shift_target * phase_in
        
        # Reduce Cars
        cars_shifted.loc[idx, 'PKM'] = row['PKM'] - shift_amount
        
        # Distribute shift to rail types proportionally to their base year shares
        for rail_type in rail_types_available:
            if total_rail_base > 0:
                # Maintain the same ratio as base year
                rail_share = rail_base_totals[rail_type] / total_rail_base
                rail_add = shift_amount * rail_share
            else:
                # If no rail in base year, split equally
                rail_add = shift_amount / len(rail_types_available)
            
            # Add to this rail type
            rail_idx = rail_shifted[rail_type][rail_shifted[rail_type]['Year'] == year].index
            if len(rail_idx) > 0:
                rail_shifted[rail_type].loc[rail_idx[0], 'PKM'] = rail_shifted[rail_type].loc[rail_idx[0], 'PKM'] + rail_add
    
    pkm_projections['Cars'] = cars_shifted
    for rail_type in rail_types_available:
        pkm_projections[rail_type] = rail_shifted[rail_type]
    
    return pkm_projections

def get_correlation_factors(vehicle_data, pkm_data):

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
    
    # Handle Bicycles and E-bikes separately
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
    
    # Prepare time series
    gdp_by_year = gdp_data.set_index('Year_from')['Value']
    pop_by_year = pop_data[pop_data['Year_to'] <= 2100].set_index('Year_to')['Value']
    
    # Get PKM types to project
    pkm_types = [t for t in pkm_data['Type_lv2'].unique() 
                 if t not in ['Active', 'Walking', 'Cycling', 'Road']]
    
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
    
    # Apply modal shift for PKM if specified in Excel
    if scenario_params['pkm_shift_to_rail'] > 0:
        pkm_projections = apply_modal_shift_to_pkm(pkm_projections, scenario_params)
    
    # Get correlation factors
    correlation_factors = get_correlation_factors(vehicle_data, pkm_data)
    
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
        return pd.DataFrame(), pd.DataFrame(), {}
    
    # Create summary
    summary = vehicles_df.groupby('Year').agg({'Value': 'sum'}).reset_index()
    summary['Vehicles_per_1000'] = summary['Value'] / pop_by_year.reindex(summary['Year']).fillna(0) * 1000
    summary['Vehicles_per_1000'] = summary['Vehicles_per_1000'].replace([np.inf, -np.inf], 0)
    
    # Save results
    os.makedirs('output/Vehicles', exist_ok=True)
    vehicles_df.to_parquet(f'output/Vehicles/vehicles_projected_{scenario_name}.parquet', index=False)
    summary.to_csv(f'output/Vehicles/vehicle_summary_{scenario_name}.csv', index=False)
    
    # Also save PKM projections
    pkm_combined = pd.DataFrame()
    for pkm_type, df in pkm_projections.items():
        if not df.empty:
            df_copy = df.copy()
            df_copy['Type'] = pkm_type
            pkm_combined = pd.concat([pkm_combined, df_copy], ignore_index=True)
    
    if not pkm_combined.empty:
        pkm_combined.to_parquet(f'output/Vehicles/pkm_projected_{scenario_name}.parquet', index=False)
    
    print(f"  ✓ Generated {len(vehicles_df):,} vehicle records")
    
    return vehicles_df, summary, pkm_projections

######################################################################################################################################################
######################################################################################################################################################
#%% Projection execution

scenarios_to_run = ['Baseline', 'Mobility Reduction', 'Modal Shift']

data_vehicles = read_excel(os.path.join(main_path, 'input', 'data_vehicle_fleet.xlsx'), sheet_name='input')
data_PKM = read_excel(os.path.join(main_path, 'input', 'data_pkm_tkm.xlsx'), sheet_name='input')
data_GDP = read_excel(os.path.join(main_path, 'input', 'data_GDP.xlsx'), sheet_name='input')
data_POP = read_excel(os.path.join(main_path, 'input', 'data_POP.xlsx'), sheet_name='input')

data_vehicles['Value'] = data_vehicles['Value'].astype(float)
data_PKM['Value'] = data_PKM['Value'].astype(float)
data_GDP['Value'] = data_GDP['Value'].astype(float)
data_POP['Value'] = data_POP['Value'].astype(float)

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

# Create Figures folder
figures_path = os.path.join('output', 'Vehicles', 'Figures')
os.makedirs(figures_path, exist_ok=True)

#%%% Vehicle fleet comparison

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
for name, df in all_summaries.items():
    if not df.empty:
        df_filtered = df[df['Year'] >= 2024]
        if not df_filtered.empty:
            ax.plot(df_filtered['Year'], df_filtered['Value'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Total Vvhicles (millions)')
ax.set_title('Vehicle fleet Comparison')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5, label='Base year')
ax.legend()

# Subplot 2: Total vehicles indexed (2024 = 1)
ax = axes[1]
for name, df in all_summaries.items():
    if not df.empty:
        df_filtered = df[df['Year'] >= 2024]
        if not df_filtered.empty:
            base_value = df_filtered[df_filtered['Year'] == 2024]['Value'].iloc[0] if 2024 in df_filtered['Year'].values else df_filtered['Value'].iloc[0]
            if base_value > 0:
                ax.plot(df_filtered['Year'], df_filtered['Value'] / base_value, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Total vehicles (Index 2024=1)')
ax.set_title('Vehicle fleet growth (Indexed)')
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)
ax.legend()

plt.tight_layout()
plt.savefig(os.path.join(figures_path, 'vehicle_comparison.png'), dpi=150, bbox_inches='tight')
plt.show()

#%%% PKM/TKM comparison (2x3 grid)

fig, axes = plt.subplots(2, 3, figsize=(18, 10))

# PKM types to plot (top row)
pkm_types_to_plot = ['Cars', 'Rail', 'Subway/tram', 'Buses']

# TKM types to plot (bottom row)
tkm_types_to_plot = ['Road', 'Rail']

# Check which PKM types actually exist in the data
available_pkm_types = []
for pkm_type in pkm_types_to_plot:
    for scenario_name, pkm_dict in all_pkm.items():
        if pkm_type in pkm_dict and not pkm_dict[pkm_type].empty:
            available_pkm_types.append(pkm_type)
            break

# Check which TKM types exist in the data
available_tkm_types = []
if 'Road' in data_PKM['Type_lv2'].unique():
    # We need to project TKM separately
    # Check if TKM data exists in the PKM data (same sheet)
    tkm_data = data_PKM[data_PKM['Type_lv2'].isin(['Road', 'Rail'])]
    if not tkm_data.empty:
        # Get TKM types from the data
        for tkm_type in tkm_types_to_plot:
            if tkm_type in tkm_data['Type_lv2'].unique():
                available_tkm_types.append(tkm_type)

# Plot PKM types (top row)
for idx, pkm_type in enumerate(available_pkm_types[:3]):  # Max 3 columns
    ax = axes[0, idx]
    
    for scenario_name, pkm_dict in all_pkm.items():
        if pkm_type in pkm_dict:
            df = pkm_dict[pkm_type]
            if not df.empty:
                df_filtered = df[df['Year'] >= 2024]
                if not df_filtered.empty:
                    base_value = df_filtered[df_filtered['Year'] == 2024]['PKM'].iloc[0] if 2024 in df_filtered['Year'].values else df_filtered['PKM'].iloc[0]
                    if base_value > 0:
                        ax.plot(df_filtered['Year'], df_filtered['PKM'] / base_value, label=scenario_name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel(f'{pkm_type} pkm (Index 2024=1)')
    ax.set_title(f'{pkm_type} pkm growth')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)

# If Buses is available, add it as the 4th plot in a separate row or column
if 'Buses' in available_pkm_types and len(available_pkm_types) <= 3:
    # If we have 3 or fewer PKM types, we can add Buses
    pass  # Already handled above

# Plot TKM types (bottom row)
for idx, tkm_type in enumerate(available_tkm_types[:3]):  # Max 3 columns
    ax = axes[1, idx]
    
    # Project TKM for each scenario
    for scenario_name in scenarios_to_run:
        # Get TKM data for this type
        tkm_data_type = data_PKM[data_PKM['Type_lv2'] == tkm_type].copy()
        
        if tkm_data_type.empty:
            continue
        
        # Get scenario parameters for this scenario
        scenario_params = load_scenario_parameters(scenario_params_path, scenario_name)
        
        # Project TKM using the same function as PKM
        gdp_by_year = data_GDP.set_index('Year_from')['Value']
        pop_by_year = data_POP[data_POP['Year_to'] <= 2100].set_index('Year_to')['Value']
        
        tkm_df = project_pkm(tkm_type, data_PKM, gdp_by_year, pop_by_year, scenario_params)
        
        if not tkm_df.empty:
            df_filtered = tkm_df[tkm_df['Year'] >= 2024]
            if not df_filtered.empty:
                base_value = df_filtered[df_filtered['Year'] == 2024]['PKM'].iloc[0] if 2024 in df_filtered['Year'].values else df_filtered['PKM'].iloc[0]
                if base_value > 0:
                    ax.plot(df_filtered['Year'], df_filtered['PKM'] / base_value, label=scenario_name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel(f'{tkm_type} tkm (Index 2024=1)')
    ax.set_title(f'{tkm_type} Freight tkm growth')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5)

# Hide any empty subplots
for idx in range(len(available_pkm_types[:3]), 3):
    if idx < 3:
        axes[0, idx].axis('off')
for idx in range(len(available_tkm_types[:3]), 3):
    if idx < 3:
        axes[1, idx].axis('off')

plt.tight_layout()
plt.savefig(os.path.join(figures_path, 'pkm_tkm_comparison.png'), dpi=150, bbox_inches='tight')
plt.show()

#%%% Scenario summary with vehicle type breakdown

for scenario_name, df in all_summaries.items():
    if not df.empty:
        df_filtered = df[df['Year'] >= 2024]
        if df_filtered.empty:
            continue
            
        last_year = df_filtered['Year'].max()
        last_row = df_filtered[df_filtered['Year'] == last_year].iloc[0]
        first_row = df_filtered[df_filtered['Year'] == 2024].iloc[0] if 2024 in df_filtered['Year'].values else df_filtered.iloc[0]
        
        growth = ((last_row['Value'] / first_row['Value']) - 1) * 100 if first_row['Value'] > 0 else 0
        
        print(f"\n{scenario_name}:")
        print(f"  Base year (2024): {first_row['Value']/1e6:.2f}M vehicles")
        print(f"  Final year ({last_year:.0f}): {last_row['Value']/1e6:.2f}M vehicles")
        print(f"  Growth (2024 to {last_year:.0f}): {growth:.1f}%")
        
        # Breakdown by vehicle type
        if scenario_name in all_results:
            vehicles_df = all_results[scenario_name]
            final_vehicles = vehicles_df[vehicles_df['Year'] == last_year]
            if not final_vehicles.empty:
                print(f"\n  Vehicle type breakdown ({last_year:.0f}):")
                # Group by main vehicle categories
                car_types = ['Cars', 'Moped', 'Motorcycles']
                rail_types = ['Railway_passenger_train_electric', 'Railway_passenger_train_fossil', 
                              'Railway_passenger_car', 'Railway_freight_train_electric',
                              'Railway_freight_train_fossil', 'Railway_freight_car']
                bus_types = ['Buses']
                tram_types = ['Tram_train', 'Tram_car']
                subway_types = ['Subway_car', 'Subway_train']
                
                car_total = final_vehicles[final_vehicles['Type_lv2'].isin(car_types)]['Value'].sum()
                rail_total = final_vehicles[final_vehicles['Type_lv2'].isin(rail_types)]['Value'].sum()
                bus_total = final_vehicles[final_vehicles['Type_lv2'].isin(bus_types)]['Value'].sum()
                tram_total = final_vehicles[final_vehicles['Type_lv2'].isin(tram_types)]['Value'].sum()
                subway_total = final_vehicles[final_vehicles['Type_lv2'].isin(subway_types)]['Value'].sum()
                
                print(f"    Cars (including motorcycles): {car_total/1e6:.2f}M")
                print(f"    Rail vehicles: {rail_total/1e6:.2f}M")
                print(f"    Buses: {bus_total/1e6:.2f}M")
                print(f"    Trams: {tram_total/1e6:.2f}M")
                print(f"    Subway: {subway_total/1e6:.2f}M")

# Calculate reduction percentages
if 'Baseline' in all_summaries and 'Mobility Reduction' in all_summaries:
    base_df = all_summaries['Baseline']
    red_df = all_summaries['Mobility Reduction']
    
    if not base_df.empty and not red_df.empty:
        base_df = base_df[base_df['Year'] >= 2024]
        red_df = red_df[red_df['Year'] >= 2024]
        
        if not base_df.empty and not red_df.empty:
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

# Calculate modal shift effect
if 'Baseline' in all_summaries and 'Modal Shift' in all_summaries:
    base_df = all_summaries['Baseline']
    shift_df = all_summaries['Modal Shift']
    
    if not base_df.empty and not shift_df.empty:
        base_df = base_df[base_df['Year'] >= 2024]
        shift_df = shift_df[shift_df['Year'] >= 2024]
        
       