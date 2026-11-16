"""Interactive map with a warehouse-cost slider.

Slider = cost of opening one warehouse, in millions of km of total delivery
distance (order-km / 1e6; Olist has no real costs, so this is hypothetical).
For each cost the best number of warehouses minimizes
cost x (warehouses) + total delivery distance over the saved p = 1..15 results
(uncapacitated, single sourcing, 43 spaced candidates, all proven optimal).
Each region is drawn in the colour of the open warehouse nearest to it, which
is how the model assigns regions when there are no capacity limits.
Writes outputs/figures/network_map.html.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "data" / "processed" / "model_inputs"
CURVE = ROOT / "outputs" / "tables" / "scenarios" / "p_curve_spaced50km.csv"
OUT = ROOT / "outputs" / "figures" / "network_map.html"
COSTS_M = [0.25, 0.35, 0.5, 0.6, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0]  # million km
DEFAULT = 1.0

cand = pd.read_csv(INPUTS / "candidates_spaced50km.csv", dtype={"candidate_id": str}).set_index("candidate_id")
regions = pd.read_csv(INPUTS / "regions.csv", dtype={"region_id": str}).set_index("region_id")
d = pd.read_csv(INPUTS / "distance_matrix_km.csv", dtype={"region_id": str}).set_index("region_id")[list(cand.index)]
curve = pd.read_csv(CURVE, dtype={"open_sites": str}).set_index("p")
assert (curve.status == "Optimal").all()
ps, z = curve.index.to_numpy(), curve.objective_order_km.to_numpy()
total_orders = regions.orders_modeled.sum()
size = 4 + 14 * np.sqrt(regions.orders_modeled / regions.orders_modeled.max())

best_p = {F: int(ps[np.argmin(F * 1e6 * ps + z)]) for F in COSTS_M}
used = sorted({s for p in set(best_p.values()) for s in curve.open_sites[p].split()},
              key=lambda s: (min(p for p in curve.index if s in curve.open_sites[p].split()), s))
palette = pc.qualitative.Alphabet
assert len(used) <= len(palette)
site_color = {s: palette[k] for k, s in enumerate(used)}  # one fixed colour per warehouse site


ACCENTS = {"belem": "Belém", "brasilia": "Brasília", "ribeirao preto": "Ribeirão Preto", "sao luis": "São Luís",
           "sao paulo": "São Paulo", "sao jose do rio preto": "São José do Rio Preto"}
# label side for crowded sites (default: top right) so neighbouring labels do not overlap
LABEL_POS = {"227": "middle right", "140": "middle left", "071": "bottom left", "892": "middle left",
             "440": "middle right", "520": "middle right", "301": "top right", "900": "bottom right"}


def name(s):
    raw = cand.loc[s, "largest_city_label"]
    return ACCENTS.get(raw, raw.title().replace(" De ", " de ").replace(" Do ", " do "))


def city(s):
    return f"{name(s)}, {cand.loc[s, 'state']}"


def traces(F):
    p = best_p[F]
    sites = curve.open_sites[p].split()
    nearest = d[sites].idxmin(axis=1)
    load = regions.orders_modeled.groupby(nearest).sum()
    reg = go.Scattergeo(
        lon=regions.lng, lat=regions.lat, mode="markers", name="Demand regions", showlegend=False,
        marker=dict(size=size, color=nearest.map(site_color), opacity=0.55, line=dict(width=0)),
        text=[f"ZIP3 region {i}: {int(o):,} orders<br>served by the {city(nearest[i])} warehouse"
              for i, o in regions.orders_modeled.items()], hoverinfo="text")
    c = cand.loc[sites]
    wh = go.Scattergeo(
        lon=c.lng, lat=c.lat, mode="markers+text", name="Warehouses", showlegend=False,
        marker=dict(size=15, symbol="square", color=[site_color[s] for s in sites], line=dict(width=2, color="black")),
        text=[name(s) for s in sites], textposition=[LABEL_POS.get(s, "top right") for s in sites], textfont=dict(size=11),
        hovertext=[f"{city(s)}: serves {int(load[s]):,} orders ({100 * load[s] / total_orders:.0f}% of all)" for s in sites],
        hoverinfo="text")
    tot = (F * 1e6 * ps + z) / 1e6
    line = go.Scatter(x=ps, y=tot, mode="lines+markers", line=dict(color="#888"), marker=dict(size=6, color="#888"),
                      hovertemplate="%{x} warehouses<br>total cost %{y:.1f}M km<extra></extra>", showlegend=False)
    star = go.Scatter(x=[p], y=[tot[list(ps).index(p)]], mode="markers", marker=dict(size=15, color="#E15759", symbol="diamond"),
                      hovertemplate="best: %{x} warehouses<extra></extra>", showlegend=False)
    avg, red = curve.avg_km_per_order[p], 100 * (1 - z[list(ps).index(p)] / z[0])
    title = (f"If one warehouse costs {F:g}M km of delivery distance, the best network has {p} warehouse{'s' if p > 1 else ''}: "
             f"the average order travels {avg:.0f} km, {red:.0f}% less total distance than with one warehouse")
    pad = 0.08 * (tot.max() - tot.min())
    return [reg, wh, line, star], title, [tot.min() - pad, tot.max() + pad]


fig = make_subplots(rows=1, cols=2, column_widths=[0.46, 0.54], horizontal_spacing=0.05,
                    specs=[[{"type": "geo"}, {"type": "xy"}]],
                    subplot_titles=("Best network", "Total cost by number of warehouses"))
frames, steps = [], []
for F in COSTS_M:
    tr, title, yr = traces(F)
    frames.append(go.Frame(data=tr, name=f"{F:g}", traces=[0, 1, 2, 3],
                           layout=go.Layout(title_text=title, yaxis=dict(range=yr, autorange=False))))
    steps.append(dict(method="animate", label=f"{F:g}M",
                      args=[[f"{F:g}"], dict(mode="immediate", frame=dict(duration=0, redraw=True), transition=dict(duration=0))]))
init, init_title, init_yr = traces(DEFAULT)
for k, t in enumerate(init):
    fig.add_trace(t, row=1, col=1 if k < 2 else 2)
fig.frames = frames
fig.update_geos(scope="south america", projection_type="mercator", lonaxis_range=[-75, -26], lataxis_range=[-35, 6],
                showcountries=True, countrycolor="#999", showland=True, landcolor="#F4F1EA", showocean=True,
                oceancolor="#E6F0F7", showsubunits=True, subunitcolor="#CCC")
fig.update_xaxes(title_text="Number of warehouses", dtick=1, row=1, col=2)
fig.update_yaxes(title_text="Building cost + delivery distance (million km)", range=init_yr, autorange=False, row=1, col=2)
fig.update_layout(
    title_text=init_title, title_font_size=14, height=860, margin=dict(l=10, r=10, t=90, b=250),
    sliders=[dict(active=COSTS_M.index(DEFAULT), y=-0.14, pad=dict(t=10),
                  currentvalue=dict(prefix="Cost of one warehouse (million km of total delivery distance): "), steps=steps)],
    annotations=list(fig.layout.annotations) + [dict(
        text="Hypothetical network from 43 candidate sites; straight-line distance; no capacity limits; 2017 delivered Olist orders "
             "(CC BY-NC-SA 4.0).<br>Dot size = orders, colour = serving warehouse. Warehouse costs are assumed, not observed.",
        x=0.5, y=-0.4, xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="#666"))])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.write_html(OUT, include_plotlyjs="cdn")
print(f"Saved {OUT}")
print({F: best_p[F] for F in COSTS_M})
