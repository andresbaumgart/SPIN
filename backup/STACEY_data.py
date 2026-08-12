# !/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Prepare base year data for scenarios
'''

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import numpy as np
import pandas as pd

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    cols = df.loc[:, "Parameter":"Value"].columns.tolist()
    return df[cols]

#%%% Data import
#%%%% Data import|Building sector

# data_func_stocks_buildings = read_excel(os.path.join(main_path, 'input/data_func_stocks_buildings.xlsx'), sheet_name='MISO2_Product')

data_func_vienna = pd.read_csv(os.path.join(main_path, 'input/raw_data/StatAT_buildings/table_2026-03-31_11-32-01.csv'), skiprows=5, encoding='cp1252', quotechar='"', usecols=range(8))
data_func_rest = pd.read_csv(os.path.join(main_path,   'input/raw_data/StatAT_buildings/table_2026-03-31_11-27-21.csv'), skiprows=5, encoding='cp1252', quotechar='"', usecols=range(8))

new_cols = ["Region_lv2", "Type_lv2", "Cohort", "Ownership", "Occupancy", "Unit", "Year", "Value"]

data_func_vienna.columns = new_cols
data_func_rest.columns = new_cols

data_func_vienna['Unit'] = "m2 UFA"
data_func_rest['Unit'] = "m2 UFA"

data_func_vienna.insert(0, 'Region_lv1', "Vienna")
data_func_rest.insert(0,   'Region_lv1', "Rest of Austria")

data_func_vienna.insert(2, 'Type_lv1',   "Buildings")
data_func_rest.insert(2,   'Type_lv1',   "Buildings")

data_func_vienna.insert(0, 'Parameter',  "Function")
data_func_rest.insert(0,   'Parameter',  "Function")

data_func_vienna['Region_lv2'] = 'Urban'

data_func_vienna['Value'] = pd.to_numeric(data_func_vienna['Value'], errors='coerce')
data_func_rest['Value'] =   pd.to_numeric(data_func_rest['Value'],   errors='coerce')

# Vienna = 100% urban but has to be deducted from remaining Austria (work-around due to Statistik Austria download limitations on number of dimensions)

urban_rest = data_func_rest[data_func_rest['Region_lv2'] == 'Urban'].copy()
rural_rest = data_func_rest[data_func_rest['Region_lv2'] != 'Urban'].copy()

cols_to_match = ['Type_lv1', 'Type_lv2', 'Cohort', 'Ownership', 'Occupancy', 'Unit', 'Year']

merged = pd.merge(urban_rest, data_func_vienna, on=cols_to_match, suffixes=('_rest', '_vienna'))
merged['Value_rest'] = merged['Value_rest'] - merged['Value_vienna']

urban_rest_minus_vienna = merged[cols_to_match + ['Value_rest']].rename(columns={'Value_rest':'Value'})
urban_rest_minus_vienna.insert(0, 'Parameter',  'Function')
urban_rest_minus_vienna.insert(0, 'Region_lv1', 'Rest of Austria')
urban_rest_minus_vienna.insert(1, 'Region_lv2', 'Urban')

rest_cleaned = pd.concat([urban_rest_minus_vienna, rural_rest], ignore_index=True)
data_func_stocks_buildings = pd.concat([data_func_vienna, rest_cleaned], ignore_index=True)
data_func_stocks_buildings['Value'] = data_func_stocks_buildings['Value'].fillna(0).astype(int)
data_func_stocks_buildings = data_func_stocks_buildings.dropna(subset=['Year'])

# Evenly distribute construction year across age cohorts

cohort_map = {
    '2011 or later': (2011, 2023), # assuming current year 2023
    '2001 to 2010':  (2001, 2010),
    '1991 to 2000':  (1991, 2000),
    '1981 to 1990':  (1981, 1990),
    '1971 to 1980':  (1971, 1980),
    '1961 to 1970':  (1961, 1970),
    '1945 to 1960':  (1945, 1960),
    '1919 to 1944':  (1919, 1944),
    'Before 1919':   (1900, 1918)} # assuming constructed between 1900 and 1918

rows = []

for _, row in data_func_stocks_buildings.iterrows():
    start, end = cohort_map[row['Cohort']]
    years = list(range(start, end + 1))
    value_per_year = row['Value'] / len(years)
    for y in years:
        new_row = row.copy()
        new_row['Year_from'] = y
        new_row['Year_to'] = y
        new_row['Value'] = value_per_year
        rows.append(new_row)

data_func_stocks_buildings = pd.DataFrame(rows)
data_func_stocks_buildings['Value'] = data_func_stocks_buildings['Value'].round().astype(int)

data_func_stocks_buildings = data_func_stocks_buildings[["Parameter", "Region_lv1", "Region_lv2", "Type_lv1", "Type_lv2", "Ownership", "Occupancy", "Cohort", "Year_from", "Year_to",  "Year", "Unit", "Value"]]

# Save

data_func_stocks_buildings['Source'] = "Statistik Austria housing census"
data_func_stocks_buildings['DOI'] = "http://statcube.at/statcube/opendatabase?id=derzgwz_gwz_zr_geb"
data_func_stocks_buildings['Notes'] = ""

data_func_stocks_buildings.to_excel(os.path.join(main_path, 'input/data_func_stocks_buildings.xlsx'), index=False)


#%%%% Data import|Transport sector

data_func_stocks_vehicles = read_excel(os.path.join(main_path, 'input/data_func_stocks_vehicles.xlsx'), sheet_name='MISO2_Product')

#%%%% Data import|General

for df in [data_func_stocks_buildings]:
    df['Year_from'] = df['Year_from'].astype(float)
    df['Year_to']   = df['Year_to'].astype(float)

######################################################################################################################################################
######################################################################################################################################################
#%% Data processing
#%%% Building sector
#%%%% Building sector|Buildings|Functions

rename_types = {
    'Residential buildings with one conventional dwelling':             'R_SFH',
    'Residential buildings with two conventional dwellings':            'R_MFH',
    'Residential buildings with three or more conventional dwellings':  'R_APB',
    'Buildings for institutional households':                           'R_IHH',
    'Buildings for public entertainment, education and health care':    'NR_public',
    'Industrial buildings and warehouses':                              'NR_indust', 
    'Traffic and communication buildings':                              'NR_trafcom', 
    'Wholesale and retail trade buildings':                             'NR_retail', 
    'Office buildings':                                                 'NR_office', 
    'Hotels and similar buildings':                                     'NR_hotels'}

rename_ownership = {
    'Private persons':                     'Private',
    'Public bodies':                       'Public', 
    'Limited profit housing associations': 'Limited-profit'}

data_func_stocks_buildings['Type_lv2'] =  data_func_stocks_buildings['Type_lv2'].replace(rename_types)
data_func_stocks_buildings['Ownership'] = data_func_stocks_buildings['Ownership'].replace(rename_ownership)

group_cols = data_func_stocks_buildings.loc[:, "Parameter":"Unit"].columns.tolist()
stocks_buildings_base = (data_func_stocks_buildings.groupby(group_cols, as_index=False).agg({'Value': 'sum'}))

ufa_to_nfa = { # UFA > NFA conversion, if required
    'R_SFH':        1.0,
    'R_MFH':        1.0,
    'R_APB':        1.0,
    'R_IHH':        1.0,
    'NR_public':    1.0,
    'NR_indust':    1.0,
    'NR_trafcom':   1.0,
    'NR_retail':    1.0,
    'NR_office':    1.0,
    'NR_hotels':    1.0,
    }

stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * stocks_buildings_base['Type_lv2'].map(ufa_to_nfa) # NFA = net floor area
stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * 1 # Upscaling factor if needed

print("Total floor area per year:\n", stocks_buildings_base['Value'].sum())
stocks_buildings_base.to_parquet("output/interim/stocks_buildings_base.parquet", index=False)

#%%%% Building sector|Household appliances|Functions

# Define number of household appliances (fridges, coolers, washing machines, dishwashers) based on households (use population as proxy, as we do not have household data included herein)
# Compile MI factors first (focus on 4 critical materials)

#%%% Transport sector
#%%%% Transport sector|Vehicles|Functions

# Add additional layer: vehicle components (data from TecEUS)

#%%%% Transport sector|Infrastructure|Functions

# Take transport infrastructure from GLOMIS and couple with vkm (derive from Lederer et al. pkm/tkm via occupation rates)





