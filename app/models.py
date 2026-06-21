"""Pydantic v2 request/response models for the negotiation service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_WEIGHT_TOL = 1e-6

# Cap the feasible grid size. The negotiation enumerates every (price, deadline)
# cell, so an unbounded range would let one request hang or exhaust memory. The
# documented ranges (e.g. 101 x 30) are far under this.
_MAX_GRID_CELLS = 200_000


class PartyParams(BaseModel):
    """One party's utility weights and concession parameters."""

    w_price: float = Field(allow_inf_nan=False)
    w_deadline: float = Field(allow_inf_nan=False)
    reservation: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    patience: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> PartyParams:
        if abs(self.w_price + self.w_deadline - 1.0) > _WEIGHT_TOL:
            msg = "w_price and w_deadline must sum to 1"
            raise ValueError(msg)
        return self


class Offer(BaseModel):
    """A (price, deadline) bundle."""

    price: int
    deadline: int


class TraceEntry(BaseModel):
    """One recorded offer in the exchange."""

    round: int
    by: Literal["buyer", "seller"]
    price: int
    deadline: int


def _check_ranges(price_range: tuple[int, int], deadline_range: tuple[int, int]) -> None:
    if price_range[0] >= price_range[1]:
        msg = "price_range must have lo < hi"
        raise ValueError(msg)
    if deadline_range[0] >= deadline_range[1]:
        msg = "deadline_range must have lo < hi"
        raise ValueError(msg)
    cells = (price_range[1] - price_range[0] + 1) * (deadline_range[1] - deadline_range[0] + 1)
    if cells > _MAX_GRID_CELLS:
        msg = f"price_range x deadline_range grid too large ({cells} > {_MAX_GRID_CELLS} cells)"
        raise ValueError(msg)


class NegotiateRequest(BaseModel):
    """Request for a one-shot bilateral settlement."""

    buyer: PartyParams
    seller: PartyParams
    price_range: tuple[int, int]
    deadline_range: tuple[int, int]
    max_rounds: int = Field(default=12, ge=1)

    @model_validator(mode="after")
    def _valid_ranges(self) -> NegotiateRequest:
        _check_ranges(self.price_range, self.deadline_range)
        return self


class NegotiateResponse(BaseModel):
    """Result of a one-shot bilateral settlement.

    ``buyer_utility``, ``seller_utility`` and ``pareto_optimal`` are only
    meaningful when ``agreement`` is non-null; on a breakdown they are
    placeholders and ``agreement`` is the authoritative no-deal signal.
    """

    agreement: Offer | None
    buyer_utility: float
    seller_utility: float
    pareto_optimal: bool
    rounds: int
    trace: list[TraceEntry]


class CounterRequest(BaseModel):
    """Request for single-round strategy advice for one agent."""

    role: Literal["buyer", "seller"]
    w_price: float = Field(allow_inf_nan=False)
    w_deadline: float = Field(allow_inf_nan=False)
    reservation: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    patience: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    price_range: tuple[int, int]
    deadline_range: tuple[int, int]
    round: int = Field(ge=0)
    opponent_offer: Offer

    @model_validator(mode="after")
    def _valid(self) -> CounterRequest:
        if abs(self.w_price + self.w_deadline - 1.0) > _WEIGHT_TOL:
            msg = "w_price and w_deadline must sum to 1"
            raise ValueError(msg)
        _check_ranges(self.price_range, self.deadline_range)
        return self


class CounterResponse(BaseModel):
    """A single agent's accept/counter advice for one round."""

    accept: bool
    counter_offer: Offer | None
    my_utility_of_opponent_offer: float
    aspiration: float
