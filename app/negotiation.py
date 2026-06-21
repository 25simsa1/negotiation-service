"""Pure-Python multi-attribute negotiation core (no framework, no external deps).

Each party scores a (price, deadline) bundle with additive multi-attribute
utility ``u = w_price * f_price + w_deadline * f_deadline`` (Keeney & Raiffa),
where each value function is normalized to ``[0, 1]`` over the integer feasible
ranges. A buyer wants a low price and short deadline; a seller wants the mirror.

Concession follows a monotonic aspiration schedule
``alpha(t) = reservation + (1 - reservation) * patience ** t`` (Rosenschein &
Zlotkin's Monotonic Concession Protocol / Zeuthen). When an opponent offer is
below aspiration, a party counters with the grid bundle whose own utility still
clears aspiration and whose normalized squared distance to the opponent offer is
minimal (Faratin, Sierra & Jennings 2002 similarity-based trade-off).

This re-implements the logic of the NANDA Town ParetoNegotiation plugin as a
standalone module; it imports nothing from that project.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-9

TraceEntry = dict[str, int | str]


@dataclass(frozen=True)
class Party:
    """One side's private utility configuration."""

    w_price: float
    w_deadline: float
    reservation: float
    patience: float
    side: str  # "buyer" or "seller"


@dataclass
class NegotiationResult:
    """Outcome of a one-shot bilateral settlement."""

    agreement: tuple[int, int] | None
    buyer_utility: float
    seller_utility: float
    pareto_optimal: bool
    rounds: int
    trace: list[TraceEntry]


@dataclass
class CounterResult:
    """A single agent's advice for one round."""

    accept: bool
    counter_offer: tuple[int, int] | None
    my_utility_of_opponent_offer: float
    aspiration: float


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def utility(
    party: Party,
    price_range: tuple[int, int],
    deadline_range: tuple[int, int],
    price: int,
    deadline: int,
) -> float:
    """Additive multi-attribute utility for a (price, deadline) bundle, clamped to range."""
    plo, phi = price_range
    dlo, dhi = deadline_range
    p = _clamp(price, plo, phi)
    d = _clamp(deadline, dlo, dhi)
    if party.side == "buyer":
        f_price = (phi - p) / (phi - plo)
        f_deadline = (dhi - d) / (dhi - dlo)
    else:
        f_price = (p - plo) / (phi - plo)
        f_deadline = (d - dlo) / (dhi - dlo)
    return party.w_price * f_price + party.w_deadline * f_deadline


def aspiration(party: Party, t: int) -> float:
    """Monotonic-concession aspiration floor for round ``t``."""
    return party.reservation + (1.0 - party.reservation) * (party.patience**t)


def _grid(price_range: tuple[int, int], deadline_range: tuple[int, int]) -> list[tuple[int, int]]:
    plo, phi = price_range
    dlo, dhi = deadline_range
    return [(p, d) for p in range(plo, phi + 1) for d in range(dlo, dhi + 1)]


