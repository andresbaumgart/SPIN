# # !/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# Created on Tue Jul  14 09:00:00 2025
# Model: STock-driven Austrian Circular EconomY (STACEY)
# @author: andrebaumgart
# """

# #%% Notes

# # Do we calculate inflows and outflows from STACEY stock projections in MISO2 or calculate future stocks from inflows and outflows in STACEY?
# # If the former: project building stocks by coupling with population; project heating systems by coupling with building stock; project household appliances by coupling with population/building stock
# # Use GLOMIS stock projections for mobility infrastructure
# # Couple vehicle stock development with vkm/tkm forecasts
    
# #%% Packages

# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt

# #%% Data import

# cols = ['Parameter', 'MISO2_country', 'Category_lv1', 'Category_lv2', 'Category_lv3', 'Year_from', 'Year_to', 'Unit', 'Value']

# def read_excel(file_path):
#     return pd.read_excel(file_path, usecols=cols)

# #%%% Data import|General

# data_GDP_constr             = read_excel("input/data_GDP_constr.xlsx")
# data_POP                    = read_excel("input/data_POP.xlsx")

# #%%% Data import|Building sector

# data_prod_stock_buildings   = read_excel("input/data_prod_stock_buildings.xlsx")
# data_prod_flow_buildings    = read_excel("input/data_prod_flow_buildings.xlsx")
# data_MI_buildings           = read_excel("input/data_MI_buildings.xlsx")
# data_MI_buildings_renov     = read_excel("input/data_MI_buildings_renov.xlsx")
# data_MI_heating_systems     = read_excel("input/data_MI_heating_systems.xlsx")
# data_rate_renov             = read_excel("input/data_rate_buildings_renov.xlsx")
# data_rate_demol             = read_excel("input/data_rate_buildings_demol.xlsx")

# #%%% Data import|Transport sector

# #%%% Data import|Electricity sector

# #%% Data processing
# #%%% Building sector
# #%%%% Buildings
# #%%%%% Buildings|Stocks
# # Base year stocks

# data_MI_buildings['Year_from'] = data_MI_buildings['Year_from'].astype(float)
# data_MI_buildings['Year_to'] = data_MI_buildings['Year_to'].astype(float)

# data_prod_stock_buildings['Year_from'] = data_prod_stock_buildings['Year_from'].astype(float)
# data_prod_stock_buildings['Year_to'] = data_prod_stock_buildings['Year_to'].astype(float)

# data_MI_buildings_exp = data_MI_buildings.copy()
# data_MI_buildings_exp = data_MI_buildings_exp.assign(Category_lv2=data_MI_buildings_exp['Category_lv2'].replace({'SFH/MFH':'SFH'}))
# data_MI_buildings_exp = pd.concat([data_MI_buildings_exp, data_MI_buildings_exp[data_MI_buildings_exp['Category_lv2']=='SFH'].assign(Category_lv2='MFH')], ignore_index=True)

# age_cohort_map = {
#     (0,    1918): (0,    1918),
#     (1919, 1944): (1919, 1944),
#     (1945, 1960): (1945, 1970),
#     (1961, 1970): (1945, 1970),
#     (1971, 1980): (1971, 1980),
#     (1981, 1990): (1981, 1990),
#     (1991, 2000): (1991, 2000),
#     (2001, 2010): (2001, 2100),
#     (2011, 2100): (2001, 2100)}

# def map_year(row):
#     return age_cohort_map.get((row['Year_from'], row['Year_to']), (np.nan, np.nan))

# data_prod_stock_buildings_mi = data_prod_stock_buildings.copy()
# data_prod_stock_buildings_mi[['MI_Year_from','MI_Year_to']] = pd.DataFrame(data_prod_stock_buildings_mi.apply(map_year, axis=1).tolist(), index=data_prod_stock_buildings_mi.index)

# stock_buildings = data_prod_stock_buildings_mi.merge(
#     data_MI_buildings_exp[['Category_lv2','Year_from','Year_to','Category_lv3','Value']],
#     left_on=['Category_lv2','MI_Year_from','MI_Year_to'],
#     right_on=['Category_lv2','Year_from','Year_to'],
#     suffixes=('','_mi')).rename(columns={'Value': 'FU_m2'})

