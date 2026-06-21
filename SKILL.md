# Negotiation Skill

Get a fair deal between two parties over **price** and **deadline** at once — describe
each side in plain terms and the service returns terms that are good for both.

## Base URL

```
https://negotiation-service.onrender.com
```

Note: this runs on a free host and may take up to ~60 seconds to wake on the first request after it has been idle.

## Recommended: `POST /deal`

The easy front door. Describe the buyer and seller in plain language — no utility
theory — and get back a fair deal. Each side gives three things:

- **buyer**: `budget` (most it will pay), `needed_by_days` (when it needs delivery),
  `cares_most_about` one of `"price"`, `"speed"`, `"both"`.
- **seller**: `min_price` (least it will accept), `preferred_deadline_days` (the
  deadline it would like), `cares_most_about` one of `"price"`, `"deadline"`, `"both"`.

### Worked example

A buyer agent has a budget of **120** and needs delivery **within 7 days**, and cares
most about **price**. The seller **won't go below 80** and **prefers a 30-day
deadline**, and cares most about the **deadline**.

```bash
curl -X POST https://negotiation-service.onrender.com/deal \
  -H 'content-type: application/json' \
  -d '{
    "buyer":  {"budget": 120, "needed_by_days": 7, "cares_most_about": "price"},
    "seller": {"min_price": 80, "preferred_deadline_days": 30, "cares_most_about": "deadline"}
  }'
```

```json
{
  "deal": {"price": 82, "deadline_days": 29},
  "summary": "Agreed on a price of 82 with delivery in 29 days; both sides do better than walking away.",
  "fair": true,
  "buyer_satisfaction": 0.814,
  "seller_satisfaction": 0.821
}
```

The price-focused buyer gets a price near the seller's floor, and the deadline-focused
seller gets a long deadline — each gives ground on the thing it cares less about. If
the buyer's budget is below the seller's minimum there is no overlap, so `deal` is
`null` and `summary` explains why:

```json
{
  "deal": null,
  "summary": "No deal: the buyer's budget (50) is below the seller's minimum (80).",
  "fair": false,
  "buyer_satisfaction": 0.0,
  "seller_satisfaction": 0.0
}
```

`fair` is `true` when no other bundle the two sides exchanged would be better for both
(trace evidence, not a global-optimality proof). `buyer_satisfaction` and
`seller_satisfaction` are each 0–1.

## Advanced

For callers who want to set utility weights directly or negotiate round by round.
Both parties score a bundle with `w_price * f_price + w_deadline * f_deadline`
(weights sum to 1), concede on a schedule `reservation + (1 - reservation) * patience ** round`,
and trade off toward the opponent's offer.

### `POST /negotiate` — one-shot settlement with explicit weights

```bash
curl -X POST https://negotiation-service.onrender.com/negotiate \
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

`agreement` is `null` on breakdown (then the utilities and `pareto_optimal` are
placeholders).

### `POST /counter` — one round of advice for a single agent

Pass your own utility, the current `round` (0-indexed), and the opponent's latest
offer; the service says whether to accept and, if not, what to counter with.

```bash
curl -X POST https://negotiation-service.onrender.com/counter \
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

## How an agent should use this

1. **For a fair one-shot deal**, call `POST /deal` with both parties described in
   plain terms (budget / needed-by / what they care about). Use the returned `deal`;
   `fair: true` means no exchanged bundle beats it for both sides.
2. **To negotiate live against another party**, call `POST /counter` each round with
   your own utility and the opponent's latest offer; if `accept` is `true`, take the
   offer, otherwise send `counter_offer` and repeat with `round + 1`.
3. **Use `POST /negotiate`** only if you want to control the utility weights directly
   and get the whole settlement in one call.
