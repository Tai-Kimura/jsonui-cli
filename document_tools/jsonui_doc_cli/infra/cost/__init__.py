"""The cost simulator's calculation (plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-B).

parts.py the charges (a unit price, the month's free amount, stepped prices on the month's total); pricebook.py which
price (a person's files > the fetched cache > the bundled table); scale.py how many run and which step; formulas.py
each category's meters; engine.py the simulation and its lines. The pricing rules (infra/rules) choose the formula
and its constants per provider. Every function is pure: what it reads comes in its arguments.
"""
