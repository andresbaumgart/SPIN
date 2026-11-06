"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Classification tables and name mappings
"""

#%% Buildings

BUILDING_TYPES = ['R_SFH', 'R_MFH', 'R_APB', 'R_IHH', 'NR_public', 'NR_indust','NR_trafcom', 'NR_retail', 'NR_office', 'NR_hotels']
RESIDENTIAL_TYPES = ['R_SFH', 'R_MFH', 'R_APB', 'R_IHH']
URBAN_CENTRE = 'Urban centre (large)'

STATCUBE_COLUMNS = {
    'Region':                                           'Region_lv1',
    'Urban_rural':                                      'Region_lv2',
    'Type of building (predominant use)':               'Type_lv2',
    'Period of construction (Level +1)':                'Cohort',
    'Type of ownership':                                'Ownership',
    'Occupancy status of the dwelling':                 'Occupancy',
    'Useful floor space in square meters per occupant': 'Density',
    'Number':                                           'Value',
}

BUILDING_TYPE_NAMES = {
    'Residential buildings with one conventional dwelling':            'R_SFH',
    'Residential buildings with two conventional dwellings':           'R_MFH',
    'Residential buildings with three or more conventional dwellings': 'R_APB',
    'Buildings for institutional households':                          'R_IHH',
    'Buildings for public entertainment, education and health care':   'NR_public',
    'Industrial buildings and warehouses':                             'NR_indust',
    'Traffic and communication buildings':                             'NR_trafcom',
    'Wholesale and retail trade buildings':                            'NR_retail',
    'Office buildings':                                                'NR_office',
    'Hotels and similar buildings':                                    'NR_hotels',
}

OWNERSHIP_NAMES = {
    'Private persons':                     'Private',
    'Public bodies':                       'Public',
    'Limited profit housing associations': 'Limited-profit',
}

# Construction period -> (first year, last year) for evenly spreading stock
CONSTRUCTION_PERIODS = {
    '2016 or later': (2016, 2024),   
    '2011 to 2015':  (2011, 2015),
    '2001 to 2010':  (2001, 2010),
    '1991 to 2000':  (1991, 2000),
    '1981 to 1990':  (1981, 1990),
    '1971 to 1980':  (1971, 1980),
    '1961 to 1970':  (1961, 1970),
    '1945 to 1960':  (1945, 1960),
    '1919 to 1944':  (1919, 1944),
    'Before 1919':   (1900, 1918),   
}

# UFA -> NFA conversion per type (1.0 = no conversion)
UFA_TO_NFA = {t: 1.0 for t in BUILDING_TYPES}

# Projection cohorts for new construction
PROJECTION_COHORTS = [(2030, '2025 to 2030'), 
                      (2035, '2031 to 2035'), 
                      (2040, '2036 to 2040'),
                      (2050, '2041 to 2050'), 
                      (2060, '2051 to 2060'), 
                      (2070, '2061 to 2070'),
                      (2080, '2071 to 2080'), 
                      (2090, '2081 to 2090'), 
                      (2100, '2091 to 2100')]

BUILDING_OUTPUT_COLUMNS = ['Parameter', 'Region_lv1', 'Region_lv2', 'Type_lv1', 'Type_lv2', 'Ownership', 'Occupancy', 'Cohort', 'Density', 'Year_from', 'Year_to', 'Year', 'Unit', 'Value']

# Appliances whose stock is reduced by appliance-sharing measures
LAUNDRY_APPLIANCES = ['Washing Machine', 'Tumble Dryer']

#%% Mobility

# Vehicle type -> traffic series (pkm/tkm) it is correlated with
VEHICLE_TO_TRAFFIC = {
    'Cars':                             'Cars',
    'Moped':                            'Cars',
    'Motorcycles':                      'Cars',
    'Buses':                            'Buses',
    'Railway_passenger_train_electric': 'Railway',     
    'Railway_passenger_train_fossil':   'Railway',
    'Railway_passenger_car':            'Railway',
    'Railway_freight_train_electric':   'Rail',        
    'Railway_freight_train_fossil':     'Rail',
    'Railway_freight_car':              'Rail',
    'Tram_train':                       'Subway/tram',
    'Tram_car':                         'Subway/tram',
    'Subway_car':                       'Subway/tram',
    'Subway_train':                     'Subway/tram',
    'Trucks':                           'Road',     
    'Vehicles_other':                   'Road',
    'Trailers':                         'Road',
    'Bicycles':                         'Cycling',
    'E_bikes':                          'Cycling',
}

ACTIVE_MODES = ['Cycling', 'Walking']    # Follow population only (no GDP effect)
TRAFFIC_EXCLUDED = ['Active']            # Container category without values

# Modal shift: car pkm -> passenger rail modes; road tkm -> rail tkm
PKM_SHIFT_FROM, PKM_SHIFT_TO = 'Cars', ['Railway', 'Subway/tram']
TKM_SHIFT_FROM, TKM_SHIFT_TO = 'Road', ['Rail']

# Traffic mode -> vehicle type whose occupancy / load factor converts its pkm / tkm into vehicle-km
# (modes not listed: constant occupancy, vehicle-km grow like pkm / tkm)
MODE_OCCUPANCY_TYPE = {'Cars': 'Cars', 'Buses': 'Buses', 'Road': 'Trucks'}

# Vehicle type -> electrification parameter key
ELECTRIFICATION_GROUPS = {'Cars': 'car', 'Motorcycles': 'motorcycle', 'Moped': 'motorcycle', 'Buses': 'bus', 'Trucks': 'truck'}

DEFAULT_ELASTICITY = 0.5
MAX_ABS_ELASTICITY = 2

# Infrastructure type -> traffic series that drive it
_ROAD           = ['Cars', 'Buses']
_RAIL           = ['Railway', 'Rail']
_URBAN_RAIL     = ['Subway/tram']
INFRA_TO_TRAFFIC = {
    'motorway':                     _ROAD, 
    'motorway_bridge':              _ROAD, 
    'motorway_tunnel':              _ROAD,
    'primary':                      _ROAD, 
    'primary_bridge':               _ROAD, 
    'primary_tunnel':               _ROAD,
    'secondary_bridge':             _ROAD, 
    'secondary_tunnel':             _ROAD,
    'tertiary_bridge':              _ROAD, 
    'tertiary_tunnel':              _ROAD,
    'local':                        _ROAD, 
    'local_bridge':                 _ROAD, 
    'local_tunnel':                 _ROAD,
    'secondary':                    _ROAD, 
    'tertiary':                     _ROAD,
    'track':                        _ROAD, 
    'track_bridge':                 _ROAD, 
    'track_tunnel':                 _ROAD,
    'parking_surface':              _ROAD, 
    'parking_underground':          _ROAD, 
    'parking_building':             _ROAD,
    'gas_station_building':         _ROAD, 
    'charging_station':             _ROAD,
    'railway':                      _RAIL, 
    'railway_bridge':               _RAIL, 
    'railway_tunnel':               _RAIL,
    'railway_building':             _RAIL, 
    'railway_building_platform':    _RAIL, 
    'rail_other':                   _RAIL,
    'subway':                       _URBAN_RAIL, 
    'subway_bridge':                _URBAN_RAIL, 
    'subway_tunnel':                _URBAN_RAIL,
    'subway_building':              _URBAN_RAIL, 
    'tram':                         _URBAN_RAIL,
}

INFRA_MODE_GROUP = {k: ('Road' if v is _ROAD else 'Railway' if v is _RAIL else 'Subway/tram')
                    for k, v in INFRA_TO_TRAFFIC.items()}

# Infrastructure that follows the vehicle fleet of a fuel type
INFRA_FUEL_LINK = {'charging_station': ['Electric'], 'gas_station_building': ['Fossil', 'Hybrid']}
# vehicles that use charging / fuelling stations (road motor vehicles; not bikes, trains, trams)
STATION_VEHICLES = ['Cars', 'Moped', 'Motorcycles', 'Buses', 'Trucks', 'Vehicles_other']
FUELING_STATION_FLOOR = 0.3   # gas stations never fall below 30 % of base

# ---------------------------------------------------------------------------
# MISO2 end-use sectors
# ---------------------------------------------------------------------------

BUILD_TO_MISO = {
    'R_SFH':                            'build_r_sfh', 
    'R_MFH':                            'build_r_mfh', 
    'R_APB':                            'build_r_apb',
    'R_IHH':                            'build_nr', 
    'NR_public':                        'build_nr', 
    'NR_indust':                        'build_nr',
    'NR_trafcom':                       'build_nr', 
    'NR_retail':                        'build_nr', 
    'NR_office':                        'build_nr',
    'NR_hotels':                        'build_nr',
}

# Renovation status -> suffix of the MISO2 building end use (e.g. build_r_sfh_unr)
RENOVATION_SUFFIX = {
    'Not renovated':        '_unr',      # historic stock (base year), not thermally renovated
    'Thermally renovated':  '_tr_his',   # historic stock, thermally renovated (incl. converted floor area)
    'New construction':     '_tr',       # built after the base year, thermally renovated standard
}

# Heating systems (columns of the 'heating' sheet, names in the heating input files) -> MISO2 end use (MW)
HEATING_TO_MISO = {
    'Heat pump':            'heat_heatpump',
    'District heating':     'heat_district',
    'Natural gas':          'heat_gas',
    'Oil and coal':         'heat_oil_coal',
    'Direct electricity':   'heat_direct_electric',
    'Wood logs':            'heat_woodlogs',
    'Pellets':              'heat_pellets',
    'Wood chips':           'heat_woodchips',
    'Solar thermal':        'heat_solar_thermal',
}
HEATING_SYSTEMS = list(HEATING_TO_MISO)

# Cooling system (all cooling by room air conditioners) -> MISO2 end use (MW)
COOLING_TO_MISO = {
    'Room air conditioner': 'heat_ac',
}
COOLING_SYSTEMS = list(COOLING_TO_MISO)

# Appliance names as in data_appliance_penetration_rates.xlsx -> MISO2 end use
HHA_TO_MISO = {
    'Fridge':                           'hha_fridge',
    'Freezer':                          'hha_freezer',
    'Washing Machine':                  'hha_washing_machine',
    'Tumble Dryer':                     'hha_dryer',
    'Dishwasher':                       'hha_dishwasher',
    'TV':                               'hha_tv',
}

VEH_TO_MISO = {
    'Cars_electric':                    'veh_car_bev',
    'Cars_fossil':                      'veh_car_icev',
    'Cars_hybrid':                      'veh_car_hev',
    'Motorcycles_electric':             'veh_motorcycles_bev',
    'Motorcycles_fossil':               'veh_motorcycles_icev',
    'Moped_fossil':                     'veh_moped_icev',
    'Moped_electric':                   'veh_moped_bev',
    'Trucks_fossil':                    'veh_trucks_icev',
    'Trucks_electric':                  'veh_trucks_bev',
    'Trucks_hybrid':                    'veh_trucks_hev',
    'Buses_fossil':                     'veh_buses_icev',
    'Buses_electric':                   'veh_buses_bev',
    'Vehicles_other_fossil':            'veh_other_icev',
    'Vehicles_other_electric':          'veh_other_bev',
    'Vehicles_other_hybrid':            'veh_other_hev',
    'Trailers':                         'veh_trailer',
    'Bicycles':                         'veh_bicycles',
    'E_bikes_electric':                 'veh_e_bikes',
    'Railway_passenger_train_electric': 'veh_railway_passenger_train_electric',
    'Railway_passenger_train_fossil':   'veh_railway_passenger_train_fossil',
    'Railway_passenger_car':            'veh_railway_passenger_car',
    'Railway_freight_train_electric':   'veh_railway_freight_train_electric',
    'Railway_freight_train_fossil':     'veh_railway_freight_train_fossil',
    'Railway_freight_car':              'veh_railway_freight_car',
    'Subway_car':                       'veh_subway_car',
    'Subway_train_electric':            'veh_subway_train_electric',
    'Tram_car':                         'veh_tram_car',
    'Tram_train_electric':              'veh_tram_train_electric',
}
INFRA_TO_MISO = {
    'motorway':                         'infra_motorway', 
    'motorway_bridge':                  'infra_motorway_bridge',
    'motorway_tunnel':                  'infra_motorway_tunnel',
    'primary':                          'infra_primary', 
    'primary_bridge':                   'infra_primary_bridge',
    'primary_tunnel':                   'infra_primary_tunnel',
    'secondary':                        'infra_secondary', 
    'secondary_bridge':                 'infra_secondary_bridge',
    'secondary_tunnel':                 'infra_secondary_tunnel',
    'tertiary':                         'infra_tertiary', 
    'tertiary_bridge':                  'infra_tertiary_bridge',
    'tertiary_tunnel':                  'infra_tertiary_tunnel',
    'local':                            'infra_local', 
    'local_bridge':                     'infra_local_bridge', 
    'local_tunnel':                     'infra_local_tunnel',
    'track':                            'infra_rural', 
    'track_bridge':                     'infra_rural_bridge', 
    'track_tunnel':                     'infra_rural_tunnel',
    'parking_surface':                  'infra_parking_surface', 
    'parking_underground':              'infra_parking_underground',
    'parking_building':                 'infra_parking_building',
    'gas_station_building':             'infra_fueling_station', 
    'charging_station':                 'infra_charging_station',
    'railway':                          'infra_railway', 
    'railway_bridge':                   'infra_railway_bridge',
    'railway_tunnel':                   'infra_railway_tunnel', 
    'railway_building':                 'infra_railway_station',
    'railway_building_platform':        'infra_railway_station_platform', 
    'rail_other':                       'infra_rail_other',
    'subway':                           'infra_subway_groundlevel', 
    'subway_bridge':                    'infra_subway_elevated',
    'subway_tunnel':                    'infra_subway_underground', 
    'subway_building':                  'infra_subway_station',
    'tram':                             'infra_tram',
}

# Operational energy of trains: end use -> (traffic series [billion pkm or tkm], vehicle types sharing that traffic).
# Energy per train = energy per pkm (tkm) x traffic / number of these trains (data_operational_energy.xlsx)
TRAIN_TRAFFIC = {
    'veh_railway_passenger_train_electric': ('Railway', ['Railway_passenger_train_electric', 'Railway_passenger_train_fossil']),
    'veh_railway_passenger_train_fossil':   ('Railway', ['Railway_passenger_train_electric', 'Railway_passenger_train_fossil']),
    'veh_railway_freight_train_electric':   ('Rail', ['Railway_freight_train_electric', 'Railway_freight_train_fossil']),
    'veh_railway_freight_train_fossil':     ('Rail', ['Railway_freight_train_electric', 'Railway_freight_train_fossil']),
    'veh_subway_train_electric':            ('Subway/tram', ['Subway_train', 'Tram_train']),
    'veh_tram_train_electric':              ('Subway/tram', ['Subway_train', 'Tram_train']),
}

# MISO end uses that are summed into one
MISO_AGGREGATE_GROUPS = {'infra_railway': ['infra_railway', 'infra_rail_other']}

# MISO2 sector whose age structure is used for power plants in the stock initialisation
POWERPLANT_COHORT_SECTOR = 'Civil_engineering_except_roads'

POWERPLANT_TYPES = ['powerplants_coal', 
                    'powerplants_oil', 
                    'powerplants_gas',
                    'powerplants_biomass', 
                    'powerplants_waste', 
                    'powerplants_wind',
                    'powerplants_pv', 
                    'powerplants_geothermal', 
                    'powerplants_hydro_ror',
                    'powerplants_hydro_storage']

# Dummy stock for end uses that MISO2 cannot take as 0 (written in every year where SPIN has 0)
STOCK_DUMMY = {'powerplants_geothermal': 0.00001}

# MISO end use -> MISO2 cohort sector (for stock initialisation of non-buildings)
ROAD_INFRA = {
    'infra_motorway', 
    'infra_motorway_bridge', 
    'infra_motorway_tunnel',
    'infra_primary', 
    'infra_primary_bridge', 
    'infra_primary_tunnel',
    'infra_secondary', 
    'infra_secondary_bridge', 
    'infra_secondary_tunnel',
    'infra_tertiary', 
    'infra_tertiary_bridge', 
    'infra_tertiary_tunnel',
    'infra_local', 
    'infra_local_bridge', 
    'infra_local_tunnel',
    'infra_rural', 
    'infra_rural_bridge', 
    'infra_rural_tunnel',
    'infra_parking_surface', 
    'infra_parking_underground', 
    'infra_parking_building',
    'infra_fueling_station', 
    'infra_charging_station',
}

MOTOR_VEHICLES = {
    'veh_car_icev', 
    'veh_car_bev', 
    'veh_car_hev',
    'veh_moped_icev', 
    'veh_moped_bev',
    'veh_motorcycles_icev', 
    'veh_motorcycles_bev',
    'veh_buses_icev', 
    'veh_buses_bev',
    'veh_trucks_icev', 
    'veh_trucks_bev', 
    'veh_trucks_hev',
    'veh_trailer',
}

def miso_cohort_sector(end_use):
    """MISO2 cohort sector used to distribute a non-building end use over age cohorts."""
    if end_use.startswith('infra_'):
        return 'Roads' if end_use in ROAD_INFRA else 'Civil_engineering_except_roads'
    if end_use.startswith('veh_'):
        return 'Motor_vehicles_trailers_and_semi-trailers' if end_use in MOTOR_VEHICLES else 'Other_transport_equipment'
    if end_use.startswith('hha_') or end_use in COOLING_TO_MISO.values():   # appliances, room air conditioners
        return 'Electrical_equipment'
    if end_use.startswith('powerplants_'):
        return POWERPLANT_COHORT_SECTOR
    return None
