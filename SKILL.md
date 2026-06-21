# Negotiation Skill

Reach a Pareto-seeking deal with another agent over **price** and **deadline** at
once, instead of haggling on price alone. The returned `pareto_optimal` flag means
the agreement is non-dominated by any bundle the parties exchanged (trace evidence,
not a global-optimality proof).

## Base URL

```
REPLACE_WITH_RENDER_URL
```

## Endpoints

### `GET /` — health

```bash
curl REPLACE_WITH_RENDER_URL/
```

```json
{"status": "ok", "service": "negotiation"}
```

### `POST /negotiate` — settle a deal in one shot

Give both parties' utility weights (each pair must sum to 1), their reservation
(no-deal floor) and patience, plus the feasible integer ranges. The service runs the
full bilateral exchange and returns the agreed bundle, both utilities, whether the
deal is non-dominated by any exchanged bundle, and the trace.

```bash
curl -X POST REPLACE_WITH_RENDER_URL/negotiate \
  -H 'content-type: application/json' \
  -d '{
    "buyer":  {"w_price": 0.9, "w_deadline": 0.1, "reservation": 0.0, "patience": 0.9},
    "seller": {"w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 0.9},
    "price_range": [50, 150],
    "deadline_range": [1, 30],
    "max_rounds": 12
  }'
```

```json
{
  "agreement": {"price": 51, "deadline": 30},
  "buyer_utility": 0.891,
  "seller_utility": 0.901,
  "pareto_optimal": true,
  "rounds": 3,
  "trace": [
    {"round": 0, "by": "buyer", "price": 50, "deadline": 1},
    {"round": 0, "by": "seller", "price": 150, "deadline": 30},
    {"round": 1, "by": "buyer", "price": 50, "deadline": 1},
    {"round": 1, "by": "seller", "price": 150, "deadline": 30},
    {"round": 2, "by": "buyer", "price": 51, "deadline": 27},
    {"round": 2, "by": "seller", "price": 51, "deadline": 30}
  ]
}
```

`agreement` is `null` if the parties break down without a deal.

### `POST /counter` — one round of advice for a single agent

For live, turn-by-turn negotiation: pass your own utility, the current `round`
(0-indexed), and the opponent's latest offer. The service tells you whether to
accept and, if not, what to counter with.

```bash
curl -X POST REPLACE_WITH_RENDER_URL/counter \
  -H 'content-type: application/json' \
  -d '{
    "role": "seller",
    "w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 0.9,
    "price_range": [50, 150], "deadline_range": [1, 30],
    "round": 1,
    "opponent_offer": {"price": 60, "deadline": 30}
  }'
```

```json
{
  "accept": true,
  "counter_offer": null,
  "my_utility_of_opponent_offer": 0.91,
  "aspiration": 0.9
}
```

When `accept` is `false`, `counter_offer` holds the bundle to send back.

## How the agent should use this

1. **To strike a fair deal in one call**, POST `/negotiate` with both parties'
   weights, reservations, patience, and the price/deadline ranges. Use the returned
   `agreement`; `pareto_optimal: true` confirms no exchanged bundle beats it for both
   sides.
2. **To negotiate live against another agent**, call POST `/counter` each round with
   your own utility, the current `round`, and the opponent's latest offer. If
   `accept` is `true`, take the opponent's offer; otherwise send `counter_offer`,
   increment `round`, and repeat until someone accepts.
3. **Before relying on the service**, GET `/` to confirm it is live.
