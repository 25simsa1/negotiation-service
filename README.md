# negotiation-service

A small HTTP service that lets two AI agents reach a **Pareto-seeking** deal over
two issues at once: **price** and **deadline**. Instead of haggling on price alone,
each side scores bundles with additive multi-attribute utility and concedes along a
monotonic schedule, countering with trade-off moves that head toward the other
party's preference. So a buyer who only cares about price and a seller who mostly
cares about the deadline can "logroll" into a deal that is good for both.

The `pareto_optimal` flag means the agreement is **non-dominated by any bundle the
two parties exchanged in the session** — a check against trace evidence, not a proof
of global optimality over the whole feasible grid. The trade-off strategy seeks the
frontier but, like any alternating-offers heuristic under incomplete information,
does not guarantee it.

The negotiation math is a standalone re-implementation of my NANDA Town warm-up
`ParetoNegotiation` plugin. This service depends on nothing from that project.

## How it works

Each party has additive utility `u = w_price * f_price + w_deadline * f_deadline`
(weights sum to 1), where each value function is normalized to `[0, 1]` over the
feasible integer ranges. A **buyer** prefers a low price and short deadline; a
**seller** prefers the opposite. Concession follows
`aspiration(t) = reservation + (1 - reservation) * patience ** t` (monotonic).
Below aspiration, a party counters with the grid bundle whose own utility still
clears aspiration and whose normalized distance to the opponent's offer is smallest
(Faratin, Sierra & Jennings similarity-based trade-off).

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/

curl -X POST localhost:8000/negotiate \
  -H 'content-type: application/json' \
  -d '{
    "buyer":  {"w_price": 0.9, "w_deadline": 0.1, "reservation": 0.0, "patience": 0.9},
    "seller": {"w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 0.9},
    "price_range": [50, 150],
    "deadline_range": [1, 30],
    "max_rounds": 12
  }'

curl -X POST localhost:8000/counter \
  -H 'content-type: application/json' \
  -d '{
    "role": "seller",
    "w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 0.9,
    "price_range": [50, 150], "deadline_range": [1, 30],
    "round": 1,
    "opponent_offer": {"price": 60, "deadline": 30}
  }'
```

## Endpoints

- `GET /` — health/liveness, returns `{"status": "ok", "service": "negotiation"}`.
- `POST /negotiate` — one-shot bilateral settlement; returns the agreed bundle,
  both utilities, whether it is non-dominated by any exchanged bundle, and the full
  exchange trace. (`agreement` is `null` on breakdown, in which case the utilities
  and `pareto_optimal` are placeholders.)
- `POST /counter` — single-round advice for one agent: accept the opponent's offer
  or return a trade-off counter.

See [SKILL.md](SKILL.md) for the agent-facing contract with example responses.

## Tests

```bash
pytest -q
```

## Deploy to Render

This repo ships a [`render.yaml`](render.yaml) blueprint. On
[Render](https://render.com): **New → Blueprint**, point it at this repo, and deploy
the free web service. Render installs `requirements.txt` and starts
`uvicorn app.main:app` on `$PORT`; `runtime.txt` pins Python 3.12.8. After it goes
live, copy the service URL into the `REPLACE_WITH_RENDER_URL` placeholder in
`SKILL.md`.

## Determinism

No wall-clock and no RNG: scoring is pure arithmetic and the concession schedule is
fixed, so the same request always yields the same agreement and trace.
