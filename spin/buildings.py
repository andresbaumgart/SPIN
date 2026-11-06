"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Floor area and appliance projections

New construction per year and building type = population growth x base-year floor area per capita x floor space factor - floor area supplied by conversions, distributed over regions with base-year (or scenario urban-share) proportions. 
Households grow with floor area (or population); appliances per household stay at base-year levels except for shared laundry appliances.

Thermal renovation: the stock existing in the base year ('historic stock') is 'Not renovated',
except for a share per construction period that is already renovated (settings sheet). A share
of it can never be renovated (settings: 'Non-renovatable share'). Each year, the renovation rate
times the historic stock is renovated; with a renovation target year, at least the renovatable
rest divided by the years left is renovated, so it is all renovated by that year. Renovation is
taken proportionally from all renovatable floor area. Floor area added by conversions counts as
historic stock, 'Thermally renovated'. New construction after the base year is 'New construction'
(thermally renovated standard).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .mappings import LAUNDRY_APPLIANCES, PROJECTION_COHORTS, URBAN_CENTRE
from .scenarios import BuildingParams, phase_in_share

log = logging.getLogger(__name__)
MIN_M2 = 0.01

@dataclass
class BuildingResult:
    new_floor_area:     pd.DataFrame  # Additions: Region_lv2, Type_lv2, Year, Value (m2), Converted
    annual:             pd.DataFrame  # Year, Population, Cumulative_Stock, New_Additions, Converted_Stock, Per_Capita,
                                      # Renovation_Rate, Renovated_Flow, Not_Renovated_Stock, Renovated_Stock,
                                      # New_Construction_Stock
    appliances:         pd.DataFrame  # Type_lv2, Year, Value (units)
    renovation:         pd.DataFrame = None  # Year, Type_lv2, Construction_period, Renovation_status, Value (m2)

def region_shares(base: pd.DataFrame, urban_share=None) -> dict:
    by_region = base.groupby('Region_lv2')['Value'].sum()
    shares = (by_region / by_region.sum()).to_dict()
    if urban_share is None:
        return shares
    out = {URBAN_CENTRE: urban_share}
    rest = {k: v for k, v in shares.items() if k != URBAN_CENTRE}
    total = sum(rest.values())
    if total > 0:
        for region, share in rest.items():
            out[region] = (share / total) * (1.0 - urban_share)
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total > 0 else out

def _conversion_plan(p: BuildingParams, base: pd.DataFrame) -> list:
    plan = []
    for c in p.conversions:
        for source in c.sources:
            src = base[base['Type_lv2'] == source]
            by_region = src.groupby('Region_lv2')['Value'].sum().to_dict()
            total = sum(by_region.values())
            if c.mode == 'vacant':
                vacant = src[src['Occupancy'] == 'No residents'].groupby('Region_lv2')['Value'].sum().to_dict()
                amount = sum(vacant.values()) * c.rate
                # converted vacant area stays the source type, now occupied
                regions = {r: v / total if total > 0 else 0 for r, v in vacant.items()}
                targets = [source]
            else:
                amount = total * c.rate
                regions = {r: v / total if total > 0 else 0 for r, v in by_region.items()}
                targets = c.targets
            plan.append(dict(source=source, targets=targets, vacant=c.mode == 'vacant', amount=amount,
                             regions=regions, start=c.start, end=c.end, done=0))
    return plan

