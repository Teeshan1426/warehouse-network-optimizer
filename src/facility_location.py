"""Discrete facility-location model (PuLP + CBC).

Excel Solver mapping:
  y[j]    binary "open site j"            -> changing cells (0/1)
  x[i][j] binary "region i served by j"   -> changing cells (0/1)
  objective                               -> target cell (minimize)
  constraints                             -> the Solver constraints box
"""
from dataclasses import dataclass

import pulp


@dataclass
class Result:
    status: str
    objective: float
    open_sites: list
    assignment: dict  # region -> site
    gap: float | None
    seconds: float


def solve(demand, dist, n_sites=None, capacity=None, fixed_cost=None,
          trip_factor=1.0, time_limit=60, rel_gap=0.0, relax=False):
    """Minimize fixed_cost*y + trip_factor*demand*distance*x.

    demand:     {region: units}
    dist:       {(region, site): distance}
    n_sites:    open exactly this many sites (None = no restriction)
    capacity:   {site: max units} or a single number for every site
    fixed_cost: {site: cost} or a single number for every site
    relax:      treat open/assign as continuous 0..1 (the LP relaxation). Its
                objective is a lower bound on the true optimum; assignments
                may be fractional, so only `objective` is meaningful.
    """
    regions = list(demand)
    sites = sorted({j for _, j in dist})
    cap = (lambda j: capacity[j]) if isinstance(capacity, dict) else (lambda j: capacity)
    fix = (lambda j: fixed_cost[j]) if isinstance(fixed_cost, dict) else (lambda j: fixed_cost or 0)

    m = pulp.LpProblem("facility_location", pulp.LpMinimize)
    kind = dict(lowBound=0, upBound=1, cat="Continuous") if relax else dict(cat="Binary")
    y = pulp.LpVariable.dicts("open", sites, **kind)
    x = pulp.LpVariable.dicts("assign", [(i, j) for i in regions for j in sites], **kind)

    m += (pulp.lpSum(fix(j) * y[j] for j in sites)
          + pulp.lpSum(trip_factor * demand[i] * dist[i, j] * x[i, j]
                       for i in regions for j in sites))

    for i in regions:                      # each region served by exactly one site
        m += pulp.lpSum(x[i, j] for j in sites) == 1
    for i in regions:                      # only open sites can serve
        for j in sites:
            m += x[i, j] <= y[j]
    if capacity is not None:               # site capacity (units per period)
        for j in sites:
            m += pulp.lpSum(demand[i] * x[i, j] for i in regions) <= cap(j) * y[j]
    if n_sites is not None:                # exactly p sites open
        m += pulp.lpSum(y[j] for j in sites) == n_sites

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit, gapRel=rel_gap)
    m.solve(solver)

    # PuLP can report status "Optimal" even when CBC stopped at the time limit
    # with only a feasible solution. sol_status tells the two apart.
    status = pulp.LpStatus[m.status]
    if m.sol_status == pulp.constants.LpSolutionOptimal:
        proven = True
    elif m.sol_status == pulp.constants.LpSolutionIntegerFeasible:
        status, proven = "Feasible (not proven optimal)", False
    else:
        if status == "Optimal":
            status = "No solution found"
        return Result(status, float("nan"), [], {}, None, m.solutionTime)
    return Result(
        status=status,
        objective=pulp.value(m.objective),
        open_sites=[j for j in sites if y[j].value() > 0.5],
        assignment={i: j for i in regions for j in sites if x[i, j].value() > 0.5},
        # Optimal with rel_gap=0 is proven exact; with rel_gap>0 it is within
        # that tolerance; a time-limited stop has an unknown gap.
        gap=(rel_gap if proven else None),
        seconds=m.solutionTime,
    )
