#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Building stock projections with appliance integration
'''

#%% Notes

# Non-residential buildings currently projected using population (any other proxy?)
# Urban-rural shift currently not reflected in materials (need to implement rule that in cities no SFH are constructed)
# Appliances are derived from households, which follow population growth in scenarios where floor area per capita decreases
# Building renovation: How to implement (MISO only takes stock projections)
# Stocks in office conversion and vacant space use lower than baseline because stock already exists (not repurposed)
# Vacant use scenario: new construction drops to almost zero because vacant building is used up AND population growth (driver of households) is near zero in this decade (see population projection)
# Shared Appliances scenario: 30% reduction in washing machines and dryers through shared laundry rooms by 2060
# Heatng systems cannot properly be modelled as operational heating demand relies on age cohort which is quantified in MISO2 using lifetimes (model analogously in STACEY?) -> endogenize in MISO2

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df.loc[:, 'Parameter':'Source']

######################################################################################################################################################
######################################################################################################################################################
#%% Scenarios

def load_scenario_parameters(file_path, scenario_name, base_region_shares=None):
    df_scenarios = pd.read_excel(file_path, sheet_name='buildings')
    df_scenarios = df_scenarios[~df_scenarios['Scenario Name'].str.startswith(('Parameter', 'Percenrage'), na=False) & df_scenarios['Scenario Name'].notna() & (df_scenarios['Scenario Name'] != '')]
    scenario = df_scenarios[df_scenarios['Scenario Name'] == scenario_name].iloc[0]
    
    reduction_factors = {}
    for btype in ['R_SFH', 'R_MFH', 'R_APB', 'R_IHH', 'NR_public', 'NR_indust', 'NR_trafcom', 'NR_retail', 'NR_office', 'NR_hotel']:
        val = scenario.get(btype, 1.0)
        reduction_factors[btype] = float(str(val).replace(',', '.').strip()) if isinstance(val, str) and val != '' else (val if pd.notna(val) else 1.0)
    
    urban_share = scenario.get('Urban Share', 'baseline')
    if isinstance(urban_share, str):
        urban_share = urban_share.replace(',', '.').strip().lower()
    
    apply_urban_shift = False
    urban_share_value = None
    if urban_share == 'baseline':
        region_shares = base_region_shares.copy() if base_region_shares else {}
    else:
        try:
            urban_share_value = float(urban_share)
            apply_urban_shift = True
            region_shares = {'Urban centre (large)': urban_share_value}
            if base_region_shares:
                non_urban_base = {k: v for k, v in base_region_shares.items() if k != 'Urban centre (large)'}
                non_urban_total = sum(non_urban_base.values())
                if non_urban_total > 0:
                    remaining = 1.0 - urban_share_value
                    for region, share in non_urban_base.items():
                        region_shares[region] = (share / non_urban_total) * remaining
        except:
            region_shares = base_region_shares.copy() if base_region_shares else {}
    
    apply_conversion = str(scenario.get('Apply Conversion', False)).lower() in ['true', '1', 'yes']
    
    # Handle conversion rate - if it's a dash or empty string, default to 0.0
    conv_rate_str = str(scenario.get('Conversion Rate', 0.0)).replace(',', '.').strip()
    if conv_rate_str == '-' or conv_rate_str == '':
        conv_rate = 0.0
    else:
        try:
            conv_rate = float(conv_rate_str)
        except ValueError:
            conv_rate = 0.0
    
    source_types = [s.strip() for s in str(scenario.get('Source Type', '-')).split(';') if s.strip() and s.strip() != '-']
    target_types = [t.strip() for t in str(scenario.get('Target Type', '-')).split(';') if t.strip() and t.strip() != '-']
    
    # Read Reduced Construction flag from Excel
    # If column doesn't exist, use scenario name as fallback
    if 'Reduced Construction' in df_scenarios.columns:
        reduced_construction = str(scenario.get('Reduced Construction', 'False')).lower() in ['true', '1', 'yes']
    else:
        # Fallback: detect by scenario name
        reduced_construction = 'Reduced' in scenario_name or 'reduced' in scenario_name.lower()
    
    # Read Appliance Sharing factor from Excel
    # Percentage of appliances shared (reduction in appliance count)
    if 'Appliances Sharing' in df_scenarios.columns:
        sharing_val = str(scenario.get('Appliances Sharing', 0.0)).replace(',', '.').strip()
        if sharing_val == '-' or sharing_val == '':
            appliance_sharing = 0.0
        else:
            try:
                appliance_sharing = float(sharing_val)
            except ValueError:
                appliance_sharing = 0.0
    else:
        appliance_sharing = 0.0
    
    # Read Start Year and End Year (apply to ALL policies)
    start_year = int(scenario.get('Start Year', 2024))
    end_year = int(scenario.get('End Year', 2060))
    
    return {
        'reduction_factors': reduction_factors,
        'urban_shift': {'apply': apply_urban_shift, 'region_shares': region_shares, 'urban_share': urban_share_value},
        'conversion': {
            'apply': apply_conversion,
            'source_types': source_types,
            'target_types': target_types,
            'conversion_rate': conv_rate,
            'start_year': start_year,
            'end_year': end_year,
            'linear': True
        },
        'reduced_construction': reduced_construction,
        'appliance_sharing': appliance_sharing,
        'start_year': start_year,
        'end_year': end_year,
        'metadata': {'Scenario Name': scenario.get('Scenario Name', 'Unknown'), 'Scenario Description': scenario.get('Description', '')}
    }

######################################################################################################################################################
######################################################################################################################################################
#%% Building projection

def get_reduction_factor(year, base_year, target_factor, start_year, end_year):
    """
    Calculate the reduction factor for a given year.
    Starts at 1.0 at start_year, gradually reaches target_factor by end_year.
    """
    if year <= start_year:
        return 1.0
    elif year >= end_year:
        return target_factor
    else:
        # Linear interpolation between 1.0 and target_factor
        progress = (year - start_year) / (end_year - start_year)
        return 1.0 - (1.0 - target_factor) * progress

def run_scenario(scenario_name, scenario_params, stocks_buildings_base, pop_by_year):
    base_year = stocks_buildings_base['Year'].min()
    base_data = stocks_buildings_base[stocks_buildings_base['Year'] == base_year].copy()
    total_stock_base = base_data['Value'].sum()
    pop_base = pop_by_year.get(base_year, pop_by_year.iloc[0])
    
    # Get population for the year before base year (for 2024 construction)
    pop_prev_year = pop_by_year.get(base_year - 1, pop_base)
    
    type_stock = base_data.groupby('Type_lv2')['Value'].sum()
    type_intensity = {b: s / pop_base for b, s in type_stock.items()}
    
    base_shares = base_data.groupby('Region_lv2')['Value'].sum()
    base_region_shares = (base_shares / base_shares.sum()).to_dict()
    
    # Store original reduction factors for gradual phase-in
    original_reduction_factors = scenario_params['reduction_factors'].copy()
    apply_future_region_shares = scenario_params['urban_shift']['apply']
    future_region_shares = scenario_params['urban_shift']['region_shares']
    conversion_params = scenario_params['conversion']
    
    # Get start/end years from scenario parameters
    start_year = scenario_params.get('start_year', 2024)
    end_year = scenario_params.get('end_year', 2040)
    
    conversion_mappings = []
    if conversion_params['apply']:
        source_types = conversion_params['source_types']
        target_types = conversion_params['target_types']
        is_vacant_use = 'Vacant' in scenario_name
        
        for source_type in source_types:
            # Get total stock of this type by region
            source_by_region = base_data[base_data['Type_lv2'] == source_type].groupby('Region_lv2')['Value'].sum().to_dict()
            source_total = sum(source_by_region.values())
            
            if is_vacant_use:
                # Vacant Space Use: only convert vacant stock (Occupancy == 'No residents')
                vacant_data = base_data[(base_data['Type_lv2'] == source_type) & (base_data['Occupancy'] == 'No residents')]
                vacant_by_region = vacant_data.groupby('Region_lv2')['Value'].sum().to_dict()
                vacant_total = sum(vacant_by_region.values())
                source_to_convert = vacant_total * conversion_params['conversion_rate']
                
                print(f"    {source_type}: {source_total:,.0f} m² total, {vacant_total:,.0f} m² vacant, "
                      f"converting {source_to_convert:,.0f} m² ({conversion_params['conversion_rate']*100:.0f}% of vacant)")
            else:
                # Office Conversion: convert from total stock (target type specified)
                source_to_convert = source_total * conversion_params['conversion_rate']
                vacant_by_region = {}
            
            conversion_mappings.append({
                'source_type': source_type,
                'target_types': target_types if not is_vacant_use else [source_type],  # Same type for vacant use
                'source_by_region': source_by_region,
                'source_total': source_total,
                'source_to_convert': source_to_convert,
                'vacant_by_region': vacant_by_region,
                'is_vacant_use': is_vacant_use
            })
    
    future_years = list(range(base_year + 1, 2101))
    cum_stock_by_type = type_stock.to_dict()  # Start with base stock
    all_rows = []
    annual_summary = []
    
    # Calculate construction for base year (2024) based on growth from 2023 to 2024
    pop_growth_base = max(0, pop_base - pop_prev_year)
    base_new_const = 0
    
    if pop_growth_base > 0:
        # Calculate new construction for base year (reduction factor = 1.0 in base year)
        for bldg_type, intensity in type_intensity.items():
            # Base year always uses factor 1.0 (no reduction yet)
            needed = pop_growth_base * intensity * 1.0
            if needed > 0.01:
                base_row = base_data[base_data['Type_lv2'] == bldg_type].iloc[0]
                for region, share in base_region_shares.items():
                    val = needed * share
                    if val > 0.01:
                        all_rows.append({
                            'Parameter': base_row['Parameter'], 'Region_lv1': base_row['Region_lv1'], 'Region_lv2': region,
                            'Type_lv1': base_row['Type_lv1'], 'Type_lv2': bldg_type,
                            'Ownership': base_row['Ownership'], 'Occupancy': base_row['Occupancy'],
                            'Density': base_row['Density'], 'Year_from': base_year, 'Year_to': base_year, 'Year': base_year,
                            'Unit': base_row['Unit'], 'Value': val
                        })
                        base_new_const += val
                        cum_stock_by_type[bldg_type] = cum_stock_by_type.get(bldg_type, 0) + val
    
    # Add base year to annual summary WITH construction
    total_stock_base_updated = sum(cum_stock_by_type.values())
    annual_summary.append({'Year': base_year, 'Population': pop_base, 'Cumulative_Stock': total_stock_base_updated, 'New_Additions': base_new_const, 'Converted_Stock': 0, 'Per_Capita': total_stock_base_updated / pop_base})
    
    cum_converted = {i: 0 for i in range(len(conversion_mappings))}
    
    for year in future_years:
        pop_cur = pop_by_year.get(year, pop_by_year.iloc[-1])
        pop_prev = pop_by_year.get(year - 1, pop_base)
        pop_growth = max(0, pop_cur - pop_prev)
        
        if apply_future_region_shares and future_region_shares:
            region_shares = future_region_shares
            total_share = sum(region_shares.values())
            if total_share > 0:
                region_shares = {k: v/total_share for k, v in region_shares.items()}
        else:
            region_shares = base_region_shares
        
        new_const = 0
        conv_this_year_total = 0
        conv_this_year = {}
        conv_reductions = {}
        
        if conversion_params['apply']:
            for i, m in enumerate(conversion_mappings):
                if conversion_params['start_year'] <= year <= conversion_params['end_year']:
                    if conversion_params['linear'] and conversion_params['end_year'] > conversion_params['start_year']:
                        progress = (year - conversion_params['start_year']) / (conversion_params['end_year'] - conversion_params['start_year'])
                    else:
                        progress = 1.0
                    total_converted = m['source_to_convert'] * progress
                    converted_now = total_converted - cum_converted[i]
                    cum_converted[i] = total_converted
                    converted_now = max(0, converted_now)
                else:
                    converted_now = 0
                conv_this_year[i] = converted_now
                conv_this_year_total += converted_now
                
                # For Vacant Space Use: reduce demand for the source type itself
                # For Office Conversion: reduce demand for the target type
                if m['is_vacant_use']:
                    conv_reductions[m['source_type']] = conv_reductions.get(m['source_type'], 0) + converted_now
                else:
                    for target_type in m['target_types']:
                        conv_reductions[target_type] = conv_reductions.get(target_type, 0) + converted_now
        
        for bldg_type, intensity in type_intensity.items():
            # Get the phase-in reduction factor for this year
            target_factor = original_reduction_factors.get(bldg_type, 1.0)
            reduction_factor = get_reduction_factor(year, base_year, target_factor, start_year, end_year)
            
            needed = pop_growth * intensity * reduction_factor
            if conversion_params['apply'] and bldg_type in conv_reductions:
                needed = max(0, needed - conv_reductions[bldg_type])
            if needed > 0.01:
                base_row = base_data[base_data['Type_lv2'] == bldg_type].iloc[0]
                for region, share in region_shares.items():
                    val = needed * share
                    if val > 0.01:
                        all_rows.append({
                            'Parameter': base_row['Parameter'], 'Region_lv1': base_row['Region_lv1'], 'Region_lv2': region,
                            'Type_lv1': base_row['Type_lv1'], 'Type_lv2': bldg_type,
                            'Ownership': base_row['Ownership'], 'Occupancy': base_row['Occupancy'],
                            'Density': base_row['Density'], 'Year_from': year, 'Year_to': year, 'Year': year,
                            'Unit': base_row['Unit'], 'Value': val
                        })
                        new_const += val
                        cum_stock_by_type[bldg_type] = cum_stock_by_type.get(bldg_type, 0) + val
        
        # Handle conversions
        if conversion_params['apply'] and conv_this_year_total > 0:
            for i, m in enumerate(conversion_mappings):
                converted_now = conv_this_year.get(i, 0)
                if converted_now <= 0: continue
                
                if m['is_vacant_use']:
                    # Vacant Space Use: change occupancy from 'No residents' to 'One or more usual residents'
                    # Same building type, only occupancy changes
                    for region, vacant_val in m['vacant_by_region'].items():
                        region_share = vacant_val / m['source_total'] if m['source_total'] > 0 else 0
                        val = converted_now * region_share
                        if val > 0.01:
                            base_row = base_data[base_data['Type_lv2'] == m['source_type']].iloc[0]
                            all_rows.append({
                                'Parameter': base_row['Parameter'], 'Region_lv1': base_row['Region_lv1'], 'Region_lv2': region,
                                'Type_lv1': base_row['Type_lv1'], 'Type_lv2': m['source_type'],
                                'Ownership': base_row['Ownership'], 
                                'Occupancy': 'One or more usual residents',  # Changed from vacant to occupied
                                'Density': base_row['Density'], 'Year_from': year, 'Year_to': year, 'Year': year,
                                'Unit': base_row['Unit'], 'Value': val, 'Converted': True, 'From_Vacant': True
                            })
                            # Add to cum_stock_by_type to maintain stock consistency with baseline
                            cum_stock_by_type[m['source_type']] = cum_stock_by_type.get(m['source_type'], 0) + val
                else:
                    # Office Conversion: convert from source to target type
                    for region, source_val in m['source_by_region'].items():
                        region_share = source_val / m['source_total'] if m['source_total'] > 0 else 0
                        val = converted_now * region_share
                        if val > 0.01:
                            # ADD to target type(s)
                            for target_type in m['target_types']:
                                base_row = base_data[base_data['Type_lv2'] == target_type].iloc[0]
                                all_rows.append({
                                    'Parameter': base_row['Parameter'], 'Region_lv1': base_row['Region_lv1'], 'Region_lv2': region,
                                    'Type_lv1': base_row['Type_lv1'], 'Type_lv2': target_type,
                                    'Ownership': base_row['Ownership'], 'Occupancy': base_row['Occupancy'],
                                    'Density': base_row['Density'], 'Year_from': year, 'Year_to': year, 'Year': year,
                                    'Unit': base_row['Unit'], 'Value': val, 'Converted': True
                                })
                                cum_stock_by_type[target_type] = cum_stock_by_type.get(target_type, 0) + val
                            
                            # SUBTRACT from source type
                            source_type = m['source_type']
                            # Make sure we don't go negative
                            current_source = cum_stock_by_type.get(source_type, 0)
                            if current_source >= val:
                                cum_stock_by_type[source_type] = current_source - val
                            else:
                                # If we would go negative, just set to zero
                                cum_stock_by_type[source_type] = 0
                                print(f"Warning: Not enough source stock ({source_type}) to convert {val:.0f} m² in {year}")
        
        cum_stock = sum(cum_stock_by_type.values())
        annual_summary.append({'Year': year, 'Population': pop_cur, 'Cumulative_Stock': cum_stock, 'New_Additions': new_const, 'Converted_Stock': conv_this_year_total, 'Per_Capita': cum_stock / pop_cur})
    
    stocks_buildings_proj = pd.DataFrame(all_rows)
    
    def get_cohort(year):
        if year == base_year: return str(base_year)
        if year <= 2030: return '2025 to 2030'
        if year <= 2035: return '2031 to 2035'
        if year <= 2040: return '2036 to 2040'
        if year <= 2050: return '2041 to 2050'
        if year <= 2060: return '2051 to 2060'
        if year <= 2070: return '2061 to 2070'
        if year <= 2080: return '2071 to 2080'
        if year <= 2090: return '2081 to 2090'
        if year <= 2100: return '2091 to 2100'
        return None
    
    base_data_with_cohort = base_data.copy()
    base_data_with_cohort['Cohort'] = str(base_year)
    
    if len(stocks_buildings_proj) > 0:
        stocks_buildings_proj['Cohort'] = stocks_buildings_proj['Year'].apply(get_cohort)
        stocks_buildings_proj = stocks_buildings_proj[stocks_buildings_proj['Cohort'].notna()]
        stocks_buildings_proj['Year_from'] = stocks_buildings_proj['Year_from'].astype(int)
        stocks_buildings_proj['Year_to'] = stocks_buildings_proj['Year_to'].astype(int)
        stocks_buildings_proj['Year'] = stocks_buildings_proj['Year'].astype(int)
    
    stocks_buildings_full = pd.concat([base_data_with_cohort, stocks_buildings_proj], ignore_index=True)
    column_order = ['Parameter', 'Region_lv1', 'Region_lv2', 'Type_lv1', 'Type_lv2', 'Ownership', 'Occupancy', 'Cohort', 'Density', 'Year_from', 'Year_to', 'Year', 'Unit', 'Value']
    for col in column_order:
        if col not in stocks_buildings_full.columns:
            stocks_buildings_full[col] = None
    stocks_buildings_full = stocks_buildings_full[column_order]
    
    os.makedirs(f'output/scenarios/{scenario_name}', exist_ok=True)
    stocks_buildings_proj.to_parquet(f'output/scenarios/{scenario_name}/stocks_buildings_proj.parquet', index=False)
    stocks_buildings_full.to_parquet(f'output/scenarios/{scenario_name}/stocks_buildings_full.parquet', index=False)
    
    return stocks_buildings_full, pd.DataFrame(annual_summary)

######################################################################################################################################################
######################################################################################################################################################
#%% Appliance projection

def project_appliances(scenario_name, scenario_params, annual_summary, appliance_base, household_base):
    """
    Project household appliances based on scenario type
    
    Households and appliances follow population growth in scenarios where floor area per capita decreases
    (Reduced Construction, Vacant Space Use, Office Conversion).
    In Baseline and Urban Shift, they follow floor area growth.
    
    Appliance sharing scenario reduces washing machines and dryers through shared laundry rooms.
    """
    
    base_year = annual_summary['Year'].min()
    
    # Base year metrics
    base_row = annual_summary[annual_summary['Year'] == base_year].iloc[0]
    base_population = base_row['Population']
    base_floor_area = base_row['Cumulative_Stock']
    base_households = household_base['Households'].sum()
    base_appliances = appliance_base.groupby('Type_lv2')['Value'].sum()
    
    # Appliance penetration rates per household
    appliances_per_household = {app: count / base_households for app, count in base_appliances.items()}
    
    # Determine household driver based on scenario type
    # Use population driver for scenarios where building stock changes independently of population
    is_reduced = scenario_params.get('reduced_construction', False)
    is_vacant = 'Vacant' in scenario_name
    is_office_conversion = 'Office Conversion' in scenario_name
    
    # Office Conversion should follow population (number of households doesn't change)
    # Reduced Construction and Vacant Space Use also follow population
    use_population_driver = is_reduced or is_vacant or is_office_conversion
    
    # Get appliance sharing factor and phase-in years
    appliance_sharing_target = scenario_params.get('appliance_sharing', 0.0)
    start_year = scenario_params.get('start_year', 2024)
    end_year = scenario_params.get('end_year', 2060)
    is_shared = 'Shared' in scenario_name and appliance_sharing_target > 0
    
    projected_rows = []
    
    for _, row in annual_summary.iterrows():
        year = row['Year']
        
        if year == base_year:
            continue
        
        # Calculate households based on scenario type
        if use_population_driver:
            # Population-based scenarios: households follow population
            households = base_households * (row['Population'] / base_population)
        else:
            # Floor area-based scenarios: households follow floor area
            households = base_households * (row['Cumulative_Stock'] / base_floor_area)
        
        # Calculate appliances from households
        for appliance, ratio in appliances_per_household.items():
            num_appliances = households * ratio
            
            # Apply sharing reduction for washing machines and dryers
            if is_shared and appliance in ['Washing_machine', 'Tumble_dryer']:
                # Get sharing factor for this year (phase-in from Excel)
                if year <= start_year:
                    sharing_factor = 0.0
                elif year >= end_year:
                    sharing_factor = appliance_sharing_target
                else:
                    # Linear interpolation between 0 and target
                    progress = (year - start_year) / (end_year - start_year)
                    sharing_factor = appliance_sharing_target * progress
                
                num_appliances = num_appliances * (1 - sharing_factor)
            
            projected_rows.append({
                'Type_lv2': appliance,
                'Year': year,
                'Value': num_appliances,
                'Scenario': scenario_name
            })
    
    return pd.DataFrame(projected_rows)

######################################################################################################################################################
######################################################################################################################################################
#%% Projection execution

# Add Shared Appliances to the list of scenarios
scenarios_to_run = ['Baseline', 'Office Conversion', 'Urban Shift', 'Reduced Construction', 'Vacant Space Use', 'Shared Appliances']

data_POP = read_excel(os.path.join(main_path, 'input/data_POP.xlsx'), sheet_name='input')
stocks_buildings_base = pd.read_parquet('output/interim/stocks_buildings_base.parquet')
appliance_base = pd.read_parquet('output/interim/stocks_appliances_base.parquet')
household_base = pd.read_parquet('output/interim/stocks_households_base.parquet')

data_POP = data_POP[data_POP['Year_to'].between(2000, 2100)].copy()
y, v = data_POP['Year_to'].values, data_POP['Value'].values
m = (y >= 2022) & (y <= 2030)
data_POP['Value_smooth'] = v.astype(float).copy()
data_POP.loc[m, 'Value_smooth'] = PchipInterpolator(y[~m], v[~m])(y[m])
pop_by_year = data_POP[data_POP['Year_to'] <= 2100].set_index('Year_to')['Value_smooth']

scenario_params_path = os.path.join(main_path, 'input', 'scenario_parameters.xlsx')
base_year = stocks_buildings_base['Year'].min()
base_data = stocks_buildings_base[stocks_buildings_base['Year'] == base_year].copy()
base_region_shares = (base_data.groupby('Region_lv2')['Value'].sum() / base_data.groupby('Region_lv2')['Value'].sum().sum()).to_dict()

print("\n" + "="*80)
print("RUNNING SCENARIOS")
print("="*80)

# Run building scenarios
all_results = {}
for scenario_name in scenarios_to_run:
    print(f"\nRunning {scenario_name}...")
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name, base_region_shares)
    stocks_buildings_full, annual_df = run_scenario(scenario_name, scenario_params, stocks_buildings_base, pop_by_year)
    all_results[scenario_name] = annual_df
    print(f"  ✓ Generated {len(annual_df)} years of building data")

# Project appliances for all scenarios
all_appliances = {}
for scenario_name in scenarios_to_run:
    print(f"\nProjecting appliances for {scenario_name}...")
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name, base_region_shares)
    appliance_proj = project_appliances(scenario_name, scenario_params, all_results[scenario_name], appliance_base, household_base)
    all_appliances[scenario_name] = appliance_proj
    appliance_proj.to_parquet(f'output/scenarios/{scenario_name}/appliances_projected.parquet', index=False)
    print(f"  ✓ Generated {len(appliance_proj):,} appliance records")

######################################################################################################################################################
######################################################################################################################################################
#%% Results
#%%% Floor area

print("\n" + "="*80)
print("GENERATING PLOTS")
print("="*80)

fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# Subplot 1: Cumulative Stock
ax = axes[0]
for name, df in all_results.items():
    ax.plot(df['Year'], df['Cumulative_Stock'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Cumulative Stock (million m²)')
ax.set_title('Stock Growth Comparison')
ax.legend()
ax.grid(True, alpha=0.3)

# Subplot 2: Annual New Construction
ax = axes[1]
for name, df in all_results.items():
    ax.plot(df['Year'], df['New_Additions'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('New Additions (million m²/year)')
ax.set_title('Annual New Construction')
ax.legend()
ax.grid(True, alpha=0.3)

# Subplot 3: Cumulative New Construction
ax = axes[2]
for name, df in all_results.items():
    cumulative = df['New_Additions'].cumsum() / 1e6
    ax.plot(df['Year'], cumulative, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Cumulative New Construction (million m²)')
ax.set_title('Cumulative New Construction')
ax.legend()
ax.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs('output/scenarios', exist_ok=True)
plt.savefig('output/scenarios/building_comparison.png', dpi=150, bbox_inches='tight')
plt.show()

#%%% Appliances

fig, axes = plt.subplots(2, 3, figsize=(15, 10))
appliance_types = ['Fridge', 'Freezer', 'Washing_machine', 'Dishwasher', 'Tumble_dryer', 'TV']

for i, appliance in enumerate(appliance_types):
    ax = axes[i // 3, i % 3]
    
    for name, df in all_appliances.items():
        appliance_data = df[df['Type_lv2'] == appliance]
        if not appliance_data.empty:
            yearly = appliance_data.groupby('Year')['Value'].sum() / 1e6
            ax.plot(yearly.index, yearly.values, label=name, linewidth=2)
    
    ax.set_xlabel('Year')
    ax.set_ylabel('Units (millions)')
    ax.set_title(f'{appliance}')
    ax.legend()
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('output/scenarios/appliance_comparison.png', dpi=150, bbox_inches='tight')
plt.show()

#%%% Overall summary

for scenario_name, df in all_results.items():
    last_year = df['Year'].max()
    last_row = df[df['Year'] == last_year].iloc[0]
    print(f"\n{scenario_name}:")
    print(f"  Final stock ({last_year}): {last_row['Cumulative_Stock']/1e6:.1f} million m²")
    print(f"  Per capita: {last_row['Per_Capita']:.1f} m²/person")
    
    if scenario_name in all_appliances:
        appliance_df = all_appliances[scenario_name]
        last_appliances = appliance_df[appliance_df['Year'] == last_year]
        if not last_appliances.empty:
            total_appliances = last_appliances['Value'].sum()
            print(f"  Total appliances: {total_appliances/1e6:.2f} million units")