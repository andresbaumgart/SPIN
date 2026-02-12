# !/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model: Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author: André Baumgart (BOKU)
Email: andre.baumgart@boku.ac.at
Purpose: Scenario design and material stock modelling
'''

#%% Packages

import os
import numpy as np
import pandas as pd
import math

#%% Data import

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    cols = df.loc[:, 'Parameter':'Value'].columns.tolist()
    return df[cols]

#%%% Data import|General

data_GDP = read_excel(os.path.join(main_path, 'input/data_GDP_constr.xlsx'), sheet_name='MISO2_GDP')
data_POP = read_excel(os.path.join(main_path, 'input/data_POP.xlsx'), sheet_name='MISO2_POP')

#%%% Data import|Building sector

data_prod_stock_buildings = pd.read_parquet("output/interim/stock_base_buildings_products.parquet")
data_MI_buildings = read_excel(os.path.join(main_path, 'input/data_MI_buildings.xlsx'), sheet_name='MISO2_MI')

#%%% Data import|Transport sector

#%% Scenarios
#%%%% Scenario parameters
#%%%%% Scenario parameters|Building sector
#%%%%%% Lifetime extension

lifetime_extension = 1.00 # Lifetime extension factor (1 = projected lifetime, 2 = doubled lifetime)

lifetimes = {                         # Assumed lifetimes:
    'SFH': 80  * lifetime_extension,  # Single Family Houses: 80 years
    'MFH': 90  * lifetime_extension,  # Multi Family Houses: 90 years
    'APB': 100 * lifetime_extension,  # Apartment Buildings: 100 years
    'NRS': 60  * lifetime_extension} # Non-Residential Structures: 60 years   
    
#%%%%%% New floor space reduction

new_stock_reduction = { # New floor space reduction factor (1 = projected floor space, 0 = no new construction)
    'SFH':  1.0, 
    'MFH':  1.0,
    'APB':  1.0,
    'NRS':  1.0}

#%%%%%%  Spatial shift

apply_future_region_shares = False # 'True' = Rural/urban shift; if 'False', base year shares are kept constant

future_region_shares = {y: {'Urban': 0.75, # Spatial shares of new construction
                            'Rural': 0.25} for y in range(2023, 2061)} # Sum must be 1

#%%% Building sector
#%%%% Building sector|Buildings
#%%%%% Building sector|Buildings|Products

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Weibull survival function

def calculate_survival_probability(age, lifetime, variance=0.2):
    if age <= 0:
        return 1.0
    if variance <= 0.2:
        k = 5.0  
    elif variance <= 0.3:
        k = 4.0
    elif variance <= 0.4:
        k = 3.0
    else:
        k = 2.5

    lambda_param = lifetime / math.gamma(1 + 1/k)  
    survival_prob = np.exp(-(age/lambda_param)**k)
    
    return max(0.0, min(1.0, survival_prob))

plt.figure(figsize=(8, 5))

def dict_to_ordered_list(lifetimes, order=['SFH', 'MFH', 'APB', 'NRS']):
    return [lifetimes[btype] for btype in order]

lifetimes_list = dict_to_ordered_list(lifetimes)

colors = ['red', 'blue', 'green', 'purple']
labels = ['SFH (80 yrs)', 'MFH (90 yrs)', 'APB (100 yrs)', 'NRS (60 yrs)']

ages = np.arange(0, 150, 1)

for L, color, label in zip(lifetimes_list, colors, labels):
    survival_probs = [calculate_survival_probability(age, L, 0.2) for age in ages]
    plt.plot(ages, survival_probs, label=label, color=color, linewidth=2)

plt.xlabel('Building Age (years)')
plt.ylabel('Survival Probability')
plt.title('Weibull Survival Curves')
plt.grid(True, alpha=0.3)
plt.legend()
plt.ylim(0, 1.05)
plt.tight_layout()
plt.show()

# Floor area projection

def project_building_stock_fixed(data_prod_stock_buildings, data_POP, lifetimes, 
                                 base_year=2022, target_year=2060,
                                 new_stock_reduction=None,
                                 future_region_shares=None,
                                 apply_future_region_shares=True):
    
    if new_stock_reduction is None:
        new_stock_reduction = {'SFH': 1.0, 'MFH': 1.0, 'APB': 1.0, 'NRS': 1.0}
    
    if future_region_shares is None:
        future_region_shares = {y: {'Urban': 0.8, 'Rural': 0.2} 
                               for y in range(2023, target_year + 1)}
    
    pop_data = data_POP[data_POP['Year_from'].between(base_year, target_year)].copy()
    pop_data = pop_data.set_index('Year_from')['Value']

    current_stock = data_prod_stock_buildings.copy()
    initial_stock = current_stock['Value'].sum()
    pop_2022 = pop_data[base_year]
    
    base_stock_per_capita = initial_stock / pop_2022
    
    annual_summary = []
    all_years_stock = []
    
    current_stock['Year'] = base_year
    all_years_stock.append(current_stock.copy())
    
    # Group age cohorts into decades
    def get_decadal_cohort(year):
        if 2001 <= year <= 2010:
            return 2001, 2010
        elif 2011 <= year <= 2020:
            return 2011, 2020
        elif 2021 <= year <= 2030:
            return 2021, 2030
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
            net_change =  0
            pop_current = pop_2022
            stock_per_capita = base_stock_per_capita
            
        else:
            year_stock = current_stock.copy()
            year_stock['Year'] = year
            
            total_eol_outflow = 0
            total_additions =   0
            
            # Apply survival functions
            for idx, row in year_stock.iterrows():
                bldg_type = row['Type_lv2']
                lifetime = lifetimes.get(bldg_type, 80)
                
                mean_year = (row['Year_from'] + row['Year_to']) / 2
                building_age = year - mean_year
                
                # Low demolition of new buildings
                if building_age < 40:
                    demolition_prob = 0.0001  # 0.01% per year
                else:
                    # Survival probability
                    survival_prob = calculate_survival_probability(building_age, lifetime, 0.15)
                    survival_prob_prev_year = calculate_survival_probability(building_age - 1, lifetime, 0.15)
                    
                    # Demolition probability 
                    if survival_prob_prev_year > 0:
                        demolition_prob = 1 - (survival_prob / survival_prob_prev_year)
                    else:
                        demolition_prob = 0.0
                
                eol_outflow = row['Value'] * demolition_prob
                total_eol_outflow += eol_outflow
                year_stock.at[idx, 'Value'] = row['Value'] - eol_outflow
            
            # Population-driven target stock
            pop_current = pop_data.get(year, pop_data.iloc[-1])
            target_stock = pop_current * base_stock_per_capita
            
            # Required construction
            current_stock_after_demo = year_stock['Value'].sum()
            stock_gap = target_stock - current_stock_after_demo
            previous_stock = annual_summary[-1]['Total_Stock']
            
            # Distribution of new construction
            if stock_gap > 0:
                type_dist = data_prod_stock_buildings.groupby('Type_lv2')['Value'].sum()
                type_dist = type_dist / type_dist.sum()
                
                for bldg_type, proportion in type_dist.items():
                    total_needed = stock_gap * proportion
                    
                    reduction = new_stock_reduction.get(bldg_type, 1.0)
                    new_for_type = total_needed * reduction
                    
                    if new_for_type > 0.1:
                        decade_start, decade_end = get_decadal_cohort(year)
                        
                        if decade_start is None:
                            continue
                        if apply_future_region_shares and year in future_region_shares:
                            urban_share = future_region_shares[year].get('Urban', 0.8)
                            rural_share = future_region_shares[year].get('Rural', 0.2)
                        else:
                            base_shares = data_prod_stock_buildings.groupby('Region_lv2')['Value'].sum()
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
            additions =        stock_gap
            eol_outflow =      total_eol_outflow
            net_change =       total_stock - previous_stock
            stock_per_capita = total_stock / pop_current
        
        annual_summary.append({
            'Year': year,
            'Total_Stock':      total_stock,
            'Population':       pop_current,
            'Stock_per_Capita': stock_per_capita,
            'Additions':        additions,
            'EOL_Outflows':     eol_outflow,
            'Net_Change':       net_change})
    
    full_series = pd.concat(all_years_stock, ignore_index=True)
    annual_summary_df = pd.DataFrame(annual_summary)
    
    return full_series, annual_summary_df

stock_buildings, annual_summary_age = project_building_stock_fixed(
    data_prod_stock_buildings=        data_prod_stock_buildings,
    data_POP=                         data_POP,
    lifetimes=                        lifetimes,
    new_stock_reduction=              new_stock_reduction,
    future_region_shares=             future_region_shares,
    apply_future_region_shares=       apply_future_region_shares)

header_format = "{:>6} | {:>15} | {:>15} | {:>15} | {:>15} | {:>12}"
data_format =   "{:>6} | {:>15.2f} | {:>15.0f} | {:>15.2f} | {:>15.2f} | {:>12.2f}"

print(header_format.format('Year', 'Total Stock', 'Population', 'Stock/Capita', 'Additions', 'Demolitions'))
print("-" * 93)

for _, row in annual_summary_age.iterrows():
    year =             int(row['Year'])
    total_stock =      row['Total_Stock']
    population =       row['Population']
    stock_per_capita = row['Stock_per_Capita']
    additions =        row['Additions']
    demolitions =      row['EOL_Outflows']
    
    print(data_format.format(year, total_stock, population, stock_per_capita, additions, demolitions))

print("-" * 93)

# Plot: Total building stock
plt.figure(figsize=(9, 4))
plt.plot(annual_summary_age['Year'], annual_summary_age['Total_Stock'] / 1e6, 'b-', linewidth=2, marker='o', markersize=4)
plt.xlabel('Year')
plt.ylabel('Total Building Stock (million m²)')
plt.title('Total Building Stock Projection 2022-2060')
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Plot: Annual construction and demolition flows
plt.figure(figsize=(9, 4))
plt.plot(annual_summary_age['Year'], annual_summary_age['Additions'] / 1e6, 'g-', linewidth=2, label='Additions', marker='^', markersize=4)
plt.plot(annual_summary_age['Year'], annual_summary_age['EOL_Outflows'] / 1e6, 'r-', linewidth=2, label='Demolitions', marker='v', markersize=4)
plt.xlabel('Year')
plt.ylabel('Annual Flow (million m²/year)')
plt.title('Annual Construction and Demolition')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Plot: Urban vs rural stock
urban_stock = []
rural_stock = []

for year in annual_summary_age['Year']:
    year_data = stock_buildings[stock_buildings['Year'] == year]
    urban = year_data[year_data['Region_lv2'] == 'Urban']['Value'].sum()
    rural = year_data[year_data['Region_lv2'] == 'Rural']['Value'].sum()
    urban_stock.append(urban / 1e6)  
    rural_stock.append(rural / 1e6)

plt.figure(figsize=(9, 4))
plt.plot(annual_summary_age['Year'], urban_stock, 'b-', linewidth=2, label='Urban Stock', marker='s', markersize=4)
plt.plot(annual_summary_age['Year'], rural_stock, 'g-', linewidth=2, label='Rural Stock', marker='d', markersize=4)
plt.xlabel('Year')
plt.ylabel('Building Stock (million m²)')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()










# CALCULATE STOCKS













data_MI_buildings = data_MI_buildings.assign(Type_lv2=data_MI_buildings['Type_lv2'].replace({'SFH/MFH':'SFH'}))
data_MI_buildings = pd.concat([data_MI_buildings, data_MI_buildings[data_MI_buildings['Type_lv2']=='SFH'].assign(Type_lv2='MFH')], ignore_index=True)

age_cohort_map = { # Match MI and housing census age cohorts 
    (0,    1918): (0,    1918),
    (1919, 1944): (1919, 1944),
    (1945, 1960): (1945, 1970),
    (1961, 1970): (1945, 1970),
    (1971, 1980): (1971, 1980),
    (1981, 1990): (1981, 1990),
    (1991, 2000): (1991, 2000),
    (2001, 2010): (2001, 2100),
    (2011, 2100): (2001, 2100)}

def map_year(row):
    return age_cohort_map.get((row['Year_from'], row['Year_to']), (np.nan, np.nan))

data_prod_stock_buildings_proj[['MI_Year_from','MI_Year_to']] = pd.DataFrame(data_prod_stock_buildings_proj.apply(map_year, axis=1).tolist(), index=data_prod_stock_buildings_proj.index)

stock_buildings = data_prod_stock_buildings_proj.merge(
    data_MI_buildings[['Region_lv1', 'Region_lv2', 'Type_lv2', 'Year_from','Year_to','Material','Value']],
    left_on=['Region_lv1','Type_lv2','MI_Year_from','MI_Year_to'],
    right_on=['Region_lv1','Type_lv2','Year_from','Year_to'],
    suffixes=('','_mi')).rename(columns={'Value': 'FU_m2_UFA'}) # UFA = useful floor area

stock_buildings['Value'] =     stock_buildings['FU_m2_NFA'] * stock_buildings['Value_mi'] # Material stocks

stock_buildings['Parameter'] = 'Material stock'
stock_buildings['Unit'] =      'metric tons'

stock_buildings = stock_buildings[stock_buildings.loc[:, 'Parameter':'Year_to'].columns.tolist() + ['Material', 'Unit', 'Value', 'FU_m2_UFA', 'FU_m2_NFA']]

print("Total material stocks in buildings (Mt):", stock_buildings['Value'].sum() / 1e6)
print(stock_buildings.groupby('Type_lv2')['Value'].sum() / 1e6)
print(stock_buildings.groupby('Material')['Value'].sum() / 1e6)

stock_buildings.to_parquet("output/interim/stock_base_buildings.parquet", index=False)

# CHECK WHY STOCKS ARE SO HIGH (SHOULD BE AROUND 600 Mt, check why 179314 Mt)
# TRACE BACK WHERE POSSIBLE DOUBLE COUNTINGS OR UNIT ERRORS OCCUR (total floor area looks okay so likely allocation of MI factors)








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











