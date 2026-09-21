#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Mobility infrastructure projections
'''

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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
    Load scenario parameters from 'infrastructure' sheet
    """
    try:
        df_scenarios = pd.read_excel(file_path, sheet_name='infrastructure')
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
#%% Infrastructure projection

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

def get_mobility_growth_rates(pkm_data, gdp_by_year, pop_by_year):
    """
    Calculate growth rates for each mobility type based on GDP and population projections.
    Returns a dictionary with mobility type as key and growth factor per year.
    """
    # Get unique mobility types
    mobility_types = pkm_data['Type_lv2'].unique()
    
    growth_rates = {}
    
    for mob_type in mobility_types:
        # Get historical data for this mobility type
        type_data = pkm_data[pkm_data['Type_lv2'] == mob_type].copy()
        
        if type_data.empty:
            continue
        
        # Aggregate by year if needed
        if len(type_data) > type_data['Year'].nunique():
            type_data = type_data.groupby('Year').agg({'Value': 'sum'}).reset_index()
        
        hist_years = type_data['Year'].values
        hist_values = type_data['Value'].values
        
        # Remove invalid data
        valid = ~np.isnan(hist_values) & (hist_values > 0)
        hist_years = hist_years[valid]
        hist_values = hist_values[valid]
        
        if len(hist_years) < 3:
            # Use default growth based on GDP and population
            base_year = 2024
            if base_year in gdp_by_year.index and base_year in pop_by_year.index:
                base_gdp = gdp_by_year[base_year]
                base_pop = pop_by_year[base_year]
                
                future_years = [y for y in range(base_year + 1, 2101) 
                               if y in gdp_by_year.index and y in pop_by_year.index]
                
                growth_factors = {}
                for year in future_years:
                    gdp_ratio = gdp_by_year[year] / base_gdp
                    pop_ratio = pop_by_year[year] / base_pop
                    growth_factors[year] = pop_ratio * gdp_ratio
                
                growth_rates[mob_type] = growth_factors
                continue
            else:
                continue
        
        # Calculate growth rates from historical data
        base_year = hist_years[-1]
        base_value = hist_values[-1]
        
        # Get base GDP and population
        if base_year in gdp_by_year.index:
            base_gdp = gdp_by_year[base_year]
        else:
            closest = min(gdp_by_year.index, key=lambda x: abs(x - base_year))
            base_gdp = gdp_by_year[closest]
        
        if base_year in pop_by_year.index:
            base_pop = pop_by_year[base_year]
        else:
            closest = min(pop_by_year.index, key=lambda x: abs(x - base_year))
            base_pop = pop_by_year[closest]
        
        # Calculate elasticity from historical data
        try:
            # Prepare data for regression
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
            
            pkm_per_capita = np.array(hist_values) / np.array(hist_pop)
            gdp_values = np.array(hist_gdp)
            
            # Filter for log transform
            valid_log = (pkm_per_capita > 0) & (gdp_values > 0)
            if sum(valid_log) >= 3:
                log_gdp = np.log(gdp_values[valid_log])
                log_pkm = np.log(pkm_per_capita[valid_log])
                
                slope, _, r_value, _, _ = linregress(log_gdp, log_pkm)
                elasticity = slope if abs(slope) < 2 else 0.5
            else:
                elasticity = 0.5
        except:
            elasticity = 0.5
        
        # Project future growth factors starting from 2025
        start_year = 2025
        future_years = [y for y in range(start_year, 2101) 
                       if y in gdp_by_year.index and y in pop_by_year.index]
        
        growth_factors = {}
        for year in future_years:
            gdp_ratio = gdp_by_year[year] / base_gdp
            pop_ratio = pop_by_year[year] / base_pop
            growth_factors[year] = pop_ratio * (gdp_ratio ** elasticity)
        
        growth_rates[mob_type] = growth_factors
    
    return growth_rates

def apply_monotonic_constraint(projections_df):
    """
    Apply monotonic constraint to ensure infrastructure never decreases.
    For each infrastructure type, ensure values are non-decreasing over time.
    """
    if projections_df.empty:
        return projections_df
    
    # Get unique infrastructure types
    infra_types = projections_df['Type_lv2'].unique()
    
    constrained_dfs = []
    
    for infra_type in infra_types:
        # Get data for this type
        type_data = projections_df[projections_df['Type_lv2'] == infra_type].copy()
        type_data = type_data.sort_values('Year')
        
        # Apply monotonic constraint: ensure non-decreasing values
        cumulative_max = type_data['Value'].cummax()
        type_data['Value_constrained'] = cumulative_max
        
        # Replace original values with constrained values
        type_data['Value'] = type_data['Value_constrained']
        type_data = type_data.drop('Value_constrained', axis=1)
        
        constrained_dfs.append(type_data)
    
    result_df = pd.concat(constrained_dfs, ignore_index=True)
    
    return result_df

def project_infrastructure_from_mobility(infra_data, mobility_growth_rates, scenario_params, infra_to_mobility_map, pkm_data):
    """
    Project infrastructure based on mobility growth rates starting from 2025.
    Supports multiple mobility types per infrastructure category.
    """
    # Get unique infrastructure types
    infra_types = infra_data['Type_lv2'].unique()
    
    # Base year data (2024)
    base_year = 2024
    infra_base = infra_data[infra_data['Year'] == base_year].copy()
    
    if infra_base.empty:
        return pd.DataFrame()
    
    # Project each infrastructure type
    all_projections = []
    
    for infra_type in infra_types:
        # Get base value for this infrastructure type
        type_base = infra_base[infra_base['Type_lv2'] == infra_type]
        if type_base.empty:
            continue
        
        base_value = type_base['Value'].iloc[0]
        
        # Find corresponding mobility type(s)
        mobility_types = infra_to_mobility_map.get(infra_type, None)
        
        if mobility_types is None:
            continue
        
        # Convert to list if single string
        if isinstance(mobility_types, str):
            mobility_types = [mobility_types]
        
        # Check if all mobility types exist in growth rates
        valid_mobility_types = [mt for mt in mobility_types if mt in mobility_growth_rates]
        
        if not valid_mobility_types:
            continue
        
        # Get growth factors for each mobility type
        growth_factors_list = []
        for mob_type in valid_mobility_types:
            growth_factors_list.append(mobility_growth_rates[mob_type])
        
        # Combine growth factors (weighted average by base year values)
        weights = []
        for mob_type in valid_mobility_types:
            mob_base_value = pkm_data[(pkm_data['Type_lv2'] == mob_type) & 
                                      (pkm_data['Year'] == base_year)]['Value'].sum()
            weights.append(mob_base_value)
        
        total_weight = sum(weights)
        if total_weight == 0:
            weights = [1.0 / len(valid_mobility_types)] * len(valid_mobility_types)
        else:
            weights = [w / total_weight for w in weights]
        
        # Get common years
        common_years = set(growth_factors_list[0].keys())
        for gf in growth_factors_list[1:]:
            common_years = common_years.intersection(gf.keys())
        
        if not common_years:
            continue
        
        # Calculate weighted average growth factor for each year
        growth_factors = {}
        for year in sorted(common_years):
            weighted_growth = 0
            for i, gf in enumerate(growth_factors_list):
                weighted_growth += gf[year] * weights[i]
            growth_factors[year] = weighted_growth
        
        # Apply growth factors to infrastructure
        for year, growth_factor in growth_factors.items():
            reduction_factor = get_phase_in_factor(
                year,
                scenario_params['start_year'],
                scenario_params['end_year'],
                scenario_params['demand_reduction']
            )
            
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
    
    # Apply monotonic constraint to prevent decreases
    result_df = apply_monotonic_constraint(result_df)
    
    return result_df

def run_scenario(scenario_name, scenario_params, infra_data, pkm_data, gdp_data, pop_data):
    """
    Run infrastructure scenario projection for a single scenario.
    """
    # Prepare time series
    gdp_by_year = gdp_data.set_index('Year_from')['Value']
    pop_by_year = pop_data[pop_data['Year_to'] <= 2100].set_index('Year_to')['Value']
    
    # Create infrastructure to mobility mapping with multiple types
    infra_to_mobility = {
        
        # Road infrastructure - driven by Cars AND Motorcycles
        'motorway':                     ['Cars', 'Buses'],
        'motorway_bridge':              ['Cars', 'Buses'],
        'motorway_tunnel':              ['Cars', 'Buses'],
        'primary':                      ['Cars', 'Buses'],
        'primary_bridge':               ['Cars', 'Buses'],
        'primary_tunnel':               ['Cars', 'Buses'],
        'secondary_bridge':             ['Cars', 'Buses'],
        'secondary_tunnel':             ['Cars', 'Buses'],
        'tertiary_bridge':              ['Cars', 'Buses'],
        'tertiary_tunnel':              ['Cars', 'Buses'],
        'local':                        ['Cars', 'Buses'],
        'local_bridge':                 ['Cars', 'Buses'],
        'local_tunnel':                 ['Cars', 'Buses'],
        'secondary':                    ['Cars', 'Buses'],
        'tertiary':                     ['Cars', 'Buses'],
        'track':                        ['Cars', 'Buses'],
        'track_bridge':                 ['Cars', 'Buses'],
        'track_tunnel':                 ['Cars', 'Buses'],
        
        # Parking and fuelling/charging infrastructure
        'parking_surface':              ['Car', 'Buses'],
        'parking_underground':          ['Car', 'Buses'],
        'parking_building':             ['Car', 'Buses'],
        'gas_station_building':         ['Car', 'Buses'],
        'charging_station':             ['Car', 'Buses'],
        
        # Rail infrastructure
        'railway':                      ['Railway', 'Rail'],
        'railway_bridge':               ['Railway', 'Rail'],
        'railway_tunnel':               ['Railway', 'Rail'],
        'railway_building':             ['Railway', 'Rail'],
        'railway_building_platform':    ['Railway', 'Rail'],
        'rail_other':                   ['Railway', 'Rail'],
        
        # Subway/Tram
        'subway':                       ['Subway/tram'],
        'subway_bridge':                ['Subway/tram'],
        'subway_tunnel':                ['Subway/tram'],
        'subway_building':              ['Subway/tram'],
        'tram':                         ['Subway/tram'],
    }
    
    # Calculate mobility growth rates
    mobility_growth_rates = get_mobility_growth_rates(pkm_data, gdp_by_year, pop_by_year)
    
    # Calculate base year total (2024)
    base_year = 2024
    infra_base = infra_data[infra_data['Year'] == base_year].copy()
    base_total = infra_base['Value'].sum()
    
    # Project infrastructure
    infra_projections = project_infrastructure_from_mobility(
        infra_data, mobility_growth_rates, scenario_params, infra_to_mobility, pkm_data
    )
    
    if infra_projections.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    
    # Create summary (annual totals)
    summary = infra_projections.groupby('Year').agg({'Value': 'sum'}).reset_index()
    
    # Calculate per-capita
    pop_for_years = pop_by_year.reindex(summary['Year'])
    summary['Infra_per_capita'] = summary['Value'] / pop_for_years
    summary['Infra_per_capita'] = summary['Infra_per_capita'].replace([np.inf, -np.inf], np.nan)
    
    # Save results
    os.makedirs('output/Infrastructure', exist_ok=True)
    infra_projections.to_parquet(f'output/Infrastructure/infrastructure_projected_{scenario_name}.parquet', index=False)
    summary.to_csv(f'output/Infrastructure/infrastructure_summary_{scenario_name}.csv', index=False)
    
    return infra_projections, summary, {'projections': infra_projections, 'growth_rates': mobility_growth_rates}

######################################################################################################################################################
######################################################################################################################################################
#%% Projection execution

print("\n" + "="*80)
print("RUNNING INFRASTRUCTURE SCENARIOS")
print("="*80)

# Define scenarios to run
scenarios_to_run = ['Baseline', 'Mobility Reduction']

# Load data
print("\nLoading data...")

# Load infrastructure data from the data processing output
infra_path = os.path.join(main_path, 'output', 'interim', 'stocks_infra_base.parquet')

if not os.path.exists(infra_path):
    print(f"  ✗ Infrastructure data not found at {infra_path}")
    print("  Please run data processing script first to generate stocks_infra_base.parquet")
    exit(1)

data_infrastructure = pd.read_parquet(infra_path)

data_PKM = read_excel(os.path.join(main_path, 'input', 'data_pkm_tkm.xlsx'), sheet_name='input')
data_GDP = read_excel(os.path.join(main_path, 'input', 'data_GDP.xlsx'), sheet_name='input')
data_POP = read_excel(os.path.join(main_path, 'input', 'data_POP.xlsx'), sheet_name='input')

# Process data
data_infrastructure['Value'] = data_infrastructure['Value'].astype(float)
data_PKM['Value'] = data_PKM['Value'].astype(float)
data_GDP['Value'] = data_GDP['Value'].astype(float)
data_POP['Value'] = data_POP['Value'].astype(float)

# Load scenario parameters
scenario_params_path = os.path.join(main_path, 'input', 'scenario_parameters.xlsx')

# Run all scenarios
all_results = {}
all_summaries = {}
all_proj = {}

for scenario_name in scenarios_to_run:
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name)
    
    infra_df, summary, proj_dict = run_scenario(
        scenario_name, scenario_params, data_infrastructure, data_PKM, data_GDP, data_POP
    )
    all_results[scenario_name] = infra_df
    all_summaries[scenario_name] = summary
    all_proj[scenario_name] = proj_dict

######################################################################################################################################################
######################################################################################################################################################
#%% Results

# Create Figures folder
figures_path = os.path.join('output', 'Infrastructure', 'Figures')
os.makedirs(figures_path, exist_ok=True)

#%%% Infrastructure comparison

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

ax = axes[0]
has_data = False
for name, df in all_summaries.items():
    if df is not None and not df.empty:
        ax.plot(df['Year'], df['Value'] / 1e6, label=name, linewidth=2)
        has_data = True

if not has_data:
    ax.text(0.5, 0.5, 'No data available', 
            horizontalalignment='center', verticalalignment='center',
            transform=ax.transAxes, fontsize=14)
else:
    ax.set_xlabel('Year')
    ax.set_ylabel('Total infrastructure area (million m²)')
    ax.set_title('Infrastructure area per scenario')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axvline(x=2024, color='gray', linestyle='--', alpha=0.5, label='Base year (2024)')
    ax.legend()

ax = axes[1]
has_data = False
for name, df in all_summaries.items():
    if df is not None and not df.empty:
        if 2024 in df['Year'].values:
            base_value = df[df['Year'] == 2024]['Value'].iloc[0]
        else:
            base_value = df['Value'].iloc[0]
        
        if base_value > 0:
            ax.plot(df['Year'], df['Value'] / base_value, label=name, linewidth=2)
            has_data = True

if not has_data:
    ax.text(0.5, 0.5, 'No data available', 
            horizontalalignment='center', verticalalignment='center',
            transform=ax.transAxes, fontsize=14)
else:
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

#%%% Infrastructure by mobility group
print("\nCreating mobility group plot...")

if not all_results['Baseline'].empty:
    baseline_df = all_results['Baseline']
    
    infra_to_mobility_group = {
        'motorway':                     'Road',
        'motorway_bridge':              'Road',
        'motorway_tunnel':              'Road',
        'primary':                      'Road',
        'primary_bridge':               'Road',
        'primary_tunnel':               'Road',
        'secondary_bridge':             'Road',
        'secondary_tunnel':             'Road',
        'tertiary_bridge':              'Road',
        'tertiary_tunnel':              'Road',
        'local':                        'Road',
        'local_bridge':                 'Road',
        'local_tunnel':                 'Road',
        'secondary':                    'Road',
        'tertiary':                     'Road',
        'track':                        'Road',
        'track_bridge':                 'Road',
        'track_tunnel':                 'Road',
        'parking_surface':              'Road',
        'parking_underground':          'Road',
        'parking_building':             'Road',
        'gas_station_building':         'Road',
        'charging_station':             'Road',
        'railway':                      'Railway',
        'railway_bridge':               'Railway',
        'railway_tunnel':               'Railway',
        'railway_building':             'Railway',
        'railway_building_platform':    'Railway',
        'rail_other':                   'Railway',
        'subway':                       'Subway/tram',
        'subway_bridge':                'Subway/tram',
        'subway_tunnel':                'Subway/tram',
        'subway_building':              'Subway/tram',
        'tram':                         'Subway/tram'
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
    plt.savefig(os.path.join(figures_path, 'infrastructure_by_mobility_group.png'), dpi=150, bbox_inches='tight')
    plt.show()
    
    if not mobility_summary.empty:
        final_year = mobility_summary['Year'].max()
        final_data = mobility_summary[mobility_summary['Year'] == final_year]
        total = final_data['Value'].sum()
        print(f"\nFinal year ({final_year:.0f}) infrastructure by mobility group:")
        for _, row in final_data.iterrows():
            if pd.notna(row['Mobility_Group']):
                print(f"  {row['Mobility_Group']}: {row['Value']/1e6:.2f}M m² ({row['Value']/total*100:.1f}%)")
        
        # Also print growth rates
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
        if 2024 in df['Year'].values:
            base_row = df[df['Year'] == 2024].iloc[0]
            base_value = base_row['Value']
        else:
            base_row = df.iloc[0]
            base_value = base_row['Value']
        
        last_row = df.iloc[-1]
        first_row = df.iloc[0]
        
        growth = ((last_row['Value'] / base_value) - 1) * 100 if base_value > 0 else 0
        
        print(f"\n{scenario_name}:")
        print(f"  Base year (2024): {base_value/1e6:.2f}M m²")
        print(f"  First projection ({first_row['Year']:.0f}): {first_row['Value']/1e6:.2f}M m²")
        print(f"  Final year ({last_row['Year']:.0f}): {last_row['Value']/1e6:.2f}M m²")
        print(f"  Growth (2024 to {last_row['Year']:.0f}): {growth:.1f}%")
        
        if 'Infra_per_capita' in last_row and pd.notna(last_row['Infra_per_capita']):
            print(f"  Per capita ({last_row['Year']:.0f}): {last_row['Infra_per_capita']:.1f} m²/person")
    else:
        print(f"\n{scenario_name}: No data available")

# Calculate reduction percentages
if 'Baseline' in all_summaries and 'Mobility Reduction' in all_summaries:
    base_df = all_summaries['Baseline']
    red_df = all_summaries['Mobility Reduction']
    
    if base_df is not None and not base_df.empty and red_df is not None and not red_df.empty:
        merged = pd.merge(
            base_df[['Year', 'Value']].rename(columns={'Value': 'Baseline'}),
            red_df[['Year', 'Value']].rename(columns={'Value': 'Reduced'}),
            on='Year',
            how='inner'
        )
        
        if not merged.empty:
            merged['Reduction'] = (1 - merged['Reduced'] / merged['Baseline']) * 100
            
            if 2060 in merged['Year'].values:
                year_2060_row = merged[merged['Year'] == 2060].iloc[0]
                print(f"\n{'-'*50}")
                print(f"Mobility Reduction vs Baseline:")
                print(f"  Reduction by 2060: {year_2060_row['Reduction']:.1f}%")
                print(f"  Baseline (2060): {year_2060_row['Baseline']/1e6:.2f}M m²")
                print(f"  Reduced (2060): {year_2060_row['Reduced']/1e6:.2f}M m²")
            
            final_year = merged['Year'].max()
            final_row = merged[merged['Year'] == final_year].iloc[0]
            
            print(f"\n  Final year ({final_year:.0f}) reduction: {final_row['Reduction']:.1f}%")
            print(f"  Baseline ({final_year:.0f}): {final_row['Baseline']/1e6:.2f}M m²")
            print(f"  Reduced ({final_year:.0f}): {final_row['Reduced']/1e6:.2f}M m²")

print("\n" + "="*80)
print("INFRASTRUCTURE PROJECTION COMPLETE")
print("="*80)