# stock_buildings['Value'] = stock_buildings['FU_m2'] * stock_buildings['Value_mi']
# stock_buildings['Category_lv3'] = stock_buildings['Category_lv3_mi']
# stock_buildings['Unit'] = "metric tons"

# stock_buildings = stock_buildings[['Parameter', 'MISO2_country', 'Category_lv1', 'Category_lv2', 'Category_lv3', 'Year_from', 'Year_to', 'Unit', 'Value', 'FU_m2']]
# stock_buildings_total = stock_buildings.groupby(['Category_lv2','Category_lv3'], as_index=False)['Value'].sum()

# #%%%%% Buildings|Inflows
# #%%%%%% Buildings|Inflows|Construction

# data_prod_flow_buildings['Year_from'] = pd.to_numeric(data_prod_flow_buildings['Year_from'])
# data_GDP_constr['Year_from'] = pd.to_numeric(data_GDP_constr['Year_from'])

# gdp_growth = {}
# for country in data_GDP_constr['MISO2_country'].unique():
#     gdp_country = data_GDP_constr[data_GDP_constr['MISO2_country'] == country].set_index('Year_from')['Value'].sort_index()
#     gdp_2024 = gdp_country.loc[2022]
#     for year in range(2022, 2101):
#         gdp_growth[(country, year)] = gdp_country.loc[year] / gdp_2024

# base_year = 2022
# base_rows = data_prod_flow_buildings[data_prod_flow_buildings['Year_from'] == base_year]

# proj_rows = []
# for idx, row in base_rows.iterrows():
#     country =      row['MISO2_country']
#     category_lv2 = row['Category_lv2']
#     base_value =   row['Value']
    
#     for year in range(base_year + 1, 2101):  
#         projected_value = base_value * gdp_growth[(country, year)]
#         proj_rows.append({
#             'Parameter':     row['Parameter'],
#             'MISO2_country': country,
#             'Category_lv1':  row['Category_lv1'],
#             'Category_lv2':  category_lv2,
#             'Category_lv3':  row['Category_lv3'],
#             'Year_from':     year,
#             'Year_to':       year,
#             'Unit':          row['Unit'],
#             'Value':         projected_value})

# data_proj = pd.DataFrame(proj_rows)
# historic_rows = data_prod_flow_buildings[data_prod_flow_buildings['Unit'] == 'm2 NFA/yr']
# inflow_buildings = pd.concat([historic_rows, data_proj], ignore_index=True)
# inflow_buildings = inflow_buildings.sort_values(['Category_lv2', 'Year_from']).reset_index(drop=True)

# floor_area = inflow_buildings

# plt.figure(figsize=(14, 6))

# building_types = floor_area['Category_lv2'].unique()
# colors = ['red', 'green', 'blue', 'orange']  
# color_map = dict(zip(building_types, colors))

# for btype in building_types:
#     data_btype = floor_area[floor_area['Category_lv2'] == btype].sort_values('Year_from')
#     plt.plot(data_btype['Year_from'], data_btype['Value'],
#              color=color_map[btype], linewidth=2, label=btype)

# plt.xlabel('Year')
# plt.ylabel('Net floor area (m² NFA/yr)')
# plt.title('Floor area added to stocks (2010–2100)')
# plt.grid(True)

# plt.legend(loc='upper left')
# plt.tight_layout()
# plt.show()

# data_MI_buildings_exp_future = data_MI_buildings_exp[data_MI_buildings_exp['Year_to'] == 2100].copy()

# inflow_buildings = inflow_buildings.merge(data_MI_buildings_exp_future[['MISO2_country', 'Category_lv2', 'Category_lv3', 'Value']], on=['MISO2_country', 'Category_lv2'], how='left', suffixes=('_inflow', '_MI_exp'))
# inflow_buildings = inflow_buildings.drop('Category_lv3_inflow', axis=1)

