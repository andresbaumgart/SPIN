"""
# Model: Service-driven Product Stock Inventory (SPIN)
# Author: André Baumgart (BOKU/SEC), andre.baumgart@boku.ac.at
# File: Overview figures
"""

from __future__ import annotations
import matplotlib.pyplot as plt
from .scenarios import BASELINE
from .mappings import COOLING_SYSTEMS, HEATING_SYSTEMS, INFRA_MODE_GROUP

PALETTE =       ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
HEAT_COLORS =   {'Heat pump': '#1baf7a', 'District heating': '#e87ba4', 'Natural gas': '#2a78d6',
                 'Oil and coal': '#52514e', 'Direct electricity': '#eda100', 'Wood logs': '#8B4513',
                 'Pellets': '#c08a3e', 'Wood chips': '#d9b98c', 'Solar thermal': '#e34948'}
COOL_COLORS =   {'Room air conditioner': '#2a78d6'}
FUEL_COLORS =   {'Fossil': '#8B4513', 'Electric': '#2E8B57', 'Hybrid': '#4169E1', 'NA': '#808080'}
GREY =          '#52514e'
TRAFFIC =       [('Cars', 'billion pkm'), ('Buses', 'billion pkm'), ('Railway', 'billion pkm'), ('Subway/tram', 'billion pkm'), ('Road', 'billion tkm (freight)'), ('Rail', 'billion tkm (freight)')]

plt.rcParams.update({
    'axes.spines.top':      False, 
    'axes.spines.right':    False, 
    'axes.grid':            True, 
    'grid.color':           '#e4e3df',
    'axes.titleweight':     'bold', 
    'axes.titlesize':       11, 
    'axes.titlelocation':   'left', 
    'legend.frameon':       False,
    'legend.fontsize':      8, 
    'lines.linewidth':      2, 
    'axes.edgecolor':       GREY, 
    'xtick.color':          GREY, 
    'ytick.color':          GREY,
})

