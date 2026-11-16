# Assumptions

What the model assumes. How each piece was built and checked is in [METHODS.md](METHODS.md).

| Assumption | Why |
| --- | --- |
| Demand = delivered orders purchased in 2017, one unit per order | 2017 is the only full calendar year in the data; order size and weight are ignored |
| Demand is flat across the year | Volume actually grew from about 750 orders in January to about 7,300 in November; peak months are not modeled |
| Orders are grouped into 839 ZIP3 regions, each placed at one point | Keeps the model a workable size; the typical order sits about 4 km from its region's point (median; mean about 14 km) |
| Warehouses can only open at 43 hypothetical candidate sites | Busiest regions plus the busiest region in each state, spaced at least 50 km apart; not real or Olist sites |
| Candidates are ranked by orders per ZIP3 region | Big cities are split across many ZIP3 regions, so some capitals (Curitiba, Salvador, Goiânia) are not candidates; ranking by metro-area demand would be a next step |
| Distance is one-way straight-line (great-circle) km | Simple and consistent; real road routes are longer |
| Each region is served by exactly one warehouse, which stocks every product | Simplifies assignment; ignores inventory and inbound supply |
| No capacity limits in the main results | Olist has no warehouse sizes; a separate capacity test is in METHODS.md |
| A warehouse's cost is the same everywhere and is measured in km of delivery distance | Olist has no warehouse cost data, so cost is a dial (0.25 to 6 million km), not an estimate |
