"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Package entry point

SPIN derives scenarios of product stocks in physical units (floor area,
household appliances, vehicles, mobility infrastructure) from service demand
and product-per-service levers, as inputs for stock-driven MISO2.
"""
from .model import Model, run

__all__ = ['Model', 'run']
