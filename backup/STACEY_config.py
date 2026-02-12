# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model: Stock-driven Modelling and Analysis of Circular Economy Potentials (STACEY)
Author: André Baumgart (BOKU)
Email: andre.baumgart@boku.ac.at
Purpose: Scenario and parameter configuration
"""
    
#%% Packages

import os
import numpy as np
import pandas as pd

main_path = os.getcwd() 

#%% Config generator

# Generate config that describes scenarios: Reference, various other (based on an excel file that allows for measures to be implemented)
# Later move this to a separate .py (actual STACEY model, not the data preparation)

# Create scenarios from combinations of measures
## Material stocks
## 