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

data_prod_stocks_buildings = read_excel(os.path.join(main_path, 'input/data_prod_stocks_buildings.xlsx'), sheet_name='MISO2_Product')

#%%%% Data import|Transport sector

data_prod_stocks_vehicles = read_excel(os.path.join(main_path, 'input/data_prod_stocks_vehicles.xlsx'), sheet_name='MISO2_Product')

#%%%% Data import|General

for df in [data_prod_stocks_buildings, 
           data_prod_stocks_vehicles]:
    df['Year_from'] = df['Year_from'].astype(float)
    df['Year_to']   = df['Year_to'].astype(float)

######################################################################################################################################################
######################################################################################################################################################
#%% Data preparation
#%%% Building sector
#%%%% Building sector|Buildings|Products

rename_types = {
    'Residential buildings with one conventional dwelling':            'SFH',
    'Residential buildings with two conventional dwellings':           'MFH',
    'Residential buildings with three or more conventional dwellings': 'APB',
    'Buildings for institutional households':                          'APB',
    'Non-residential buildings':                                       'NRS'}

rename_ownership = {
    'Private persons':                     'Private',
    'Public bodies':                       'Public', 
    'Limited profit housing associations': 'Limited-profit'}

data_prod_stocks_buildings['Type_lv2'] =  data_prod_stocks_buildings['Type_lv2'].replace(rename_types)
data_prod_stocks_buildings['Ownership'] = data_prod_stocks_buildings['Ownership'].replace(rename_ownership)

group_cols = data_prod_stocks_buildings.loc[:, "Parameter":"Unit"].columns.tolist()
stocks_buildings_base = (data_prod_stocks_buildings.groupby(group_cols, as_index=False).agg({'Value': 'sum'}))

stocks_buildings_base.loc[stocks_buildings_base['Year_from'] == 0, 'Year_from'] = 1880

ufa_to_nfa = { # UFA > NFA conversion (identify sources and calibrate)
    'SFH': 1.10,
    'MFH': 1.10,
    'APB': 1.15,
    'NRS': 1.20}

stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * stocks_buildings_base['Type_lv2'].map(ufa_to_nfa) # NFA = net floor area
stocks_buildings_base['Unit'] = "m2 NFA"
stocks_buildings_base['Value'] = stocks_buildings_base['Value'] * 1.3 # Upscaling factor to account for unreported stock

print("Total floor area per year:\n", stocks_buildings_base['Value'].sum())
stocks_buildings_base.to_parquet("output/interim/stocks_buildings_base.parquet", index=False)

#%%%% Building sector|Household appliances|Products

# Define number of household appliances (fridges, coolers, washing machines, dishwashers) based on households (use population as proxy, as we do not have household data included herein)
# Compile MI factors first (focus on 4 critical materials)

#%%% Transport sector
#%%%% Transport sector|Vehicles|Products

# Add additional layer: vehicle components (data from TecEUS)

#%%%% Transport sector|Infrastructure|Products

# Take transport infrastructure from GLOMIS and couple with vkm (derive from Lederer et al. pkm/tkm via occupation rates)





