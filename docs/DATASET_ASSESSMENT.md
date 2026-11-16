# Dataset assessment

What the Olist data contains, what was found when checking it, and what it can and cannot support. Audit tables are in `outputs/tables/dataset_assessment/`.

## Source

- [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle), licensed CC BY-NC-SA 4.0. Nine tables; 99,441 orders from September 2016 to October 2018.
- The raw files are not included in this repository. Only aggregated tables (no customer-level rows) are shared.

## Tables used

- **orders**: status and purchase date, to keep delivered orders purchased in 2017.
- **customers**: the delivery ZIP code prefix for each order.
- **geolocation**: latitude and longitude by ZIP code prefix (about 1 million rows).

## Why 2017 delivered orders

- 2017 is the only full calendar year; 2016 and 2018 are partial (2016 has only a few hundred orders, and orders stop in October 2018).
- Delivered orders are demand that was actually shipped. 2017 has 43,428 of them across all 27 states.

## Problems found and how they were handled

| Problem | Handling |
| --- | --- |
| Geolocation has many repeated rows (261,831 exact duplicates) and some points outside Brazil | Duplicates removed and points outside a Brazil box dropped before computing region points |
| Joining tables the wrong way multiplies rows (customers to raw geolocation would turn 99,441 records into about 15 million) | Each table is reduced to one row per key before joining; SQL totals were cross-checked with pandas |
| 114 of the 2017 orders have no usable coordinate | Excluded and counted (0.26% of orders) |
| Demand grows sharply through 2017 (750 delivered orders in January, 7,289 in November) | Noted as a limitation; the model uses annual totals |

## What the data cannot tell us

Olist's real warehouse locations, warehouse sizes or costs, road distances, routes or carrier rates. The freight value on each order is a price paid, not a cost of shipping from a chosen warehouse. That is why the candidate sites, capacity limits and warehouse costs in this project are hypothetical.

## Reproducing the audit

`src/assess_dataset.py` (with `requirements-assessment.txt`) needs the raw Olist files and a local checksum file, neither of which is included, so rebuilding the inputs from raw data is not supported as-is. The model itself runs from the prepared inputs in `data/processed/model_inputs/`.
