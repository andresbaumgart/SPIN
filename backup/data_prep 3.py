#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Model:   Function scenarios for Stock-driven MISO2
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Prepare base year data for scenarios
'''

#%% Notes

# Derive penetration rates of appliances per households from Statistik Austria or other sources
# For vehicles, quantify these in MISO2, as 

######################################################################################################################################################
######################################################################################################################################################
#%% General
#%%% Packages

import os
import warnings
import numpy as np
import pandas as pd

# Suppress warnings
warnings.filterwarnings('ignore')

#%%% Universal settings

main_path = os.getcwd()

def read_excel(file_path, sheet_name=None):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    cols = df.loc[:, "Parameter":"Value"].columns.tolist()
    return df[cols]

#%%% Data import
#%%%% Data import|Statistik Austria housing data

# Load Statistik Austria data

def read_statcube_csv(file_path):
    encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']

    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding, skiprows=6, low_memory=False)
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
            
            if 'Annotations' in df.columns:
                df = df.drop('Annotations', axis=1)
            
            if 'Year' in df.columns:
                df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
                df = df[df['Year'].notna()]
                df['Year'] = df['Year'].astype(int)
            
            if 'Number' in df.columns:
                df['Number'] = pd.to_numeric(df['Number'], errors='coerce')
            
            return df
        except:
            continue
    
    return pd.DataFrame()

housing_path = os.path.join(main_path, 'input', 'StatCube', 'Buildings')

df1 = read_statcube_csv(os.path.join(housing_path, 'table_2026-07-20_11-14-41.csv'))
df2 = read_statcube_csv(os.path.join(housing_path, 'table_2026-07-20_11-26-41.csv'))
df3 = read_statcube_csv(os.path.join(housing_path, 'table_2026-07-20_11-30-58.csv'))

if not df1.empty and len(df1.columns) > 1:
    df1.rename(columns={df1.columns[1]: 'Urban_rural'}, inplace=True)
if not df2.empty and len(df2.columns) > 1:
    df2.rename(columns={df2.columns[1]: 'Urban_rural'}, inplace=True)
if not df3.empty and len(df3.columns) > 1:
    df3.rename(columns={df3.columns[1]: 'Region'}, inplace=True)

df_combined = pd.concat([df1, df2], ignore_index=True)

if not df_combined.empty:
    df_combined.insert(1, 'Region', 'Austria')

vienna_data = df3[df3['Region'] == 'Vienna'].copy()

if not vienna_data.empty:
    vienna_data.insert(2, 'Urban_rural', 'Urban centre (large)')

# Deduct Vienna (all "Urban centre (large)") from Austria total

if not df_combined.empty and not vienna_data.empty:
    austria_urban_centre = df_combined[df_combined['Urban_rural'] == 'Urban centre (large)'].copy()
    austria_rest = df_combined[df_combined['Urban_rural'] != 'Urban centre (large)'].copy()
    match_cols = [col for col in austria_urban_centre.columns if col not in ['Year', 'Region', 'Urban_rural', 'Number']]
    merged = austria_urban_centre.merge(vienna_data, on=match_cols, how='left', suffixes=('_austria', '_vienna'))
    merged['Number'] = merged['Number_austria'] - merged['Number_vienna'].fillna(0)

    cols_to_keep = ['Year_austria', 'Region_austria', 'Urban_rural_austria'] + match_cols + ['Number']
    austria_urban_centre_deducted = merged[cols_to_keep].copy()
    austria_urban_centre_deducted.rename(columns={'Year_austria': 'Year', 'Region_austria': 'Region', 'Urban_rural_austria': 'Urban_rural'}, inplace=True)
    austria_final = pd.concat([austria_urban_centre_deducted, austria_rest], ignore_index=True)
    
    # Rename 'Austria' to 'Rest of Austria' in austria_final
    austria_final['Region'] = 'Rest of Austria'
    
    complete_austria = pd.concat([austria_final, vienna_data], ignore_index=True)

    non_urban_combinations = austria_final[
        austria_final['Urban_rural'] != 'Urban centre (large)'
    ][['Urban_rural'] + match_cols].drop_duplicates()

    vienna_empty_rows = []
    for _, combo in non_urban_combinations.iterrows():
        new_row = {'Year': 2024, 'Region': 'Vienna', 'Number': 0}
        for col in ['Urban_rural'] + match_cols:
            new_row[col] = combo[col]
        vienna_empty_rows.append(new_row)

    vienna_empty_df = pd.DataFrame(vienna_empty_rows)
    complete_austria_final = pd.concat([complete_austria, vienna_empty_df], ignore_index=True)

else:
    complete_austria_final = pd.DataFrame()

# Finalize base year data

data_func_stocks_buildings = complete_austria_final.copy()

data_func_stocks_buildings.rename(columns={
    'Region':                                           'Region_lv1',
    'Urban_rural':                                      'Region_lv2',
    'Type of building (predominant use)':               'Type_lv2',
    'Period of construction (Level +1)':                'Cohort',
    'Type of ownership':                                'Ownership',
    'Occupancy status of the dwelling':                 'Occupancy',
    'Useful floor space in square meters per occupant': 'Density',
    'Number':                                           'Value'}, inplace=True)

data_func_stocks_buildings.insert(0, 'Parameter', 'Function')
data_func_stocks_buildings.insert(0, 'Type_lv1', 'Buildings')

data_func_stocks_buildings['Value'] = data_func_stocks_buildings['Value'].fillna(0).astype(int)

# Evenly distribute construction year across age cohorts

cohort_map = {
    '2016 or later': (2016, 2024), # assuming current year 2024
    '2011 to 2015':  (2011, 2015),
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
    if row['Value'] > 0:
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
data_func_stocks_buildings.insert(data_func_stocks_buildings.columns.get_loc('Year') + 1, 'Unit', 'm2 UFA')

data_func_stocks_buildings = data_func_stocks_buildings[["Parameter", "Region_lv1", "Region_lv2", "Type_lv1", "Type_lv2", "Ownership", "Occupancy", "Cohort", "Density", "Year_from", "Year_to",  "Year", "Unit", "Value"]]

data_func_stocks_buildings['Source'] = "Statistik Austria housing census"
data_func_stocks_buildings['DOI'] = "http://statcube.at/statcube/opendatabase?id=derzgwz_gwz_zr_geb"
data_func_stocks_buildings['Notes'] = ""

data_func_stocks_buildings.to_excel(os.path.join(main_path, 'output/interim/data_func_stocks_buildings.xlsx'), index=False)

#%%%% Data import|Transport sector

# data_vehicle_fleet = read_excel(os.path.join(main_path, 'input/data_vehicle_fleet.xlsx'), sheet_name='input')

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

#  Data corrections

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
    'NR_hotels':    1.0,}

stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * stocks_buildings_base['Type_lv2'].map(ufa_to_nfa) # NFA = net floor area
stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * 1 # Upscaling factor if needed 

print("Total floor area per year:\n", stocks_buildings_base['Value'].sum())
stocks_buildings_base.to_parquet("output/interim/stocks_buildings_base.parquet", index=False)

#%%%% Building sector|Household appliances|Functions

def derive_households_and_appliances(stocks_buildings_base):

    # Household size by building type

    df_hh = pd.read_excel(os.path.join(main_path, 'input', 'StatCube', 'Buildings', 'table_2026-08-12_13-28-50.xlsx'), sheet_name='input', header=None)

    household_size_by_type = {
        'R_SFH':      float(df_hh[df_hh.iloc[:,0] == 'R_SFH'].iloc[0,1]),
        'R_MFH':      float(df_hh[df_hh.iloc[:,0] == 'R_MFH'].iloc[0,1]),
        'R_APB':      float(df_hh[df_hh.iloc[:,0] == 'R_APB'].iloc[0,1]),
        'R_IHH':      float(df_hh[df_hh.iloc[:,0] == 'R_IHH'].iloc[0,1]),
        'NR_public':  0,
        'NR_indust':  0,
        'NR_trafcom': 0,
        'NR_retail':  0,
        'NR_office':  0,
        'NR_hotels':  0}
    
    # Appliance penetration rates (% of households with each appliance)
    
    df_app = pd.read_excel(os.path.join(main_path, 'input', 'data_appliance_penetration_rates.xlsx'), sheet_name='input')
    
    appliances_per_hh = dict(zip(df_app['Appliance'], df_app['Value']))
    
    def get_density_midpoint(density_str):

        if density_str == 'Not applicable':
            return None
        
        import re
        numbers = re.findall(r'[\d.]+', density_str)
        
        if len(numbers) == 0:
            return None
        elif len(numbers) == 1:
            if 'Under' in density_str:
                return float(numbers[0]) * 0.80 # Assumed average 10 m2/cap or under
            elif 'and over' in density_str:
                return float(numbers[0]) * 1.20 # Assumed average 80 m2/cap or over
            else:
                return float(numbers[0])
        else:
            return (float(numbers[0]) + float(numbers[1])) / 2
    
    all_appliance_rows = []
    all_household_rows = []
    
    for year in stocks_buildings_base['Year'].unique():
        year_data = stocks_buildings_base[stocks_buildings_base['Year'] == year]
        
        for btype, hh_size in household_size_by_type.items():
            if hh_size == 0:  # Skip non-residential
                continue
            
            btype_data = year_data[year_data['Type_lv2'] == btype]
            if btype_data.empty:
                continue
            
            for region in btype_data['Region_lv2'].unique():
                region_data = btype_data[btype_data['Region_lv2'] == region]
                if region_data.empty:
                    continue
                
                for density_class in region_data['Density'].unique():
                    if density_class == 'Not applicable':
                        continue
                    
                    density_data = region_data[region_data['Density'] == density_class]
                    total_ufa = density_data['Value'].sum()
                    
                    if total_ufa == 0:
                        continue
                    
                    # Get density midpoint
                    density_mid = get_density_midpoint(density_class)
                    if density_mid is None or density_mid <= 0:
                        continue
                    
                    # Calculate occupants and households
                    occupants = total_ufa / density_mid
                    households = occupants / hh_size
                    
                    # Store household info
                    all_household_rows.append({
                        'Year':                  year,
                        'Region_lv2':            region,
                        'Building_Type':         btype,
                        'Density_Class':         density_class,
                        'Total_UFA_m2':          total_ufa,
                        'Density_m2_per_person': density_mid,
                        'Occupants':             occupants,
                        'Household_Size':        hh_size,
                        'Households':            households})
                    
                    # Calculate appliances
                    for appliance, penetration in appliances_per_hh.items():
                        num_appliances = households * penetration
                        if num_appliances > 0.1:
                            all_appliance_rows.append({
                                'Parameter':     'Function',
                                'Type_lv1':      'Appliances',
                                'Type_lv2':      appliance,
                                'Building_Type': btype,
                                'Density_Class': density_class,
                                'Region_lv1':    'Austria',
                                'Region_lv2':    region,
                                'Year_from':     year,
                                'Year_to':       year,
                                'Year':          year,
                                'Unit':          'Units',
                                'Value':         num_appliances,
                                'Source':        'Derived from building stock',
                                'Notes':         f'Based on {households:.0f} households'})
    
    appliance_df = pd.DataFrame(all_appliance_rows)
    household_df = pd.DataFrame(all_household_rows)
    
    if not appliance_df.empty:
        print("\nAppliances by type (n):")
        print(appliance_df.groupby('Type_lv2')['Value'].sum().sort_values(ascending=False))
    
    return appliance_df, household_df

appliance_base, household_base = derive_households_and_appliances(stocks_buildings_base)
    
#%%% Transport sector
#%%%% Transport sector|Vehicles|Functions

# Add additional layer: vehicle components (data from TecEUS)

#%%%% Transport sector|Infrastructure|Functions

# Take transport infrastructure from GLOMIS and couple with vkm (derive from Lederer et al. pkm/tkm via occupation rates)