# inflow_buildings['Value'] = inflow_buildings['Value_inflow'] * inflow_buildings['Value_MI_exp'] # Change MI here to reflect change in construction technology
# inflow_buildings['Category_lv3'] = inflow_buildings['Category_lv3_MI_exp']
# inflow_buildings['Unit'] = "metric tons/yr"
# inflow_buildings = inflow_buildings.rename(columns={'Value_inflow': 'FU_m2'})
# inflow_buildings = inflow_buildings[['Parameter', 'MISO2_country', 'Category_lv1', 'Category_lv2', 'Category_lv3', 'Year_from', 'Year_to', 'Unit', 'Value', 'FU_m2']]
# inflow_buildings = inflow_buildings[inflow_buildings['Year_from'] >= 2023]

# #%%%%%% Building sector|Buildings|Inflows|Maintenance
# #%%%%%% Building sector|Buildings|Inflows|Thermal renovation

# # Apply to building stock thermal renovation rates and material intensities incl. inflows and outflows based on CeAT data

# #%%%%%% Building sector|Buildings|Inflows|Operation

# # Apply to building stock heating energy demand per m2 of floor area based on CeAT data

# #%%%% Building sector|Heating systems
# #%%%%% Building sector|Heating systems|Stocks

# # Take data from CeAT using every consumption per fuel type and capacity per technology to quantify stocks

# #%%%%% Building sector|Heating systems|Inflows
# #%%%%%% Building sector|Heating systems|Inflows|Additions
# #%%%%%% Building sector|Heating systems|Inflows|Operation

# # Apply fuel usage of heating systems for operation based on CeAT data

# #%%%% Building sector|Household appliances
# #%%%%% Building sector|Household appliances|Stocks

# # Define number of household appliances (fridges, coolers, washing machines, dishwashers) based on households (use population as proxy, as we do not have household data included herein)

# #%%%%% Building sector|Household appliances|Inflows
# #%%%%%% Building sector|Household appliances|Inflows|Additions
# #%%%%%% Building sector|Household appliances|Inflows|Operation

# # Apply operational energy use of household appliances (look up factors)

# #%%% Transport sector
# #%%%% Transport sector|Vehicles
# #%%%%% Transport sector|Vehicles|Stocks

# # Take fleet size from CeAT and couple with vkm (derive from Lederer et al. pkm/tkm via occupation rates)
# # Add additional layer: vehicle components (data from TecEUS)

# #%%%%% Transport sector|Vehicles|Inflows
# #%%%%%% Transport sector|Vehicles|Inflows|Additions
# #%%%%%% Transport sector|Vehicles|Inflows|Operation

# # Apply fuel consumption (l fuel/vkm) to traffic scenarios based on Lederer et al. projections and CeAT factors

# #%%%% Transport sector|Transport infrastructure
# #%%%%% Transport sector|Transport infrastructure|Stocks

# # Take transport infrastructure from GLOMIS and couple with vkm (derive from Lederer et al. pkm/tkm via occupation rates)

# #%%%%% Transport sector|Transport infrastructure|Inflows
# #%%%%%% Transport sector|Transport infrastructure|Inflows|Additions
# #%%%%%% Transport sector|Transport infrastructure|Inflows|Maintenance

# # Apply lifetime assumptions to infrastructure stock (primarily roads) based on CeAT and Grossegger 2021 data

# #%%% Electricity sector
# #%%%% Electricity sector|Power plants
# #%%%%% Electricity sector|Power plants|Stocks

# # Quantify material stocks based on approach by Gerald (see CeAT sheets)

# #%%%%% Electricity sector|Power plants|Inflows
# #%%%%%% Electricity sector|Power plants|Inflows|Additions
# #%%%%%% Electricity sector|Power plants|Inflows|Operation
# #%%%% Electricity sector|Grid
# #%%%%% Electricity sector|Grid|Stocks

# # Quantify material stocks based on approach by Gerald (see CeAT sheets)

# #%%%%% Electricity sector|Grid|Inflows
# #%%%%%% Electricity sector|Grid|Inflows|Additions
# #%%%%%% Electricity sector|Grid|Inflows|Operation