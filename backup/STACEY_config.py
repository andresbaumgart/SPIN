# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model:   Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author:  André Baumgart (BOKU)
Email:   andre.baumgart@boku.ac.at
Purpose: Scenario and parameter configuration
"""
    
######################################################################################################################################################
######################################################################################################################################################
#%% Packages

import os
import numpy as np
import pandas as pd

main_path = os.getcwd() 

#%% Config generator

# Generate config that describes scenarios: Reference, various other (based on an excel file that allows for measures to be implemented)
# Later move this to a separate .py (actual STACEY model, not the data preparation)

# Select for each scnenario the correct stocks, lifetimes, waste rates, and recycling rates


# Reference scenario

stock_buildings_proj = pd.read_parquet("output/interim/stocks_buildings_proj.parquet")










# Dimensions

# Buildings: per age cohort
#           SFH
#           MFH
#           APB
#           NRB

# Vehicles: per age cohort (assumption-based)
#           Cars (conventional, electric, hybrid),
#           Two-wheelers (conventional, electric)
#           Trucks (<3.5, 3.5-7.5, >7.5)
#           Buses (conventional, electric)
#           Subway trains
#           Train cars
#           Tram cars
#           Bicycles
#           E-bikes

# Infrastructure (GLOMIS): per age cohort (assumption-based)
#           Motorway
#           Primary
#           Secondary
#           Tertiary
#           Local
#           Rural
#           Road bridges and tunnels
#           Railway
#           Subway
#           Tram
#           Rail bridges and tunnels
#           Station buildings
#           Parking garages
#           Parking buildings
#           Parking surfaces
#           Airport infrastructure
#           Harbors
#           Conventional fuelling infrastructure
#           E-charging stations 
    
# Heating/cooling systems: coupled with floor area
#           Natural gas
#           Direct electricity
#           Wood pellet
#           Wood logs
#           Wood chips
#           Solar
#           Heat pumps
#           Coal

# Household appliances: coupled with floor area
#           Fridges
#           Coolers
#           Dishwashers
#           Washing machines


# Materials
# Sand/gravel
# Concrete
# Bricks
# Gypsum
# Glass_flat
# Iron/steel
# Copper
# Aluminum
# Tungsten
# Silica
# Graphite
# EPS
# Glass wool
# Stone wool
# Timber
# Plastic

# Temporal dimension
# 2022-2060

# Age-cohorts
# 1980-1918
# 1919-1944
# 1945-1960
# 1961-1970
# 1971-1980
# 1981-1990
# 1991-2000
# 2001-2010
# 2011-2022
# 2023-2030
# 2031-2040
# 2041-2050
# 2051-2060

# Waste rates per material
# Recycling rates per material
# Lifetimes per stock type
# MI per stock type and material
