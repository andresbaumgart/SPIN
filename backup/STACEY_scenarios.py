#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Scenario design and material stock modelling
'''

# Notes

# Scenario assumptions for new construction: Is this actual new construction if demolished building replacement is not considered herein?

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side
from datetime import datetime

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    cols = df.loc[:, 'Parameter':'Source'].columns.tolist()
    return df[cols]

#%%% Data import

data_POP = read_excel(os.path.join(main_path, 'input/data_POP.xlsx'), sheet_name='MISO2_POP')

stocks_buildings_base = pd.read_parquet('output/interim/stocks_buildings_base.parquet')

#%%%% Material intensity database

data_MI = read_excel(os.path.join(main_path, 'input/data_MI.xlsx'), sheet_name='MISO2_MI')

all_years = range(1900, 2101)
pivot_data = []

for (country, element, sector, material), group in data_MI.groupby(['MISO2_country', 'Element', 'End_use_sector', 'Material']):
    row_dict = {'MISO2_country': country, 'Element': element, 'End_use_sector': sector, 'Material': material}
    for year in all_years:
        value = None
        for _, mi_row in group.iterrows():
            if year >= mi_row['Year_from'] and year <= mi_row['Year_to']:
                value = mi_row['Value']
                break
        row_dict[year] = value
    pivot_data.append(row_dict)

values_df = pd.DataFrame(pivot_data)
year_columns = [col for col in values_df.columns if isinstance(col, int)]
values_df[year_columns] = values_df[year_columns].ffill(axis=1).bfill(axis=1)

sources_df = values_df.copy()
for col in year_columns:
    sources_df[col] = ''

for idx, row in values_df.iterrows():
    country = row['MISO2_country']
    element = row['Element']
    sector = row['End_use_sector']
    material = row['Material']
    subset = data_MI[(data_MI['MISO2_country']  == country) & 
                     (data_MI['Element']        == element) &
                     (data_MI['End_use_sector'] == sector) & 
                     (data_MI['Material']       == material)]
    for _, mi_row in subset.iterrows():
        year_range = range(mi_row['Year_from'], mi_row['Year_to'] + 1)
        for year in year_range:
            if year in year_columns:
                sources_df.loc[idx, year] = mi_row['Source']

output_path = os.path.join(main_path, 'output/MISO_inputs/MISO2_MaterialIntensity_Functions_v1.xlsx')
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with pd.ExcelWriter(output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    values_df.to_excel(writer, sheet_name='values', index=False)
    sources_df.to_excel(writer, sheet_name='sources', index=False)

wb = load_workbook(output_path)
thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin'))

for sheet_name in ['values', 'sources']:
    ws = wb[sheet_name]
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border

if 'Cover' in wb.sheetnames:
    wb['Cover']['B12'] = datetime.now().strftime('%d.%m.%Y')

wb.save(output_path)

######################################################################################################################################################
######################################################################################################################################################
#%% Scenarios
#%%%% Scenario parameters

#%%%%%% Reduction in new floor space

new_stocks_reduction = { # New floor space reduction factor (1 = projected floor space, 0 = no new construction)
    'R_SFH':      1.0, 
    'R_MFH':      1.0,
    'R_APB':      1.0,
    'R_IHH':      1.0,
    'NR_public':  1.0,
    'NR_indust':  1.0,
    'NR_trafcom': 1.0,
    'NR_retail':  1.0,
    'NR_office':  1.0,
    'NR_hotel':   1.0}

#%%%%%% Urban-rural shift

apply_future_region_shares = True # 'True' = urban/rural shift; if 'False', base year shares are kept constant

future_region_shares = {y: {'Urban':                                         0.60, # Urban share of new construction
                            'Regional centre (central)':                     0.05, 
                            'Regional centre (intermediate)':                0.05,
                            'Rural area (central)':                          0.05,
                            'Rural area (intermediate)':                     0.05,
                            'Rural area (peripheral)':                       0.05,
                            'Rural area surrounding centres (central)':      0.05,
                            'Rural area surrounding centres (intermediate)': 0.05,
                            'Rural area surrounding centres (peripheral)':   0.05     
                            } for y in range(2023, 2101)} 

######################################################################################################################################################
######################################################################################################################################################
#%% Building sector projection

# Smoothen population projection
data_POP = data_POP[data_POP['Year_to'].between(2000, 2100)].copy()
y = data_POP['Year_to'].values
v = data_POP['Value'].values
m = (y >= 2022) & (y <= 2030)

data_POP['Value_smooth'] = v.astype(float).copy()
data_POP.loc[m, 'Value_smooth'] = PchipInterpolator(y[~m], v[~m])(y[m])

plt.figure(figsize=(12, 6))
plt.plot(data_POP['Year_to'], data_POP['Value'] / 1e6, 'b-', label='Original')
plt.plot(data_POP['Year_to'], data_POP['Value_smooth'] / 1e6, 'r-', label='Smoothed')
plt.legend()
plt.title('Population Projection')
plt.xlabel('Year')
plt.ylabel('Population (millions)')
plt.grid(True, alpha=0.3)
plt.show()

# Projection function
def project_building_stocks_simple(data_func_stocks_buildings, data_POP, 
                                   base_year=2023, target_year=2100,
                                   new_stocks_reduction=None,
                                   future_region_shares=None,
                                   apply_future_region_shares=True):
    
    if new_stocks_reduction is None:
        new_stocks_reduction = {btype: 1.0 for btype in data_func_stocks_buildings['Type_lv2'].unique()}
    
    if future_region_shares is None:
        future_region_shares = {y: {} for y in range(base_year + 1, target_year + 1)}
    
    # Prepare population data
    pop_data = data_POP[data_POP['Year_from'].between(base_year, target_year)].copy()
    pop_data = pop_data.set_index('Year_from')['Value_smooth']
    
    # Base year stock (2023)
    base_stock = data_func_stocks_buildings.copy()
    base_stock['Year'] = base_year
    
    total_stock_2023 = base_stock['Value'].sum()
    pop_2023 = pop_data[base_year]
    
    # Calculate REDUCED target stock based on reduction factors
    # Apply reduction factors to the base year per-building-type stock
    reduced_base_stock = 0
    type_reduced_stock = {}
    
    for bldg_type in data_func_stocks_buildings['Type_lv2'].unique():
        type_stock_2023 = data_func_stocks_buildings[data_func_stocks_buildings['Type_lv2'] == bldg_type]['Value'].sum()
        reduction = new_stocks_reduction.get(bldg_type, 1.0)
        type_reduced_stock[bldg_type] = type_stock_2023 * reduction
        reduced_base_stock += type_reduced_stock[bldg_type]
    
    # Calculate new per-capita stock based on reduced total
    stocks_per_capita_target = reduced_base_stock / pop_2023
    
    # Get distribution factors from base year (original, not reduced)
    type_dist = data_func_stocks_buildings.groupby('Type_lv2')['Value'].sum()
    type_dist = type_dist / type_dist.sum()
    
    # Get base region shares
    base_shares = data_func_stocks_buildings.groupby('Region_lv2')['Value'].sum()
    base_region_shares = (base_shares / base_shares.sum()).to_dict()
    
    # Store all data: start with base year
    all_years_data = [base_stock]
    annual_summary = [{'Year': base_year, 'Stocks': total_stock_2023, 'Pop': pop_2023, 'Stocks_cap': total_stock_2023/pop_2023, 'NAS': 0}]
    
    # Track cumulative stock (starting with base stock)
    cumulative_stock = total_stock_2023
    
    for year in range(base_year + 1, target_year + 1):
        pop_current = pop_data.get(year, pop_data.iloc[-1])
        
        # Calculate target stock based on reduced per-capita target
        target_stock = pop_current * stocks_per_capita_target
        
        # Calculate how much new stock is needed (only if target exceeds cumulative)
        stocks_gap = max(0, target_stock - cumulative_stock)
        
        if stocks_gap > 0:
            # Determine region shares for this year
            if apply_future_region_shares and year in future_region_shares and future_region_shares[year]:
                region_shares = future_region_shares[year]
            else:
                region_shares = base_region_shares
            
            # Create new stock for this year
            sample_row = data_func_stocks_buildings.iloc[0]
            new_stock_list = []
            
            for bldg_type, proportion in type_dist.items():
                # Apply building-type-specific reduction to new construction as well
                reduction = new_stocks_reduction.get(bldg_type, 1.0)
                total_needed = stocks_gap * proportion * reduction
                
                if total_needed > 0.01:
                    for region, share in region_shares.items():
                        new_for_region = total_needed * share
                        
                        if new_for_region > 0.01:
                            new_stock_list.append({
                                'Parameter':  sample_row['Parameter'],
                                'Region_lv1': sample_row['Region_lv1'],
                                'Region_lv2': region,
                                'Type_lv1':   sample_row['Type_lv1'],
                                'Type_lv2':   bldg_type,
                                'Ownership':  sample_row['Ownership'],
                                'Occupancy':  sample_row.get('Occupancy', None),
                                'Year_from':  year,
                                'Year_to':    year,
                                'Unit':       sample_row['Unit'],
                                'Value':      new_for_region,
                                'Year':       year
                            })
            
            if new_stock_list:
                new_stock_df = pd.DataFrame(new_stock_list)
                all_years_data.append(new_stock_df)
                cumulative_stock += stocks_gap
        
        annual_summary.append({
            'Year':       year,
            'Stocks':     cumulative_stock,
            'Pop':        pop_current,
            'Stocks_cap': cumulative_stock / pop_current if pop_current > 0 else 0,
            'NAS':        stocks_gap
        })
        
        if year % 10 == 0 or year == target_year:
            print(f'{year}: Pop={pop_current:,.0f}, Stock={cumulative_stock:,.2f} m², '
                  f'Stock/cap={cumulative_stock/pop_current:.2f}, Additions={stocks_gap:,.2f}')
    
    full_series = pd.concat(all_years_data, ignore_index=True)
    return full_series, pd.DataFrame(annual_summary)

# Run projection
stocks_buildings_proj, annual_summary = project_building_stocks_simple(
    data_func_stocks_buildings=stocks_buildings_base,
    data_POP=data_POP,
    base_year=2023,
    target_year=2100,
    new_stocks_reduction=new_stocks_reduction,
    future_region_shares=future_region_shares,
    apply_future_region_shares=apply_future_region_shares)

stocks_buildings_proj.to_parquet('output/interim/stocks_buildings_proj.parquet', index=False)

#%%% Export MISO inputs

def prepare_stock_data_for_export(stocks_buildings_proj, stock_types=None):
    if stock_types is None:
        stock_types = stocks_buildings_proj['Type_lv2'].unique().tolist()
    
    all_pivot_dfs = []
    
    for stock_type in stock_types:
        df_type = stocks_buildings_proj[stocks_buildings_proj['Type_lv2'] == stock_type].copy()
        
        if df_type.empty:
            continue
        
        grouped = df_type.groupby(['Type_lv2', 'Year', 'Year_from', 'Year_to'])['Value'].sum().reset_index()
        
        pivot_df = grouped.pivot_table(index=['Type_lv2', 'Year_from', 'Year_to'], columns='Year', values='Value', fill_value=0).reset_index()
        
        pivot_df = pivot_df.rename(columns={'Year_from': 'Time'})
        pivot_df = pivot_df.drop(columns=['Year_to'])
        pivot_df.insert(0, 'MISO2_country', 'Austria')
        pivot_df.insert(1, 'Element', 'Element1')
        pivot_df.insert(2, 'End_use_sector', pivot_df['Type_lv2'])
        
        all_pivot_dfs.append(pivot_df)
    
    if not all_pivot_dfs:
        raise ValueError("No stock types were processed successfully!")
    
    combined_pivot_df = pd.concat(all_pivot_dfs, ignore_index=True)
    
    all_year_columns = [col for col in combined_pivot_df.columns 
                       if isinstance(col, int) and col <= 2100]
    year_2023 =        [col for col in all_year_columns if col == 2023]
    year_future =      [col for col in all_year_columns if col >= 2024]
    
    column_order_1 = ['MISO2_country', 'Element', 'End_use_sector', 'Time'] + year_2023
    initialization_df = combined_pivot_df[column_order_1].copy()
    initialization_df.columns = [str(col) if isinstance(col, int) else col 
                                 for col in initialization_df.columns]
    
    if year_future:
        function_df = combined_pivot_df.groupby(['MISO2_country', 'Element', 'End_use_sector'])[year_future].sum().reset_index()
        column_order_2 = ['MISO2_country', 'Element', 'End_use_sector'] + year_future
        function_df = function_df[column_order_2]
        function_df.columns = [str(col) if isinstance(col, int) else col 
                               for col in function_df.columns]
    else:
        function_df = pd.DataFrame(columns=['MISO2_country', 'Element', 'End_use_sector'])
    
    return initialization_df, function_df, combined_pivot_df, year_future, year_2023


def save_excel_with_sheets(df, output_path, source_label=None):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name='values', index=False)
        
        sources_df = df.copy()
        year_columns = [col for col in sources_df.columns 
                       if col not in ['MISO2_country', 'Element', 'End_use_sector', 'Material', 'Time']]
        
        for col in year_columns:
            if source_label and str(col) == '2023':
                sources_df[col] = source_label
            else:
                sources_df[col] = 'Modeled'
        
        sources_df.to_excel(writer, sheet_name='sources', index=False)
    
    wb = load_workbook(output_path)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    for sheet_name in ['values', 'sources']:
        ws = wb[sheet_name]
        for cell in ws[1]:
            cell.font =      Font(bold=True)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border =    thin_border
    
    if 'Cover' in wb.sheetnames:
        wb['Cover']['B12'] = datetime.now().strftime('%d.%m.%Y')
    
    wb.save(output_path)

initialization_df, function_df, combined_pivot_df, year_future, year_2023 = prepare_stock_data_for_export(stocks_buildings_proj=stocks_buildings_proj, stock_types=None)

mi_values_df = pd.read_excel(os.path.join(main_path, 'output/MISO_inputs/MISO2_MaterialIntensity_Functions_v1.xlsx'), sheet_name='values')

all_expanded_rows = []

for _, stock_row in initialization_df.iterrows():
    country = stock_row['MISO2_country']
    element = stock_row['Element']
    sector = stock_row['End_use_sector']
    construction_year = int(float(stock_row['Time']))
    stock_value_2023 = stock_row['2023']
    
    if stock_value_2023 == 0:
        continue
    
    for material in mi_values_df['Material'].unique():
        mi_row = mi_values_df[(mi_values_df['MISO2_country'] == country) & 
                               (mi_values_df['Element'] == element) &
                               (mi_values_df['End_use_sector'] == sector) & 
                               (mi_values_df['Material'] == material)]
        
        if mi_row.empty:
            continue
        
        if construction_year in mi_row.columns:
            mi_value = mi_row[construction_year].values[0]
        else:
            mi_value = 0
        
        if mi_value == 0:
            continue
        
        new_row = {
            'MISO2_country': country,
            'Element': element,
            'End_use_sector': sector,
            'Material': material,
            'Time': construction_year,
            '2023': stock_value_2023 * mi_value}
        
        all_expanded_rows.append(new_row)

if all_expanded_rows:
    stock_with_material = pd.DataFrame(all_expanded_rows)
else:
    stock_with_material = initialization_df.copy()
    stock_with_material.insert(3, 'Material', 'concrete')

# FILTER START - Remove this block to disable filtering
filter_end_use =  'R_SFH'
filter_material = 'iron_steel'
stock_with_material = stock_with_material[(stock_with_material['End_use_sector'] == filter_end_use) & (stock_with_material['Material'] == filter_material)]
initialization_df = initialization_df[initialization_df['End_use_sector'] == filter_end_use]
# FILTER END

save_excel_with_sheets(stock_with_material, 'output/MISO_inputs/MISO2_Stock_Initialization_v1.xlsx', 'Statistik Austria Housing Register')
save_excel_with_sheets(initialization_df, 'output/MISO_inputs/MISO2_Function_Initialization_v1.xlsx', 'Statistik Austria Housing Register')

pivot_df_future = combined_pivot_df.copy()

if 'Type_lv2' in pivot_df_future.columns:
    pivot_df_future = pivot_df_future.drop(columns=['Type_lv2'])

grouped_future = pivot_df_future.groupby(['MISO2_country', 'Element', 'End_use_sector'])[year_future].sum().reset_index()

# FILTER START - Remove this block to disable filtering
grouped_future = grouped_future[grouped_future['End_use_sector'] == filter_end_use]
# FILTER END

column_order_2 = ['MISO2_country', 'Element', 'End_use_sector'] + year_future
grouped_future = grouped_future[column_order_2]
grouped_future.columns = [str(col) if isinstance(col, int) else col for col in grouped_future.columns]

save_excel_with_sheets(grouped_future, 'output/MISO_inputs/MISO2_Function_Stock_v1.xlsx')

#%%% Projection overview

print('\n' + '='*70)
print('Building stocks summary')
print('='*70)
print(annual_summary[['Year', 'Stocks', 'Pop', 'Stocks_cap', 'NAS']].to_string(
    index=False,
    formatters={
        'Year':       lambda x: f'{int(x):>6}',
        'Stocks':     lambda x: f'{x:>15.2f}',
        'Pop':        lambda x: f'{int(x):>15.0f}',
        'Stocks_cap': lambda x: f'{x:>15.2f}',
        'NAS':        lambda x: f'{x:>15.2f}'
    }))

#%%% Annual stock spatial distribution 

stocks_year = stocks_buildings_proj[stocks_buildings_proj['Year'] == 2100].copy()
summary_df = stocks_year.groupby(['Type_lv2', 'Region_lv2'])['Value'].sum().reset_index()
type_totals = summary_df.groupby('Type_lv2')['Value'].sum().reset_index()
type_totals.columns = ['Type_lv2', 'Total_Value']

summary_df = summary_df.merge(type_totals, on='Type_lv2')
summary_df['Share'] = summary_df['Value'] / summary_df['Total_Value']

pivot_share = summary_df.pivot(index='Type_lv2', columns='Region_lv2', values='Share').fillna(0)

fig, ax = plt.subplots(figsize=(14, 8))

pivot_share.plot(kind='bar', stacked=True, ax=ax, colormap='viridis', edgecolor='black')

ax.set_title('Building stock distribution by building type and region', fontsize=14, fontweight='bold')
ax.set_xlabel('Building type', fontsize=12)
ax.set_ylabel('Share of total floor area', fontsize=12)
ax.set_ylim(0, 1)
ax.legend(title='Region', bbox_to_anchor=(1.05, 1), loc='upper left')
ax.tick_params(axis='x', rotation=45)
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.show()

#%%%% Building sector|Heating systems

# Stock projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase efficiency

# Calculate final energy demand of building stock: floor space (m2) * age-cohort and type-specific Final energy demand for heating [kWh/m²/a] (renovated and unrenovated)
# Calculate final energy input of building stock, heizgradtagbereinigt: Above demand * shares of different heating types (Kranzl: gas, wood chips, solar, etc., %) / heating day ratio (CeAT)
# Calculate installed capacity (GW) per heating type by dividing above final energy input by heating hours, then apply multiplication factor (Kranzl)

#%%%%% Building sector|Heating systems|Operation

# Apply fuel usage of heating systems for operation based on CeAT data

#%%%% Building sector|Cooling systems

# Analogous approach to heating systems

#%%%%% Building sector|Cooling systems|Operation

# Analogous approach to heating systems

#%%%% Building sector|Household appliances

# Product projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase sharing (reduction))

#%%%%% Building sector|Household appliances|Operation

# Apply operational energy use of household appliances (look up factors)

#%%% Transport sector
#%%%% Transport sector|Mobility

# Mobility projections (pkm/tkm)
# Convert to vkm using occupancy rates
# Implement 2060 modal split that can be set in config
# Implement different options: a) trend continuation, b) mobility reduction, c) shift to active/public

#%%%% Transport sector|Vehicles

# Stock projection
# Implement different options: a) project to 2060 using mobility (above) as proxies, b) set level; c) increase sharing (reduction))

#%%%%% Transport sector|Vehicles|Operation

# Apply fuel consumption (l fuel/vkm) to traffic scenarios based on Lederer et al. projections and CeAT factors

#%%%% Transport sector|Infrastructure

# Take transport infrastructure from GLOMIS and couple with vkm


#%%% Projection overview

print('\n' + '='*70)
print('Building stocks summary')
print('='*70)
print(annual_summary[['Year', 'Stocks', 'Pop', 'Stocks_cap', 'NAS']].to_string(
    index=False,
    formatters={
        'Year':       lambda x: f'{int(x):>6}',
        'Stocks':     lambda x: f'{x:>15.2f}',
        'Pop':        lambda x: f'{int(x):>15.0f}',
        'Stocks_cap': lambda x: f'{x:>15.2f}',
        'NAS':        lambda x: f'{x:>15.2f}'
    }))

#%%% Annual stock spatial distribution 

stocks_year = stocks_buildings_proj[stocks_buildings_proj['Year'] == 2100].copy()
summary_df = stocks_year.groupby(['Type_lv2', 'Region_lv2'])['Value'].sum().reset_index()
type_totals = summary_df.groupby('Type_lv2')['Value'].sum().reset_index()
type_totals.columns = ['Type_lv2', 'Total_Value']

summary_df = summary_df.merge(type_totals, on='Type_lv2')
summary_df['Share'] = summary_df['Value'] / summary_df['Total_Value']

pivot_share = summary_df.pivot(index='Type_lv2', columns='Region_lv2', values='Share').fillna(0)

fig, ax = plt.subplots(figsize=(14, 8))

pivot_share.plot(kind='bar', stacked=True, ax=ax, colormap='viridis', edgecolor='black')

ax.set_title('Building stock distribution by building type and region', fontsize=14, fontweight='bold')
ax.set_xlabel('Building type', fontsize=12)
ax.set_ylabel('Share of total floor area', fontsize=12)
ax.set_ylim(0, 1)
ax.legend(title='Region', bbox_to_anchor=(1.05, 1), loc='upper left')
ax.tick_params(axis='x', rotation=45)
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.show()

#%%%% Building sector|Heating systems

# Stock projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase efficiency

# Calculate final energy demand of building stock: floor space (m2) * age-cohort and type-specific Final energy demand for heating [kWh/m²/a] (renovated and unrenovated)
# Calculate final energy input of building stock, heizgradtagbereinigt: Above demand * shares of different heating types (Kranzl: gas, wood chips, solar, etc., %) / heating day ratio (CeAT)
# Calculate installed capacity (GW) per heating type by dividing above final energy input by heating hours, then apply multiplication factor (Kranzl)

#%%%%% Building sector|Heating systems|Operation

# Apply fuel usage of heating systems for operation based on CeAT data

#%%%% Building sector|Cooling systems

# Analogous approach to heating systems

#%%%%% Building sector|Cooling systems|Operation

# Analogous approach to heating systems

#%%%% Building sector|Household appliances

# Product projections
# Implement different options: a) project to 2060 using proxies (reference scenario), b) set level; c) increase sharing (reduction))

#%%%%% Building sector|Household appliances|Operation

# Apply operational energy use of household appliances (look up factors)

#%%% Transport sector
#%%%% Transport sector|Mobility

# Mobility projections (pkm/tkm)
# Convert to vkm using occupancy rates
# Implement 2060 modal split that can be set in config
# Implement different options: a) trend continuation, b) mobility reduction, c) shift to active/public

#%%%% Transport sector|Vehicles

# Stock projection
# Implement different options: a) project to 2060 using mobility (above) as proxies, b) set level; c) increase sharing (reduction))

#%%%%% Transport sector|Vehicles|Operation

# Apply fuel consumption (l fuel/vkm) to traffic scenarios based on Lederer et al. projections and CeAT factors

#%%%% Transport sector|Infrastructure

# Take transport infrastructure from GLOMIS and couple with vkm