def project_buildings(p: BuildingParams, stock: pd.DataFrame, pop: pd.Series, end_year=2100,
                      renovated_share: dict | None = None, non_renovatable=0.0) -> BuildingResult:
    base_year = stock['Year'].min()
    base = stock[stock['Year'] == base_year]
    pop_base = pop.get(base_year, pop.iloc[0])
    type_stock = base.groupby('Type_lv2')['Value'].sum()
    per_capita = {t: v / pop_base for t, v in type_stock.items()}
    base_shares = region_shares(base)
    shares = region_shares(base, p.urban_share) if p.urban_share is not None else base_shares
    plan = _conversion_plan(p, base)

    stock_by_type = type_stock.to_dict()
    rows, annual, removals = [], [], []

    def add(btype, region, year, value, converted=False):
        rows.append({'Region_lv2': region, 'Type_lv2': btype, 'Year': year, 'Value': value, 'Converted': converted})
        stock_by_type[btype] = stock_by_type.get(btype, 0) + value

    for year in range(base_year, end_year + 1):
        if year == base_year:   # Growth from previous year into base year, base-year distribution
            pop_now = pop_base
            growth = max(0, pop_base - pop.get(base_year - 1, pop_base))
            year_shares = base_shares
        else:
            pop_now = pop.get(year, pop.iloc[-1])
            growth = max(0, pop_now - pop.get(year - 1, pop_base))
            year_shares = shares

        converted, supplied = [], {}
        for c in plan:
            amount = 0
            if year > base_year and c['start'] <= year <= c['end']:
                progress = (year - c['start']) / (c['end'] - c['start']) if c['end'] > c['start'] else 1.0
                total = c['amount'] * progress
                amount = max(0, total - c['done'])
                c['done'] = total
            converted.append(amount)
            for t in c['targets']:
                supplied[t] = supplied.get(t, 0) + amount

        # New construction ----------------------------------------------------
        new = 0
        for btype, intensity in per_capita.items():
            factor = p.floor_space_factor(btype, year) if year > base_year else 1.0
            needed = growth * intensity * factor
            if plan and btype in supplied:
                needed = max(0, needed - supplied[btype])
            if needed > MIN_M2:
                for region, share in year_shares.items():
                    val = needed * share
                    if val > MIN_M2:
                        add(btype, region, year, val)
                        new += val

        # Converted floor arean -----------------------------------------------
        for c, amount in zip(plan, converted):
            if amount <= 0:
                continue
            for region, share in c['regions'].items():
                val = amount * share
                if val <= MIN_M2:
                    continue
                for t in c['targets']:
                    add(t, region, year, val, converted=True)
                if not c['vacant']:
                    left = stock_by_type.get(c['source'], 0)
                    if left < val:
                        log.warning('Not enough %s floor area to convert %.0f m2 in %s', c['source'], val, year)
                    stock_by_type[c['source']] = max(0, left - val)
                    removals.append((year, c['source'], min(left, val)))

        total = sum(stock_by_type.values())
        annual.append({'Year': year, 'Population': pop_now, 'Cumulative_Stock': total, 'New_Additions': new,
                       'Converted_Stock': sum(converted), 'Per_Capita': total / pop_now})

    annual = pd.DataFrame(annual)
    additions = pd.DataFrame(rows)
    renovation, flows = renovation_status(p, base, additions, removals, base_year, end_year,
                                          renovated_share or {}, non_renovatable)
    status = renovation.groupby(['Year', 'Renovation_status'])['Value'].sum().unstack(fill_value=0)
    status = status.reindex(columns=[NOT_RENOVATED, RENOVATED, NEW_BUILD], fill_value=0).reindex(annual['Year'], fill_value=0)
    annual['Renovation_Rate'] = [p.renovation_rate(y) if y > base_year else 0.0 for y in annual['Year']]
    annual['Renovated_Flow'] = flows.reindex(annual['Year'], fill_value=0).values
    annual['Not_Renovated_Stock'] = status[NOT_RENOVATED].values
    annual['Renovated_Stock'] = status[RENOVATED].values          # historic stock, thermally renovated
    annual['New_Construction_Stock'] = status[NEW_BUILD].values   # built after the base year
    return BuildingResult(additions, annual, None, renovation)


NOT_RENOVATED, RENOVATED, NEW_BUILD = 'Not renovated', 'Thermally renovated', 'New construction'


def _new_cohort(year):
    for last, label in PROJECTION_COHORTS:
        if year <= last:
            return label
    return f'{year}'


