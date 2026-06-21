"""FastAPI integration tests using the TestClient."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import PartyParams
from app.negotiation import Party, utility

client = TestClient(app)

PRICE_RANGE = (50, 150)
DEADLINE_RANGE = (1, 30)

_NEGOTIATE_BODY: dict[str, Any] = {
    "buyer": {"w_price": 0.9, "w_deadline": 0.1, "reservation": 0.0, "patience": 0.9},
    "seller": {"w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 0.9},
    "price_range": [50, 150],
    "deadline_range": [1, 30],
    "max_rounds": 12,
}

_COUNTER_ACCEPT_BODY: dict[str, Any] = {
    "role": "seller",
    "w_price": 0.1,
    "w_deadline": 0.9,
    "reservation": 0.0,
    "patience": 0.9,
    "price_range": [50, 150],
    "deadline_range": [1, 30],
    "round": 1,
    "opponent_offer": {"price": 60, "deadline": 30},
}


def test_health() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "negotiation"}


def test_negotiate_returns_valid_agreement() -> None:
    resp = client.post("/negotiate", json=_NEGOTIATE_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["agreement"] == {"price": 51, "deadline": 30}  # deterministic golden
    assert 0.0 <= body["buyer_utility"] <= 1.0
    assert 0.0 <= body["seller_utility"] <= 1.0
    assert body["pareto_optimal"] is True
    assert body["rounds"] >= 1
    assert len(body["trace"]) >= 2


def test_negotiate_is_deterministic_over_http() -> None:
    first = client.post("/negotiate", json=_NEGOTIATE_BODY).json()
    second = client.post("/negotiate", json=_NEGOTIATE_BODY).json()
    assert first == second


def test_counter_accepts_good_offer() -> None:
    resp = client.post("/counter", json=_COUNTER_ACCEPT_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["accept"] is True
    assert body["counter_offer"] is None
    assert body["my_utility_of_opponent_offer"] >= body["aspiration"]


def test_counter_rejects_and_returns_aspiration_satisfying_counter() -> None:
    # Seller's worst offer (low price, short deadline) is below aspiration -> counter.
    body_req = {**_COUNTER_ACCEPT_BODY, "opponent_offer": {"price": 50, "deadline": 1}}
    resp = client.post("/counter", json=body_req)
    assert resp.status_code == 200
    body = resp.json()
    assert body["accept"] is False
    assert body["counter_offer"] is not None
    seller = Party(0.1, 0.9, 0.0, 0.9, "seller")
    counter = (body["counter_offer"]["price"], body["counter_offer"]["deadline"])
    assert utility(seller, PRICE_RANGE, DEADLINE_RANGE, *counter) >= body["aspiration"] - 1e-9


def test_bad_weights_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "buyer": {"w_price": 0.7, "w_deadline": 0.7, "reservation": 0.0, "patience": 0.9}}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422
    assert any("must sum to 1" in e["msg"] for e in resp.json()["detail"])


def test_bad_range_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "price_range": [150, 50]}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422
    assert any("lo < hi" in e["msg"] for e in resp.json()["detail"])


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_weight_rejected_by_model(bad_value: float) -> None:
    # Non-finite floats are not valid JSON, so they cannot arrive over HTTP from a
    # standard client; the model still rejects them so they can never reach the math.
    with pytest.raises(ValidationError):
        PartyParams(w_price=bad_value, w_deadline=0.5, reservation=0.0, patience=0.9)


def test_reservation_out_of_range_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "buyer": {"w_price": 0.9, "w_deadline": 0.1, "reservation": 1.5, "patience": 0.9}}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422


def test_patience_out_of_range_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "seller": {"w_price": 0.1, "w_deadline": 0.9, "reservation": 0.0, "patience": 1.5}}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422


def test_oversized_range_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "price_range": [0, 100000]}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422
    assert any("grid too large" in e["msg"] for e in resp.json()["detail"])


def test_non_positive_max_rounds_returns_422() -> None:
    bad = {**_NEGOTIATE_BODY, "max_rounds": 0}
    resp = client.post("/negotiate", json=bad)
    assert resp.status_code == 422


def test_negative_round_returns_422() -> None:
    bad = {**_COUNTER_ACCEPT_BODY, "round": -1}
    resp = client.post("/counter", json=bad)
    assert resp.status_code == 422
