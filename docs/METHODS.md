# Methods

How the inputs were built, how the model works, and how the results were checked. Assumptions are in [ASSUMPTIONS.md](ASSUMPTIONS.md); the data audit is in [DATASET_ASSESSMENT.md](DATASET_ASSESSMENT.md).

## 1. Demand regions

- 43,428 delivered orders purchased in 2017, grouped by the first three digits of the customer ZIP code (ZIP3).
- ZIP3 was chosen over state (27 regions, too coarse), city (3,360, with many tiny ones) and full ZIP (12,036, mostly tiny).
- Each region's point: duplicate coordinates removed, points outside Brazil dropped, then the median point per ZIP5, averaged by orders within each ZIP3.
- 114 orders (0.26%) had no usable coordinate and were excluded, leaving 43,314 orders in 839 regions.
- Grouping error is small: an order sits a median 3.7 km from its region's point, and totals differ from full-ZIP results by under 0.3%.

## 2. Candidate sites and distances

- 81 candidates: the 60 busiest regions plus the busiest region in each state.
- Thinned to 43 by keeping a site only if it is at least 50 km from every busier site already kept (many metro areas had several near-identical sites).
- Distance from every region to every candidate: great-circle km (haversine), cross-checked with a second formula.
- Using 43 instead of 81 sites raises total distance by only 0.1% to 2.5% across 1 to 15 warehouses.

## 3. Model (`src/facility_location.py`, PuLP with the CBC solver)

- Decisions: open site j or not (y = 0/1); serve region i from site j or not (x = 0/1).
- Minimize total order-km: sum of orders(i) × distance(i, j) × x(i, j).
- Rules: each region served by exactly one site; only open sites can serve; exactly p sites open.
- Optional: a cost F per open site (with the number of sites left free), or a capacity limit Q per site.
- Every result's solver status is checked; a run that stops at its time limit is never reported as optimal.

## 4. Validation

`src/check_candidate_prototype.py` runs the model on a four-customer example whose answers were verified by full enumeration. It reproduces both known totals.

## 5. Results for 1 to 15 warehouses (`src/run_scenarios.py`)

All 15 solves are proven optimal (gap 0) on both the 43-site and the 81-site lists.

| Warehouses | 1 | 2 | 5 | 6 | 10 | 15 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Average trip per order (km) | 545 | 402 | 240 | 215 | 147 | 109 |
| Less total distance than 1 warehouse | 0% | 26.2% | 56.0% | 60.6% | 73.0% | 80.0% |

Each added warehouse saves fewer km than the one before: the 2nd cuts total distance by 26.2%, the 15th by 4.0%.

## 6. Best number of warehouses by cost (`src/break_even.py`)

For a warehouse cost F, total cost = F × warehouses + total order-km; the best number minimizes it over the results above. Solving the model directly with F at 0.5, 1 and 2 million gave the same answers.

| Cost of one warehouse (million km) | 0.5 | 0.75 | 1 | 1.5 | 2 | 3 to 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Best number of warehouses | 10 | 8 | 6 | 5 | 4 | 2 |

Near ties (under 0.5%) at 0.5, 0.75, 1 and 2 million; at 0.75 million, 8 and 7 warehouses differ by only 0.05%. Below about 0.2 million the best number could exceed 15, which was not solved.

## 7. Capacity test (`src/run_capacity_sweep.py`, 5 warehouses)

Same limit Q on every warehouse; extra total distance compared with no limit:

| Q (orders per year) | 20,000 | 17,300 | 13,000 | 10,400 | 9,500 | 8,700 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Extra distance | 0% | +2.0% | +7.7% | +13.5% | +18.9% to +19.4% | +31.2% to +34.7% |

The first four are optimal within 0.1%. The last two hit the time limit, so they are a range between a proven lower bound and the best solution found. Without limits, the São Paulo-area site serves about 45% of orders in the 5-warehouse network.
