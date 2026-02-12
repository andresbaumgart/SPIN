# !/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Scenario design and material stock modelling
'''

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import numpy as np
import pandas as pd
import math
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    cols = df.loc[:, 'Parameter':'Value'].columns.tolist()
    return df[cols]

color_map = {
    'sand':        '#1D1D1D',
    'concrete':    '#2F2F2F',
    'bricks':      '#454545',
    'glass_flat':  '#696969',
    'gypsum':      '#888888',
    'graphite':    '#3A6C73',
    'silica':      '#2E8591',
    'tungsten':    '#1DB0C5',
    'iron_steel':  '#8C0000',
    'copper':      '#DB1212',
    'aluminum':    '#F15C5C',
    'metal_other': '#F8A9A9',
    'plastic':     '#FDC828',
    'glass_wool':  '#7428FD',
    'stone_wool':  '#8562C3',
    'eps':         '#9280B2',
    'timber':      '#5A8D55'}

#%%% Data import
#%%%% Data import|General

data_POP = read_excel(os.path.join(main_path, 'input/data_POP.xlsx'), sheet_name='MISO2_POP')

#%%%% Data import|Building sector

stocks_buildings_base = pd.read_parquet("output/interim/stocks_buildings_base.parquet")
data_MI_buildings = read_excel(os.path.join(main_path, 'input/data_MI_buildings.xlsx'), sheet_name='MISO2_MI')

#%%%% Data import|Transport sector

######################################################################################################################################################
######################################################################################################################################################
#%% Scenarios
#%%%% Scenario parameters
#%%%%% Scenario parameters|Building sector
#%%%%%% Lifetime extension

lifetime_extension = 1.0 # Lifetime extension factor (1.0 = projected lifetime, 1.5 = lifetime increaed by 50%)

lifetimes = {                        # Assumed lifetimes:
    'SFH': 80  * lifetime_extension, # Single-family houses
    'MFH': 90  * lifetime_extension, # Multi-family houses
    'APB': 100 * lifetime_extension, # Apartment buildings
    'NRS': 60  * lifetime_extension} # Non-residential buildings   
    
#%%%%%% Reduction in new floor space

new_stocks_reduction = { # New floor space reduction factor (1 = projected floor space, 0 = no new construction)
    'SFH':  1.0, 
    'MFH':  1.0,
    'APB':  1.0,
    'NRS':  1.0}

#%%%%%% Urban-rural shift

apply_future_region_shares = False # 'True' = Rural/urban shift; if 'False', base year shares are kept constant

future_region_shares = {y: {'Urban': 0.75,                             # Urban share of new construction
                            'Rural': 0.25} for y in range(2023, 2061)} # Rural share of new construction

#%%% Building sector
#%%%% Building sector|Buildings
#%%%%% Building sector|Buildings|Products

# Smoothen population projection

data_POP = data_POP[data_POP['Year_to'].between(2000, 2100)].copy()
y = data_POP['Year_to'].values
v = data_POP['Value'].values
m = (y >= 2022) & (y <= 2030)
data_POP['Value_smooth'] = v.copy()
data_POP.loc[m, 'Value_smooth'] = PchipInterpolator(y[~m], v[~m])(y[m])

plt.figure(figsize=(12, 6))
plt.plot(data_POP['Year_to'], data_POP['Value']        / 1e6, 'b-', label='Original')
plt.plot(data_POP['Year_to'], data_POP['Value_smooth'] / 1e6, 'r-', label='Smoothed')
plt.legend()
plt.show()

# Weibull survival function

min_survival = 0.03 # Minimum survival set to account for historical building protection status

def calculate_survival_probability(age, lifetime, variance=0.2, min_survival=min_survival): 
    if age <= 0:
        return 1.0
    if variance   <= 0.2:
        k = 5.0  
    elif variance <= 0.3:
        k = 4.0
    elif variance <= 0.4:
        k = 3.0
    else:
        k = 2.5

    lambda_param = lifetime / math.gamma(1 + 1/k)  
    weibull_survival = np.exp(-(age/lambda_param)**k)
    
    survival_prob = weibull_survival + min_survival * (1 - weibull_survival)
    
    return max(0.0, min(1.0, survival_prob))

plt.figure(figsize=(8, 5))

def dict_to_ordered_list(lifetimes, order=['SFH', 'MFH', 'APB', 'NRS']):
    return [lifetimes[btype] for btype in order]

lifetimes_list = dict_to_ordered_list(lifetimes)

colors = ['red', 'blue', 'green', 'purple']
labels = ['SFH', 'MFH',  'APB',   'NRS']

ages = np.arange(0, 150, 1)

for L, color, label in zip(lifetimes_list, colors, labels):
    survival_probs = [calculate_survival_probability(age, L, 0.2) for age in ages]
    plt.plot(ages, survival_probs, label=label, color=color, linewidth=2)

plt.axhline(y=min_survival, color='black', linestyle='--', linewidth=1.5, alpha=0.7)
plt.text(0, min_survival * 1.05, 'minimum survival', color='black', fontsize=9, ha='left', va='bottom', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=2))
plt.xlabel('Building age (years)')
plt.ylabel('Survival probability')
plt.title('Weibull survival curves with 5% minimum survival floor')
plt.grid(True, alpha=0.3)
plt.legend()
plt.ylim(0, 1.05)
plt.tight_layout()
plt.show()

# Floor area projection

def project_building_stocks_fixed(data_prod_stocks_buildings, data_POP, lifetimes, 
                                 base_year=2022, target_year=2060,
                                 new_stocks_reduction=None,
                                 future_region_shares=None,
                                 apply_future_region_shares=True):
    
    if new_stocks_reduction is None:
        new_stocks_reduction = {'SFH': 1.0, 'MFH': 1.0, 'APB': 1.0, 'NRS': 1.0}
    
    if future_region_shares is None:
        future_region_shares = {y: {'Urban': 0.8, 'Rural': 0.2} 
                               for y in range(2023, target_year + 1)}
    
    pop_data = data_POP[data_POP['Year_from'].between(base_year, target_year)].copy()
    pop_data = pop_data.set_index('Year_from')['Value_smooth']

    current_stock = data_prod_stocks_buildings.copy()
    initial_stock = current_stock['Value'].sum()
    pop_2022 = pop_data[base_year]
    
    base_stocks_per_capita = initial_stock / pop_2022
    
    annual_summary =  []
    all_years_stock = []
    
    current_stock['Year'] = base_year
    all_years_stock.append(current_stock.copy())
    
    # Group age cohorts into decades
    def get_decadal_cohort(year):
        if 2001 <= year <= 2010:
            return 2001, 2010
        elif 2011 <= year <= 2020:
            return 2011, 2020
        elif 2021 <= year <= 2022: 
            return 2021, 2022
        elif 2023 <= year <= 2030:  
            return 2023, 2030
        elif 2031 <= year <= 2040:
            return 2031, 2040
        elif 2041 <= year <= 2050:
            return 2041, 2050
        elif 2051 <= year <= 2060:
            return 2051, 2060
        else:
            return None, None
    
    for year in range(base_year, target_year + 1):
        
        if year == base_year:
            total_stock = initial_stock
            additions =   0
            eol_outflow = 0
            pop_current = pop_2022
            stocks_per_capita = base_stocks_per_capita
            
        else:
            year_stock = current_stock.copy()
            year_stock['Year'] = year
            
            total_eol_outflow = 0
            
            # Application of survival functions
            for idx, row in year_stock.iterrows():
                bldg_type = row['Type_lv2']
                lifetime = lifetimes.get(bldg_type, 80)
                
                construction_year = (row['Year_from'] + row['Year_to']) / 2

                building_age = year - construction_year
                
                survival_prob = calculate_survival_probability(building_age, lifetime, 0.15)
                survival_prob_prev_year = calculate_survival_probability(building_age - 1, lifetime, 0.15)

                if survival_prob_prev_year > 0:
                    demolition_prob = 1 - (survival_prob / survival_prob_prev_year)
                else:
                    demolition_prob = 0.0
                
                eol_outflow = row['Value'] * demolition_prob
                total_eol_outflow += eol_outflow
                year_stock.at[idx, 'Value'] = row['Value'] - eol_outflow
            
            # Population-driven target stock
            pop_current = pop_data.get(year, pop_data.iloc[-1])
            target_stock = pop_current * base_stocks_per_capita
            
            # Required construction
            current_stocks_after_demo = year_stock['Value'].sum()
            stocks_gap = target_stock - current_stocks_after_demo
            
            # Distribution of new construction
            if stocks_gap > 0:
                type_dist = data_prod_stocks_buildings.groupby('Type_lv2')['Value'].sum()
                type_dist = type_dist / type_dist.sum()
                
                for bldg_type, proportion in type_dist.items():
                    total_needed = stocks_gap * proportion
                    
                    reduction = new_stocks_reduction.get(bldg_type, 1.0)
                    new_for_type = total_needed * reduction
                    
                    if new_for_type > 0.1:
                        decade_start, decade_end = get_decadal_cohort(year)
                        
                        if decade_start is None:
                            continue
                        if apply_future_region_shares and year in future_region_shares:
                            urban_share = future_region_shares[year].get('Urban', 0.8)
                            rural_share = future_region_shares[year].get('Rural', 0.2)
                        else:
                            base_shares = data_prod_stocks_buildings.groupby('Region_lv2')['Value'].sum()
                            base_shares = base_shares / base_shares.sum()
                            urban_share = base_shares.get('Urban', 0.8)
                            rural_share = base_shares.get('Rural', 0.2)
                        
                        urban_new = new_for_type * urban_share
                        rural_new = new_for_type * rural_share
                        
                        # Urban construction
                        if urban_new > 0.1:
                            existing_mask_urban = (
                                (year_stock['Type_lv2'] ==   bldg_type) &
                                (year_stock['Region_lv2'] == 'Urban') &
                                (year_stock['Year_from'] ==  decade_start) &
                                (year_stock['Year_to'] ==    decade_end))
                            
                            if existing_mask_urban.any():
                                cohort_idx = year_stock[existing_mask_urban].index[0]
                                year_stock.at[cohort_idx, 'Value'] += urban_new
                            else:
                                sample_row = year_stock.iloc[0]
                                new_row = {
                                    'Parameter':  sample_row['Parameter'],
                                    'Region_lv1': sample_row['Region_lv1'],
                                    'Region_lv2': 'Urban',
                                    'Type_lv1':   sample_row['Type_lv1'],
                                    'Type_lv2':   bldg_type,
                                    'Ownership':  sample_row['Ownership'],
                                    'Year_from':  decade_start,
                                    'Year_to':    decade_end,
                                    'Unit':       sample_row['Unit'],
                                    'Value':      urban_new,
                                    'Year':       year}
                                year_stock = pd.concat([year_stock, pd.DataFrame([new_row])], ignore_index=True)
                        
                        # Rural construction
                        if rural_new > 0.1:
                            existing_mask_rural = (
                                (year_stock['Type_lv2'] ==   bldg_type) &
                                (year_stock['Region_lv2'] == 'Rural') &
                                (year_stock['Year_from'] ==  decade_start) &
                                (year_stock['Year_to'] ==    decade_end))
                            
                            if existing_mask_rural.any():
                                cohort_idx = year_stock[existing_mask_rural].index[0]
                                year_stock.at[cohort_idx, 'Value'] += rural_new
                            else:
                                sample_row = year_stock.iloc[0]
                                new_row = {
                                    'Parameter':  sample_row['Parameter'],
                                    'Region_lv1': sample_row['Region_lv1'],
                                    'Region_lv2': 'Rural',
                                    'Type_lv1':   sample_row['Type_lv1'],
                                    'Type_lv2':   bldg_type,
                                    'Ownership':  sample_row['Ownership'],
                                    'Year_from':  decade_start,
                                    'Year_to':    decade_end,
                                    'Unit':       sample_row['Unit'],
                                    'Value':      rural_new,
                                    'Year':       year}
                                year_stock = pd.concat([year_stock, pd.DataFrame([new_row])], ignore_index=True)
            
            current_stock = year_stock.copy()
            all_years_stock.append(year_stock.copy())
            
            total_stock =      year_stock['Value'].sum()
            additions =        stocks_gap
            eol_outflow =      total_eol_outflow
            stocks_per_capita = total_stock / pop_current
        
        annual_summary.append({
            'Year':       year,
            'Stocks':     total_stock,
            'Pop':        pop_current,
            'Stocks_cap': stocks_per_capita,
            'NAS':        additions,
            'EOL':        eol_outflow})
    
    full_series = pd.concat(all_years_stock, ignore_index=True)
    annual_summary_df = pd.DataFrame(annual_summary)
    
    return full_series, annual_summary_df

stocks_buildings_proj, annual_summary_age = project_building_stocks_fixed(
    data_prod_stocks_buildings = stocks_buildings_base,
    data_POP =                   data_POP,
    lifetimes =                  lifetimes,
    new_stocks_reduction =       new_stocks_reduction,
    future_region_shares =       future_region_shares,
    apply_future_region_shares = apply_future_region_shares)

print(annual_summary_age[['Year', 'Stocks', 'Pop', 'Stocks_cap', 'NAS', 'EOL']].to_string(index=False, formatters={
    'Year':       lambda x: f'{int(x):>6}',
    'Stocks':     lambda x: f'{x:>15.2f}',
    'Pop':        lambda x: f'{int(x):>15.0f}',
    'Stocks_cap': lambda x: f'{x:>15.2f}',
    'NAS':        lambda x: f'{x:>15.2f}',
    'EOL':        lambda x: f'{x:>12.2f}'}))

# Plot: Total building stock (2022-2060)

plt.figure(figsize=(9, 4))
plt.plot(annual_summary_age['Year'], annual_summary_age['Stocks'] / 1e6, 'b-', linewidth=2)
plt.ylim(0, max(annual_summary_age['Stocks'] / 1e6) * 1.2)
plt.xlabel('Year')
plt.ylabel('Net floor area (million m²)')
plt.title('Total building stock (2022-2060)')
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Plot: Annual total NAS and EOL floor area (2023-2060)

plt.figure(figsize=(9, 4))
mask = (annual_summary_age['Year'] >= 2023) & (annual_summary_age['Year'] <= 2060)
plt.plot(annual_summary_age['Year'][mask], annual_summary_age['NAS'][mask] / 1e6, 'g-', linewidth=2, label='NAS')
plt.plot(annual_summary_age['Year'][mask], annual_summary_age['EOL'][mask] / 1e6, 'r-', linewidth=2, label='EOL')
plt.xlabel('Year')
plt.ylabel('Net floor area (million m²/year)')
plt.title('Annual total NAS and EOL floor area (2023-2060)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Plot: Location of building stock (2022-2060)

urban_stock = []
rural_stock = []

for year in annual_summary_age['Year']:
    year_data = stocks_buildings_proj[stocks_buildings_proj['Year'] == year]
    urban = year_data[year_data['Region_lv2'] == 'Urban']['Value'].sum()
    rural = year_data[year_data['Region_lv2'] == 'Rural']['Value'].sum()
    urban_stock.append(urban / 1e6)  
    rural_stock.append(rural / 1e6)

plt.figure(figsize=(9, 4))
plt.plot(annual_summary_age['Year'], urban_stock, 'b-', linewidth=2, label='Urban stock')
plt.plot(annual_summary_age['Year'], rural_stock, 'g-', linewidth=2, label='Rural stock')
plt.ylim(0, max(max(urban_stock), max(rural_stock)) * 1.1)
plt.xlabel('Year')
plt.ylabel('Net floor area (million m²)')
plt.title('Location of building stock (2022-2060)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Plot: Total building stock per age cohort (2022-2060)

stocks_buildings_proj_cohort = stocks_buildings_proj.copy()
stocks_buildings_proj_cohort['Value'] = stocks_buildings_proj_cohort['Value'] / 1000000 # Unit: million m2 NFA

stocks_buildings_proj_cohort['Cohort'] = stocks_buildings_proj.apply(
    lambda row: f"{int(row['Year_from'])}-{int(row['Year_to'])}" 
    if pd.notna(row['Year_from']) and pd.notna(row['Year_to']) 
    else "Unknown", axis=1)

cohort_order = sorted(stocks_buildings_proj_cohort['Cohort'].unique(), key=lambda x: int(x.split('-')[0]))
stacked_data = stocks_buildings_proj_cohort.pivot_table(index='Year', columns='Cohort', values='Value', aggfunc='sum').fillna(0)
stacked_data = stacked_data[cohort_order]

fig, ax = plt.subplots(figsize=(10, 6))
colors = plt.cm.viridis_r(np.linspace(0.2, 0.9, len(cohort_order)))
ax.stackplot(stacked_data.index, stacked_data.T, labels=stacked_data.columns, colors=colors, alpha=0.85, edgecolor='white', linewidth=0.5)
ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Net floor area (million m2)', fontsize=12)
ax.set_title('Total building stock per age cohort (2022-2060)', fontsize=14, pad=20)
ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), title='Construction period', title_fontsize=11)
ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
ax.set_facecolor('#f8f9fa')
ax.set_xlim(stacked_data.index.min(), stacked_data.index.max())
plt.tight_layout()
plt.show()

#%%%%% Building sector|Buildings|Stocks

data_MI_buildings = data_MI_buildings.assign(Type_lv2=data_MI_buildings['Type_lv2'].replace({'SFH/MFH':'SFH'}))
data_MI_buildings = pd.concat([data_MI_buildings, data_MI_buildings[data_MI_buildings['Type_lv2']=='SFH'].assign(Type_lv2='MFH')], ignore_index=True)

age_cohort_map = { 
    # Floor area            MI           
    (1880, 1918): (0,    1918),
    (1919, 1944): (1919, 1944),
    (1945, 1960): (1945, 1970),
    (1961, 1970): (1945, 1970),
    (1971, 1980): (1971, 1980),
    (1981, 1990): (1981, 1990),
    (1991, 2000): (1991, 2000),
    (2001, 2010): (2001, 2100),
    (2011, 2022): (2001, 2100),
    (2023, 2030): (2001, 2100),
    (2031, 2040): (2001, 2100),
    (2041, 2050): (2001, 2100),
    (2051, 2060): (2001, 2100)}

def map_age_cohort(year_from, year_to):
    return age_cohort_map.get((year_from, year_to), (year_from, year_to))

stocks_buildings_proj_prep = stocks_buildings_proj.copy()
stocks_buildings_proj_prep['MI_Year_from'] = stocks_buildings_proj_prep.apply(lambda row: map_age_cohort(row['Year_from'], row['Year_to'])[0], axis=1)
stocks_buildings_proj_prep['MI_Year_to'] =   stocks_buildings_proj_prep.apply(lambda row: map_age_cohort(row['Year_from'], row['Year_to'])[1], axis=1)
stocks_buildings_proj_prep['Value'] = pd.to_numeric(stocks_buildings_proj_prep['Value'], errors='coerce')

data_MI_buildings = data_MI_buildings.rename(columns={
    'Year_from': 'MI_Year_from',
    'Year_to':   'MI_Year_to',
    'Value':     'MI_Value'})

data_MI_buildings['MI_Value'] = pd.to_numeric(data_MI_buildings['MI_Value'], errors='coerce')

data_MI_buildings_pivot = data_MI_buildings.pivot_table(index=['Region_lv1', 'Type_lv2', 'MI_Year_from', 'MI_Year_to'], columns='Material', values='MI_Value', aggfunc='first').reset_index()
data_MI_buildings_pivot = data_MI_buildings_pivot.rename(columns=lambda x: f"MI_{x}" if x not in ['Region_lv1', 'Type_lv2', 'MI_Year_from', 'MI_Year_to'] else x)
stocks_buildings_proj_wide = pd.merge(stocks_buildings_proj_prep, data_MI_buildings_pivot, how='left', on=['Region_lv1', 'Type_lv2', 'MI_Year_from', 'MI_Year_to'])

material_columns = [col for col in stocks_buildings_proj_wide.columns 
                    if col.startswith('MI_') 
                    and col not in ['MI_Year_from', 'MI_Year_to']]

for col in material_columns:
    stocks_buildings_proj_wide[col] = pd.to_numeric(stocks_buildings_proj_wide[col], errors='coerce')

id_cols = [col for col in stocks_buildings_proj_wide.columns 
           if not col.startswith('MI_') 
           and col not in ['MI_Year_from', 'MI_Year_to']]

stocks_buildings_proj = pd.melt(stocks_buildings_proj_wide, id_vars=id_cols, value_vars=material_columns, var_name='Material', value_name='MI')

stocks_buildings_proj['Material'] = stocks_buildings_proj['Material'].str[3:]
stocks_buildings_proj['Stocks_t'] = stocks_buildings_proj['Value'] * stocks_buildings_proj['MI']
stocks_buildings_proj = stocks_buildings_proj.rename(columns={'Value': 'FU_m2_NFA'})
stocks_buildings_proj = stocks_buildings_proj.loc[:, list(stocks_buildings_proj.loc[:, 'Parameter':'Year_to'].columns) + ['Material', 'Year', 'FU_m2_NFA', 'Stocks_t']]

# Plot: Material stocks per material

stocks_buildings_proj_sum = stocks_buildings_proj.groupby(['Year', 'Region_lv1', 'Material'])['Stocks_t'].sum().reset_index()
stocks_buildings_proj_sum['Stocks_Mt'] = stocks_buildings_proj_sum['Stocks_t'] / 1_000_000
stacked_materials = stocks_buildings_proj_sum.pivot_table(index='Year', columns='Material', values='Stocks_Mt', aggfunc='sum').fillna(0)
ordered_cols = [m for m in color_map.keys() if m in stacked_materials.columns]
stacked_materials = stacked_materials[ordered_cols]
colors = [color_map[m] for m in ordered_cols]

fig, ax = plt.subplots(figsize=(10, 6))
ax.stackplot(stacked_materials.index, stacked_materials.T.values, labels=ordered_cols, colors=colors, alpha=0.85, linewidth=0.3)
ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Material stock (Mt)', fontsize=12)
ax.set_title('Material stocks in buildings per material', fontsize=14, pad=20)
ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), title='Material', title_fontsize=12, fontsize=10, ncol=1, frameon=True, fancybox=True, shadow=True)
plt.tight_layout()
plt.show()

# Export

stocks_buildings_proj.to_parquet("output/interim/stocks_buildings_proj.parquet", index=False)

#%%%% Building sector|Heating systems
#%%%%% Building sector|Heating systems|Products

# Stock projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase efficiency

# Calculate final energy demand of building stock: floor space (m2) * age-cohort and type-specific Final energy demand for heating [kWh/m²/a] (renovated and unrenovated)
# Calculate final energy input of building stock, heizgradtagbereinigt: Above demand * shares of different heating types (Kranzl: gas, wood chips, solar, etc., %) / heating day ratio (CeAT)
# Calculate installed capacity (GW) per heating type by dividing above final energy input by heating hours, then apply multiplication factor (Kranzl)

#%%%%% Building sector|Heating systems|Stocks

# Calculate material stock of installed capacity: MI * Installed capacity

#%%%%% Building sector|Heating systems|Operation

# Apply fuel usage of heating systems for operation based on CeAT data

#%%%% Building sector|Cooling systems
#%%%%% Building sector|Cooling systems|Products

# Analogous approach to heating systems
#%%%%% Building sector|Cooling systems|Stocks

# Analogous approach to heating systems

#%%%%% Building sector|Cooling systems|Operation

# Analogous approach to heating systems

#%%%% Building sector|Household appliances
#%%%%% Building sector|Household appliances|Products

# Product projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase sharing (reduction))

#%%%%% Building sector|Household appliances|Stocks

# Apply material intensity factors (to be compiled)

#%%%%% Building sector|Household appliances|Operation

# Apply operational energy use of household appliances (look up factors)

#%%% Transport sector
#%%%% Transport sector|Mobility

# Mobility projections (pkm/tkm)
# Convert to vkm using occupancy rates
# Implement 2060 modal split that can be set in config
# Implement different options: a) trend continuation, b) mobility reduction, c) shift to active/public

#%%%% Transport sector|Vehicles|Products

# Stock projections
# Implement different options: a) project to 2060 using mobility (above) as proxies, b) set level; c) increase sharing (reduction))

#%%%% Transport sector|Vehicles|Stocks

# Apply MI factors

#%%%% Transport sector|Vehicles|Operation

# Apply fuel consumption (l fuel/vkm) to traffic scenarios based on Lederer et al. projections and CeAT factors

#%%%% Transport sector|Infrastructure
#%%%% Transport sector|Infrastructure|Products

# Take transport infrastructure from GLOMIS and couple with vkm (

#%%%% Transport sector|Infrastructure|Stocks

# Multiply areas with MIs 