def _styles(names):
    out, i = {}, 0
    for n in names:
        if n == BASELINE:
            out[n] = dict(color=GREY, linewidth=2.6, zorder=5)
        else:
            out[n] = dict(color=PALETTE[i % 8], linestyle=['-', '--', ':'][i // 8 % 3])
            i += 1
    return out

def _grid(n, cols=3, size=(5, 4)):
    rows = (n + cols - 1) // cols
    fig, ax = plt.subplots(rows, cols, figsize=(size[0] * cols, size[1] * rows), squeeze=False)
    for k in range(n, rows * cols):
        ax[k // cols, k % cols].axis('off')
    return fig, [ax[k // cols, k % cols] for k in range(n)]

def _finish(fig, ax_list, path):
    for a in ax_list:
        a.set_xlabel('Year')
    ax_list[0].legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)

def _finish_legend_below(fig, ax_list, path, title=None):
    """Multi-panel figure with one shared legend below all panels."""
    for a in ax_list:
        a.set_xlabel('Year')
    if title:
        fig.suptitle(title, x=0.01, ha='left', fontweight='bold')
    handles, labels = ax_list[0].get_legend_handles_labels()
    cols = min(len(labels), 6)
    rows = -(-len(labels) // cols)
    fig.tight_layout(rect=(0, 0.02 + 0.025 * rows, 1, 0.98 if title else 1))
    fig.legend(handles, labels, loc='lower center', ncol=cols, frameon=False, fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)

def _total_and_index(series: dict, styles, title, unit, base_year, path, scale=1e6):
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5))
    for n, s in series.items():
        a.plot(s.index, s.values / scale, label=n, **styles[n])
        if s.get(base_year, 0) > 0:
            b.plot(s.index, s.values / s[base_year], label=n, **styles[n])
    a.set(title=title, ylabel=unit)
    b.set(title=f'{title}: index {base_year} = 1', ylabel=f'Index ({base_year} = 1)')
    b.axhline(1, color=GREY, linestyle='--', linewidth=0.8)
    _finish(fig, [a, b], path)

def plot_all(results: dict, s):
    by, out = s.base_year, s.output_dir / 'figures'

    # Buildings ---------------------------------------------------------------
    res = {n: r for n, r in results.items() if n == BASELINE or 'buildings' in r.scenario.sectors}
    st = _styles(res)
    fig, ax = plt.subplots(1, 3, figsize=(18, 5))
    for n, r in res.items():
        a = r.buildings.annual
        ax[0].plot(a['Year'], a['Cumulative_Stock'] / 1e6, label=n, **st[n])
        ax[1].plot(a['Year'], a['New_Additions'] / 1e6, label=n, **st[n])
        ax[2].plot(a['Year'], a['New_Additions'].cumsum() / 1e6, label=n, **st[n])
    for a, t, u in zip(ax, ['Floor area stock', 'Annual new construction', 'Cumulative new construction'],
                       ['million m²', 'million m²/year', 'million m²']):
        a.set(title=t, ylabel=u)
    _finish(fig, list(ax), out / 'stocks_buildings.png')

    fig, ax = _grid(len(res))
    for a, (n, r) in zip(ax, res.items()):
        b = r.buildings.annual
        a.stackplot(b['Year'], b['Not_Renovated_Stock'] / 1e6, b['Renovated_Stock'] / 1e6,
                    b['New_Construction_Stock'] / 1e6,
                    labels=['Historic, not renovated (_unr)', 'Historic, thermally renovated (_tr_his)',
                            'New construction (_tr)'], colors=['#eb6834', '#2a78d6', '#9ec5f0'],
                    edgecolor='white', linewidth=0.5)
        a.set(title=n, ylabel='million m²')
    _finish_legend_below(fig, ax, out / 'stocks_buildings_renovation.png', 'Floor area stock by renovation status')

    apps = sorted({t for r in res.values() for t in r.buildings.appliances['Type_lv2'].unique()})
    fig, ax = _grid(len(apps))
    for a, app in zip(ax, apps):
        for n, r in res.items():
            d = r.buildings.appliances.query('Type_lv2 == @app').groupby('Year')['Value'].sum() / 1e6
            a.plot(d.index, d.values, label=n, **st[n])
        a.set(title=app, ylabel='million units')
    _finish(fig, ax, out / 'stocks_appliances.png')

    # Heating -----------------------------------------------------------------
    res = {n: r for n, r in results.items() if n == BASELINE or {'buildings', 'heating'} & r.scenario.sectors}
    fig, ax = _grid(len(res))
    top = max(r.heating.groupby('Year')['Capacity'].sum().max() for r in res.values()) / 1000 * 1.05
    for a, (n, r) in zip(ax, res.items()):
        d = r.heating.pivot_table(index='Year', columns='Heating_system', values='Capacity', aggfunc='sum')
        d = d.reindex(columns=[x for x in HEATING_SYSTEMS if x in d.columns]).fillna(0) / 1000
        a.stackplot(d.index, d.T.values, labels=d.columns, colors=[HEAT_COLORS[x] for x in d.columns],
                    edgecolor='white', linewidth=0.3)
        a.set(title=n, ylabel='GW', ylim=(0, top))
    _finish_legend_below(fig, ax, out / 'stocks_heating_capacity.png', 'Installed heating capacity (space heating and hot water)')

    # Cooling -----------------------------------------------------------------
    fig, ax = _grid(len(res))
    top = max(r.cooling.groupby('Year')['Capacity'].sum().max() for r in res.values()) / 1000 * 1.05
    for a, (n, r) in zip(ax, res.items()):
        d = r.cooling.pivot_table(index='Year', columns='Cooling_system', values='Capacity', aggfunc='sum')
        d = d.reindex(columns=[x for x in COOLING_SYSTEMS if x in d.columns]).fillna(0) / 1000
        a.stackplot(d.index, d.T.values, labels=d.columns, colors=[COOL_COLORS[x] for x in d.columns],
                    edgecolor='white', linewidth=0.3)
        a.set(title=n, ylabel='GW', ylim=(0, top))
    _finish_legend_below(fig, ax, out / 'stocks_cooling_capacity.png', 'Installed space cooling capacity')

    # Mobility ----------------------------------------------------------------
    res = {n: r for n, r in results.items() if n == BASELINE or 'mobility' in r.scenario.sectors}
    st = _styles(res)
    _total_and_index({n: r.vehicles.vehicles.groupby('Year')['Value'].sum() for n, r in res.items()},
                     st, 'Vehicle fleet', 'million vehicles', by, out / 'stocks_vehicles.png')

    types = sorted({t for r in res.values() for t in r.vehicles.vehicles['Type_lv2'].unique()})
    fig, ax = _grid(len(types), cols=4, size=(4.5, 3.4))
    for a, vtype in zip(ax, types):
        peak = max(r.vehicles.vehicles.loc[r.vehicles.vehicles['Type_lv2'] == vtype, 'Value'].max() for r in res.values())
        scale, unit = (1e6, 'million') if peak >= 1e6 else (1e3, 'thousand') if peak >= 1e3 else (1, '')
        for n, r in res.items():
            v = r.vehicles.vehicles
            d = v[v['Type_lv2'] == vtype].groupby('Year')['Value'].sum() / scale
            a.plot(d.index, d.values, label=n, **st[n])
        a.set(title=vtype.replace('_', ' '), ylabel=f'{unit} vehicles'.strip(), ylim=(0, None))
    _finish_legend_below(fig, ax, out / 'stocks_vehicles_by_mode.png', 'Vehicle stock by mode')

    fig, ax = _grid(len(res))
    for a, (n, r) in zip(ax, res.items()):
        fuel = r.vehicles.by_fuel.groupby(['Fuel_type', 'Year'])['Value'].sum() / 1e6
        for f in fuel.index.get_level_values(0).unique():
            a.plot(fuel[f].index, fuel[f].values, label=f, color=FUEL_COLORS.get(f, GREY))
        a.set(title=n, ylabel='million vehicles')
    _finish(fig, ax, out / 'stocks_vehicles_by_fuel.png')

    fig, ax = _grid(len(TRAFFIC))
    for a, (mode, unit) in zip(ax, TRAFFIC):
        for n, r in res.items():
            t = r.vehicles.traffic.get(mode)
            if t is not None:
                t = t[t.index >= by]
                a.plot(t.index, t.values, label=n, **st[n])
        a.set(title=f'Traffic: {mode}', ylabel=unit)
    _finish(fig, ax, out / 'additional_traffic_volume.png')

    _total_and_index({n: r.infrastructure.groupby('Year')['Value'].sum() for n, r in res.items()},
                     st, 'Infrastructure area', 'million m²', by, out / 'stocks_infrastructure.png')

    modes = ['Road', 'Railway', 'Subway/tram']
    fig, ax = _grid(len(modes))
    for a, mode in zip(ax, modes):
        for n, r in res.items():
            p = r.infrastructure
            d = p[p['Type_lv2'].map(INFRA_MODE_GROUP) == mode].groupby('Year')['Value'].sum() / 1e6
            a.plot(d.index, d.values, label=n, **st[n])
        a.set(title=f'Infrastructure: {mode}', ylabel='million m²')
    _finish(fig, ax, out / 'stocks_infrastructure_by_mode.png')
