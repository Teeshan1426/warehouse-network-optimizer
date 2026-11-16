# Warehouse network optimization: project summary

A company with customers spread across a country faces a tradeoff: more warehouses bring goods closer to customers, but each warehouse costs money to build and run. This project asks where such a network should put its warehouses, and how many are worth building. It builds an optimization model to examine that tradeoff, using 43,314 e-commerce orders from Brazil (Olist, 2017, delivered orders). The network is hypothetical and does not describe Olist's actual operations.

## Approach

I grouped the orders into 839 regions by ZIP code prefix and used each region's order count as its demand. I then picked 43 hypothetical warehouse sites, spaced at least 50 km apart. For each region and site I calculated the straight-line distance, and built an integer linear programming model in Python (PuLP, with the CBC solver). The model chooses which sites to open and assigns each region to one open warehouse, minimizing total demand-weighted distance. I solved it for every network size from 1 to 15 warehouses, each proven optimal.

## Findings

**More warehouses cut distance, but each new one helps less.** With one warehouse, the average order travels about 545 km. With five it travels about 240 km, and with ten about 147 km, which is 73% less total distance than a single warehouse. After that the gains get small: the 15th warehouse cuts distance by only 4%.

**The best number of warehouses depends on what a warehouse costs.** Olist has no warehouse cost data, so I measured a warehouse's cost in kilometers of delivery distance. If one warehouse costs about as much as 1 million km of total delivery distance, the lowest total cost is at about 6 warehouses. If it costs 2 million km, the best is about 4, and if it costs 0.5 million km, about 10.

**Warehouses go where the orders are first, then spread out to reach farther regions.** Demand is concentrated: São Paulo state alone accounts for 39% of orders, and 22% come from within 50 km of the Guarulhos site near São Paulo. So with only 3 warehouses, the model puts one near São Paulo (Sorocaba), one in Minas Gerais (Juiz de Fora), and one in the northeast (Aracaju). Each network size is solved separately, so a bigger network isn't just a smaller one with extra sites. The 10-warehouse network uses Rio de Janeiro, Belo Horizonte, Brasília, Recife, Belém, Porto Alegre, and others, so that distant regions aren't served from São Paulo.

## Recommendation

If a warehouse costs roughly 1 million km of delivery distance, I would build about 6 warehouses, near São Paulo (Guarulhos), in Minas Gerais (Juiz de Fora), Brasília, Porto Alegre, Aracaju in the northeast, and São Luís (Maranhão). That cuts total distance by about 61% compared with a single warehouse, and the average order travels about 215 km instead of 545 km. If warehouses are more expensive, a 4-warehouse network (without Brasília and São Luís) still cuts distance by about 48%. These are modeled results from hypothetical sites, not a plan for Olist.

## Limitations

- **Distance is a straight line,** not road distance, so real delivery routes would be longer.
- **Every order counts the same.** I didn't account for order size, weight, or product type.
- **Warehouse costs are assumed.** Olist has no warehouse cost data, so the results show how the answer changes with cost, not what it actually is.
