"""FastAPI app exposing the negotiation core to agents."""

from __future__ import annotations

from fastapi import FastAPI

from app.models import (
    CounterRequest,
    CounterResponse,
    NegotiateRequest,
    NegotiateResponse,
    Offer,
    TraceEntry,
)
from app.negotiation import Party, advise_counter, run_negotiation

app = FastAPI(
    title="negotiation",
    description="Pareto-seeking multi-attribute negotiation over price and deadline.",
)


@app.get("/")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "negotiation"}


@app.post("/negotiate", response_model=NegotiateResponse)
def negotiate(req: NegotiateRequest) -> NegotiateResponse:
    """Settle a bilateral deal between a buyer and a seller in one shot."""
    buyer = Party(req.buyer.w_price, req.buyer.w_deadline, req.buyer.reservation, req.buyer.patience, "buyer")
    seller = Party(
        req.seller.w_price, req.seller.w_deadline, req.seller.reservation, req.seller.patience, "seller"
    )
    result = run_negotiation(buyer, seller, req.price_range, req.deadline_range, req.max_rounds)
    agreement = (
        Offer(price=result.agreement[0], deadline=result.agreement[1])
        if result.agreement is not None
        else None
    )
    return NegotiateResponse(
        agreement=agreement,
        buyer_utility=result.buyer_utility,
        seller_utility=result.seller_utility,
        pareto_optimal=result.pareto_optimal,
        rounds=result.rounds,
        trace=[TraceEntry(**entry) for entry in result.trace],
    )


@app.post("/counter", response_model=CounterResponse)
def counter(req: CounterRequest) -> CounterResponse:
    """Advise one agent for a single round: accept the opponent's offer or counter."""
    result = advise_counter(
        req.role,
        req.w_price,
        req.w_deadline,
        req.reservation,
        req.patience,
        req.price_range,
        req.deadline_range,
        req.round,
        req.opponent_offer.price,
        req.opponent_offer.deadline,
    )
    counter_offer = (
        Offer(price=result.counter_offer[0], deadline=result.counter_offer[1])
        if result.counter_offer is not None
        else None
    )
    return CounterResponse(
        accept=result.accept,
        counter_offer=counter_offer,
        my_utility_of_opponent_offer=result.my_utility_of_opponent_offer,
        aspiration=result.aspiration,
    )
