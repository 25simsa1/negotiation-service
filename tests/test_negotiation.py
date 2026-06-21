"""Tests for the pure-Python negotiation core."""

from __future__ import annotations

from app.negotiation import (
    Party,
    _dominates,
    advise_counter,
    aspiration,
    run_negotiation,
    utility,
)

PRICE_RANGE = (50, 150)
DEADLINE_RANGE = (1, 30)


def _buyer(reservation: float = 0.0) -> Party:
    # Price-driven: cares about a low price, barely about the deadline.
    return Party(w_price=0.9, w_deadline=0.1, reservation=reservation, patience=0.9, side="buyer")


def _seller(reservation: float = 0.0) -> Party:
    # Deadline-driven: cares about a long deadline, barely about price.
    return Party(w_price=0.1, w_deadline=0.9, reservation=reservation, patience=0.9, side="seller")


def test_agreement_is_pareto_non_dominated() -> None:
    """Independently verify the settlement is non-dominated by any exchanged bundle.

    Recomputes utilities from the test's own parties (not the code's flag) and
    checks strict dominance inline, so a broken negotiation or a wrongly-reported
    flag would both fail here.
    """
    buyer, seller = _buyer(), _seller()
    result = run_negotiation(buyer, seller, PRICE_RANGE, DEADLINE_RANGE)
    assert result.agreement is not None

    ap, ad = result.agreement
    ub_star = utility(buyer, PRICE_RANGE, DEADLINE_RANGE, ap, ad)
    us_star = utility(seller, PRICE_RANGE, DEADLINE_RANGE, ap, ad)

    exchanged = {(e["price"], e["deadline"]) for e in result.trace}
    for xp, xd in exchanged:
        if (xp, xd) == (ap, ad):
            continue
        ub_x = utility(buyer, PRICE_RANGE, DEADLINE_RANGE, xp, xd)
        us_x = utility(seller, PRICE_RANGE, DEADLINE_RANGE, xp, xd)
        no_worse = ub_x >= ub_star - 1e-9 and us_x >= us_star - 1e-9
        strictly_better = ub_x > ub_star + 1e-9 or us_x > us_star + 1e-9
        assert not (no_worse and strictly_better), f"{(xp, xd)} dominates agreement {(ap, ad)}"

    assert result.pareto_optimal is True


def test_dominates_relation() -> None:
    """The dominance helper the flag relies on is correct on hand-built bundles."""
    buyer, seller = _buyer(), _seller()
    # (50, 30): low price + long deadline -> better for BOTH than (150, 1).
    assert _dominates((50, 30), (150, 1), buyer, seller, PRICE_RANGE, DEADLINE_RANGE) is True
    assert _dominates((150, 1), (50, 30), buyer, seller, PRICE_RANGE, DEADLINE_RANGE) is False
    # (50, 1) is buyer-ideal, (150, 30) seller-ideal: incomparable either way.
    assert _dominates((50, 1), (150, 30), buyer, seller, PRICE_RANGE, DEADLINE_RANGE) is False
    assert _dominates((150, 30), (50, 1), buyer, seller, PRICE_RANGE, DEADLINE_RANGE) is False
    # A bundle never strictly dominates itself.
    assert _dominates((80, 15), (80, 15), buyer, seller, PRICE_RANGE, DEADLINE_RANGE) is False


def test_agreement_is_individually_rational() -> None:
    """Neither party settles below its reservation utility."""
    buyer = _buyer(reservation=0.2)
    seller = _seller(reservation=0.2)
    result = run_negotiation(buyer, seller, PRICE_RANGE, DEADLINE_RANGE)
    if result.agreement is None:
        return
    assert result.buyer_utility >= buyer.reservation - 1e-9
    assert result.seller_utility >= seller.reservation - 1e-9


def test_counter_accepts_ideal_offer() -> None:
    """An offer equal to the agent's ideal clears the round-0 aspiration (1.0)."""
    result = advise_counter(
        "buyer", 0.9, 0.1, 0.0, 0.9, PRICE_RANGE, DEADLINE_RANGE, round_index=0, opp_price=50, opp_deadline=1
    )
    assert result.accept is True
    assert result.counter_offer is None
    assert result.my_utility_of_opponent_offer == 1.0


def test_counter_returns_aspiration_satisfying_offer() -> None:
    """A below-aspiration offer is rejected with a counter whose own utility clears alpha."""
    party = Party(0.9, 0.1, 0.0, 0.9, "buyer")
    result = advise_counter(
        "buyer", 0.9, 0.1, 0.0, 0.9, PRICE_RANGE, DEADLINE_RANGE, round_index=1, opp_price=150, opp_deadline=30
    )
    assert result.accept is False
    assert result.counter_offer is not None
    counter_utility = utility(party, PRICE_RANGE, DEADLINE_RANGE, *result.counter_offer)
    assert counter_utility >= result.aspiration - 1e-9
    assert result.aspiration == aspiration(party, 1)


def test_negotiation_is_deterministic() -> None:
    """Identical inputs produce an identical settlement and trace (pinned golden)."""
    first = run_negotiation(_buyer(), _seller(), PRICE_RANGE, DEADLINE_RANGE)
    second = run_negotiation(_buyer(), _seller(), PRICE_RANGE, DEADLINE_RANGE)
    assert first == second
    # Golden values pin the deterministic outcome, not just call-to-call equality.
    assert first.agreement == (51, 30)
    assert first.rounds == 3
    assert round(first.buyer_utility, 3) == 0.891
    assert round(first.seller_utility, 3) == 0.901


def test_breakdown_returns_null_agreement() -> None:
    """When neither side concedes enough in the allotted rounds, there is no deal."""
    # Reservations above any jointly feasible utility force a breakdown.
    stubborn_buyer = Party(0.9, 0.1, 0.99, 0.9, "buyer")
    stubborn_seller = Party(0.1, 0.9, 0.99, 0.9, "seller")
    result = run_negotiation(stubborn_buyer, stubborn_seller, PRICE_RANGE, DEADLINE_RANGE, max_rounds=5)
    assert result.agreement is None
    assert result.pareto_optimal is False