def tradeoff_counter(
    party: Party,
    price_range: tuple[int, int],
    deadline_range: tuple[int, int],
    alpha: float,
    opp_price: int,
    opp_deadline: int,
    grid: list[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """The aspiration-satisfying grid bundle nearest the opponent's offer (FSJ trade-off).

    Among bundles whose own utility is at least ``alpha``, pick the one minimizing
    normalized squared distance to the opponent's offer; tie-break on lower price
    then lower deadline. If no bundle clears aspiration, return the most-preferred
    bundle for this party. ``grid`` may be precomputed and passed in to avoid
    rebuilding it every round.
    """
    plo, phi = price_range
    dlo, dhi = deadline_range
    p_span = phi - plo
    d_span = dhi - dlo
    op = _clamp(opp_price, plo, phi)
    od = _clamp(opp_deadline, dlo, dhi)

    if grid is None:
        grid = _grid(price_range, deadline_range)
    acceptable = [
        (p, d) for (p, d) in grid if utility(party, price_range, deadline_range, p, d) >= alpha
    ]
    if acceptable:
        return min(
            acceptable,
            key=lambda b: (((b[0] - op) / p_span) ** 2 + ((b[1] - od) / d_span) ** 2, b[0], b[1]),
        )
    return min(
        grid,
        key=lambda b: (-utility(party, price_range, deadline_range, b[0], b[1]), b[0], b[1]),
    )


def _dominates(
    x: tuple[int, int],
    y: tuple[int, int],
    buyer: Party,
    seller: Party,
    price_range: tuple[int, int],
    deadline_range: tuple[int, int],
) -> bool:
    """Bundle ``x`` Pareto-dominates ``y``: no worse for either party, strictly better for one."""
    ubx = utility(buyer, price_range, deadline_range, *x)
    usx = utility(seller, price_range, deadline_range, *x)
    uby = utility(buyer, price_range, deadline_range, *y)
    usy = utility(seller, price_range, deadline_range, *y)
    no_worse = ubx >= uby - _EPS and usx >= usy - _EPS
    strictly_better = ubx > uby + _EPS or usx > usy + _EPS
    return no_worse and strictly_better


def run_negotiation(
    buyer: Party,
    seller: Party,
    price_range: tuple[int, int],
    deadline_range: tuple[int, int],
    max_rounds: int = 12,
) -> NegotiationResult:
    """Run an alternating-offers settlement between two Pareto-seeking parties.

    Both sides open from their best-for-self bundle, then alternately respond to
    the other's latest offer: accept once it clears aspiration, else counter with
    a trade-off move. Returns the settled bundle (or ``None`` on breakdown), both
    utilities, the full exchange trace, and whether the agreement is non-dominated
    by any bundle exchanged in the session.
    """
    plo, phi = price_range
    dlo, dhi = deadline_range
    grid = _grid(price_range, deadline_range)  # built once, reused every round
    buyer_last = (plo, dlo)  # buyer's best-for-self opener
    seller_last = (phi, dhi)  # seller's best-for-self opener
    exchanged: list[tuple[int, int]] = [buyer_last, seller_last]
    trace: list[TraceEntry] = [
        {"round": 0, "by": "buyer", "price": plo, "deadline": dlo},
        {"round": 0, "by": "seller", "price": phi, "deadline": dhi},
    ]

    agreement: tuple[int, int] | None = None
    buyer_round = 0
    seller_round = 0
    rounds_elapsed = 0

    for r in range(1, max_rounds + 1):
        rounds_elapsed = r

        alpha_b = aspiration(buyer, buyer_round)
        if utility(buyer, price_range, deadline_range, *seller_last) >= alpha_b:
            agreement = seller_last
            break
        buyer_last = tradeoff_counter(buyer, price_range, deadline_range, alpha_b, *seller_last, grid=grid)
        exchanged.append(buyer_last)
        trace.append({"round": r, "by": "buyer", "price": buyer_last[0], "deadline": buyer_last[1]})
        buyer_round += 1

        alpha_s = aspiration(seller, seller_round)
        if utility(seller, price_range, deadline_range, *buyer_last) >= alpha_s:
            agreement = buyer_last
            break
        seller_last = tradeoff_counter(seller, price_range, deadline_range, alpha_s, *buyer_last, grid=grid)
        exchanged.append(seller_last)
        trace.append(
            {"round": r, "by": "seller", "price": seller_last[0], "deadline": seller_last[1]}
        )
        seller_round += 1

    if agreement is None:
        return NegotiationResult(None, 0.0, 0.0, False, rounds_elapsed, trace)

    buyer_utility = utility(buyer, price_range, deadline_range, *agreement)
    seller_utility = utility(seller, price_range, deadline_range, *agreement)
    pareto_optimal = not any(
        b != agreement and _dominates(b, agreement, buyer, seller, price_range, deadline_range)
        for b in exchanged
    )
    return NegotiationResult(
        agreement, buyer_utility, seller_utility, pareto_optimal, rounds_elapsed, trace
    )


def advise_counter(
    role: str,
    w_price: float,
    w_deadline: float,
    reservation: float,
    patience: float,
    price_range: tuple[int, int],
    deadline_range: tuple[int, int],
    round_index: int,
    opp_price: int,
    opp_deadline: int,
) -> CounterResult:
    """Advise one agent for a single round: accept the opponent's offer or counter.

    Accept iff the offer's own-utility clears this round's aspiration; otherwise
    return the FSJ trade-off counter and ``accept=False``.
    """
    party = Party(w_price, w_deadline, reservation, patience, role)
    alpha = aspiration(party, round_index)
    u_opp = utility(party, price_range, deadline_range, opp_price, opp_deadline)
    if u_opp >= alpha:
        return CounterResult(True, None, u_opp, alpha)
    counter = tradeoff_counter(party, price_range, deadline_range, alpha, opp_price, opp_deadline)
    return CounterResult(False, counter, u_opp, alpha)