def renovation_status(p: BuildingParams, base: pd.DataFrame, additions: pd.DataFrame, removals: list,
                      base_year, end_year, renovated_share: dict,
                      non_renovatable=0.0) -> tuple[pd.DataFrame, pd.Series]:
    """Floor area stock per year by building type, construction period and renovation status,
    plus the floor area renovated per year.

    Historic stock (base year incl. base-year additions): renovated share per construction period
    from the settings sheet, the rest not renovated; `non_renovatable` x historic stock is never
    renovated. Each later year, renovation = rate x historic stock or, with a target year, at least
    the renovatable rest / years left (at most the renovatable rest), proportionally from all
    renovatable floor area. Floor area removed by conversions is taken proportionally from that
    type's historic stock. Converted floor area counts as historic, renovated ('Converted');
    new construction after the base year as 'New construction' by construction period.
    """
    existing = base.groupby(['Type_lv2', 'Cohort'])['Value'].sum()
    if len(additions):
        early = additions[additions['Year'] <= base_year].groupby('Type_lv2')['Value'].sum()
        for t, v in early.items():
            key = (t, '2016 or later')
            existing[key] = existing.get(key, 0) + v
    existing = existing.sort_index()
    unknown = sorted(set(existing.index.get_level_values(1)) - set(renovated_share))
    if renovated_share and unknown:
        log.warning('No base-year renovated share for construction period(s) %s; 0 assumed', unknown)
    share = existing.index.get_level_values(1).map(lambda c: renovated_share.get(c, 0.0)).to_numpy(float)
    total = existing.to_numpy(float)
    ren = total * share
    nren = total - ren
    fixed = np.minimum(total * non_renovatable, nren)       # never renovated
    types = existing.index.get_level_values(0).to_numpy()

    later = additions[additions['Year'] > base_year] if len(additions) else additions
    new = conv = pd.Series(dtype=float)
    if len(later):
        built = later[~later['Converted'].astype(bool)]
        new = built.assign(Cohort=built['Year'].map(_new_cohort)).groupby(['Year', 'Type_lv2', 'Cohort'])['Value'].sum()
        conv = later[later['Converted'].astype(bool)].groupby(['Year', 'Type_lv2'])['Value'].sum()
    removed = {}
    for y, t, v in removals:
        removed.setdefault(y, {}).setdefault(t, 0)
        removed[y][t] += v

    out, flows, new_cum, conv_cum = [], {}, {}, {}
    for year in range(base_year, end_year + 1):
        if year > base_year:
            for t, v in removed.get(year, {}).items():          # conversions out of the historic stock
                m = types == t
                have = nren[m].sum() + ren[m].sum()
                if have > 0:
                    f = min(1.0, v / have)
                    nren[m] *= (1 - f)
                    ren[m] *= (1 - f)
                    fixed[m] *= (1 - f)
            pool = np.maximum(nren - fixed, 0)                  # renovatable, not yet renovated
            flow = p.renovation_rate(year) * (nren.sum() + ren.sum())
            if p.renovation_target and year <= p.renovation_target:
                flow = max(flow, pool.sum() / (p.renovation_target - year + 1))
            flow = min(flow, pool.sum())
            if flow > 0:
                move = pool * (flow / pool.sum())
                ren += move
                nren -= move
            flows[year] = flow
            if year in new.index.get_level_values(0):
                for (t, c), v in new.loc[year].items():
                    new_cum[(t, c)] = new_cum.get((t, c), 0) + v
            if year in conv.index.get_level_values(0):
                for t, v in conv.loc[year].items():
                    conv_cum[t] = conv_cum.get(t, 0) + v
        for i, (t, c) in enumerate(existing.index):
            out.append((year, t, c, NOT_RENOVATED, nren[i]))
            out.append((year, t, c, RENOVATED, ren[i]))
        for t, v in conv_cum.items():
            out.append((year, t, 'Converted', RENOVATED, v))
        for (t, c), v in new_cum.items():
            out.append((year, t, c, NEW_BUILD, v))
    df = pd.DataFrame(out, columns=['Year', 'Type_lv2', 'Construction_period', 'Renovation_status', 'Value'])
    return df, pd.Series(flows, dtype=float)

def project_appliances(p: BuildingParams, annual: pd.DataFrame, appliances: pd.DataFrame,
                       households: pd.DataFrame) -> pd.DataFrame:
    base = annual.iloc[0]
    hh_base = households['Households'].sum()
    per_household = {a: n / hh_base for a, n in appliances.groupby('Type_lv2')['Value'].sum().items()}
    driver = 'Population' if p.households_follow == 'population' else 'Cumulative_Stock'
    rows = []
    for _, r in annual.iterrows():
        hh = hh_base * (r[driver] / base[driver])
        for appliance, ratio in per_household.items():
            n = hh * ratio
            if p.sharing and appliance in LAUNDRY_APPLIANCES:
                n = n * (1 - phase_in_share(r['Year'], p.sharing.start, p.sharing.end, p.sharing.value))
            rows.append({'Type_lv2': appliance, 'Year': r['Year'], 'Value': n})
    return pd.DataFrame(rows)
