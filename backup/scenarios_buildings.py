#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Building stock projections
'''

#%% Notes

# Non-residential buildings currently projected using population (any other proxy?)
# Urban-rural shift currently not reflected in materials (need to implement rule that in cities no SFH are constructed)

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
#%% Scenario loading

def load_scenario_parameters(file_path, scenario_name, base_region_shares=None):
    df_scenarios = pd.read_excel(file_path, sheet_name='Scenarios')
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
    conv_rate = float(str(scenario.get('Conversion Rate', 0.0)).replace(',', '.').strip() or 0.0)
    
    source_types = [s.strip() for s in str(scenario.get('Source Type', '-')).split(';') if s.strip() and s.strip() != '-']
    target_types = [t.strip() for t in str(scenario.get('Target Type', 'R_APB')).split(';') if t.strip() and t.strip() != '-']
    if not target_types: target_types = ['R_APB']
    
    return {
        'reduction_factors': reduction_factors,
        'urban_shift': {'apply': apply_urban_shift, 'region_shares': region_shares, 'urban_share': urban_share_value},
        'conversion': {
            'apply': apply_conversion,
            'source_types': source_types,
            'target_types': target_types,
            'conversion_rate': conv_rate,
            'start_year': int(scenario.get('Start Year', 2024)),
            'end_year': int(scenario.get('End Year', 2060)),
            'linear': True
        },
        'metadata': {'Scenario Name': scenario.get('Scenario Name', 'Unknown'), 'Scenario Description': scenario.get('Description', '')}
    }

######################################################################################################################################################
######################################################################################################################################################
#%% Projection function

def run_scenario(scenario_name, scenario_params, stocks_buildings_base, pop_by_year):
    base_year = stocks_buildings_base['Year'].min()
    base_data = stocks_buildings_base[stocks_buildings_base['Year'] == base_year].copy()
    total_stock_base = base_data['Value'].sum()
    pop_base = pop_by_year.get(base_year, pop_by_year.iloc[0])
    
    type_stock = base_data.groupby('Type_lv2')['Value'].sum()
    type_intensity = {b: s / pop_base for b, s in type_stock.items()}
    
    base_shares = base_data.groupby('Region_lv2')['Value'].sum()
    base_region_shares = (base_shares / base_shares.sum()).to_dict()
    
    new_stocks_reduction = scenario_params['reduction_factors']
    apply_future_region_shares = scenario_params['urban_shift']['apply']
    future_region_shares = scenario_params['urban_shift']['region_shares']
    conversion_params = scenario_params['conversion']
    
    conversion_mappings = []
    if conversion_params['apply']:
        source_types = conversion_params['source_types']
        target_types = conversion_params['target_types']
        target_type = target_types[0]
        for source_type in source_types:
            source_by_region = base_data[base_data['Type_lv2'] == source_type].groupby('Region_lv2')['Value'].sum().to_dict()
            source_total = sum(source_by_region.values())
            conversion_mappings.append({
                'source_type': source_type,
                'target_type': target_type,
                'source_by_region': source_by_region,
                'source_total': source_total,
                'source_to_convert': source_total * conversion_params['conversion_rate']
            })
    
    future_years = list(range(base_year + 1, 2101))
    cum_stock_by_type = type_stock.to_dict()
    all_rows = []
    annual_summary = []
    
    annual_summary.append({'Year': base_year, 'Population': pop_base, 'Cumulative_Stock': total_stock_base, 'New_Additions': 0, 'Converted_Stock': 0, 'Per_Capita': total_stock_base / pop_base})
    
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
                conv_reductions[m['target_type']] = conv_reductions.get(m['target_type'], 0) + converted_now
        
        for bldg_type, intensity in type_intensity.items():
            needed = pop_growth * intensity * new_stocks_reduction.get(bldg_type, 1.0)
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
        
        if conversion_params['apply'] and conv_this_year_total > 0:
            for i, m in enumerate(conversion_mappings):
                converted_now = conv_this_year.get(i, 0)
                if converted_now <= 0: continue
                for region, source_val in m['source_by_region'].items():
                    region_share = source_val / m['source_total'] if m['source_total'] > 0 else 0
                    val = converted_now * region_share
                    if val > 0.01:
                        base_row = base_data[base_data['Type_lv2'] == m['target_type']].iloc[0]
                        all_rows.append({
                            'Parameter': base_row['Parameter'], 'Region_lv1': base_row['Region_lv1'], 'Region_lv2': region,
                            'Type_lv1': base_row['Type_lv1'], 'Type_lv2': m['target_type'],
                            'Ownership': base_row['Ownership'], 'Occupancy': base_row['Occupancy'],
                            'Density': base_row['Density'], 'Year_from': year, 'Year_to': year, 'Year': year,
                            'Unit': base_row['Unit'], 'Value': val, 'Converted': True
                        })
                        cum_stock_by_type[m['target_type']] = cum_stock_by_type.get(m['target_type'], 0) + val
        
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
#%% Execution

scenarios_to_run = ['Baseline', 'Office Conversion', 'Urban Shift', 'Reduced Construction']

data_POP = read_excel(os.path.join(main_path, 'input/data_POP.xlsx'), sheet_name='MISO2_POP')
stocks_buildings_base = pd.read_parquet('output/interim/stocks_buildings_base.parquet')

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

all_results = {}
for scenario_name in scenarios_to_run:
    scenario_params = load_scenario_parameters(scenario_params_path, scenario_name, base_region_shares)
    stocks_buildings_full, annual_df = run_scenario(scenario_name, scenario_params, stocks_buildings_base, pop_by_year)
    all_results[scenario_name] = annual_df

#%% Plot results

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
for name, df in all_results.items():
    ax.plot(df['Year'], df['Cumulative_Stock'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('Cumulative Stock (million m²)')
ax.set_title('Stock Growth Comparison')
ax.legend()
ax.grid(True, alpha=0.3)

ax = axes[1]
for name, df in all_results.items():
    ax.plot(df['Year'], df['New_Additions'] / 1e6, label=name, linewidth=2)
ax.set_xlabel('Year')
ax.set_ylabel('New Additions (million m²)')
ax.set_title('Annual New Construction Comparison')
ax.legend()
ax.grid(True, alpha=0.3)

plt.tight_layout()
os.makedirs('output/scenarios', exist_ok=True)
plt.savefig('output/scenarios/scenario_comparison.png', dpi=150, bbox_inches='tight')
plt.show()