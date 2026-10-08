"""
Mock Banking API (FICTITIOUS data) - backend for the AgentCore Gateway module.

Exposed ONLY through Amazon API Gateway (REST, AWS_IAM authorization).
Routes:
    GET  /customers/{customer_id}/products
    GET  /customers/{customer_id}/transactions
    POST /simulations/cdt     {"amount": number, "term_days": 90|180|360|540}
    POST /simulations/loan    {"amount": number, "months": int, "rate_ea": number}
    GET  /exchange-rates
"""

import json
import logging
import os
from pathlib import Path

LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DATA = json.loads((Path(__file__).parent / "banking-api-data.json").read_text(encoding="utf-8"))
AGENT_NAME = os.environ.get("AGENT_NAME", "AgentBot")
MAX_AMOUNT = 5_000_000_000


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _get_customer(event: dict):
    customer_id = str((event.get("pathParameters") or {}).get("customer_id", "")).strip()
    return customer_id, DATA["customers"].get(customer_id)


def _parse_body(event: dict) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
        return body if isinstance(body, dict) else {}
    except json.JSONDecodeError:
        return {}


def _positive_amount(value) -> float:
    amount = float(value)
    if amount <= 0 or amount > MAX_AMOUNT:
        raise ValueError("amount must be > 0 and <= 5.000.000.000")
    return amount


def get_products(event: dict) -> dict:
    customer_id, customer = _get_customer(event)
    if not customer:
        return _response(404, {"error": f"Customer '{customer_id}' not found. Valid demo ids: {list(DATA['customers'])}"})
    return _response(200, {
        "customer_id": customer_id,
        "name": customer["name"],
        "segment": customer["segment"],
        "currency": DATA["currency"],
        "products": customer["products"],
    })


def get_transactions(event: dict) -> dict:
    customer_id, customer = _get_customer(event)
    if not customer:
        return _response(404, {"error": f"Customer '{customer_id}' not found. Valid demo ids: {list(DATA['customers'])}"})
    limit = int((event.get("queryStringParameters") or {}).get("limit", 5))
    return _response(200, {
        "customer_id": customer_id,
        "currency": DATA["currency"],
        "transactions": customer["transactions"][: max(1, min(limit, 20))],
    })


def simulate_cdt(event: dict) -> dict:
    body = _parse_body(event)
    try:
        amount = _positive_amount(body.get("amount"))
        term_days = str(int(body.get("term_days", 360)))
    except (TypeError, ValueError) as exc:
        return _response(400, {"error": f"Invalid input: {exc}"})
    rates = DATA["cdt_rates_ea"]
    if term_days not in rates:
        return _response(400, {"error": f"term_days must be one of {list(rates)}"})
    rate_ea = rates[term_days] / 100
    gross_interest = amount * ((1 + rate_ea) ** (int(term_days) / 365) - 1)
    withholding = gross_interest * DATA["cdt_withholding_pct"] / 100
    return _response(200, {
        "product": "CDT Digital (ficticio)",
        "amount": round(amount, 2),
        "term_days": int(term_days),
        "rate_ea_pct": rates[term_days],
        "gross_interest": round(gross_interest, 2),
        "withholding_tax": round(withholding, 2),
        "net_at_maturity": round(amount + gross_interest - withholding, 2),
        "currency": DATA["currency"],
        "disclaimer": "Simulacion ficticia de entrenamiento, no constituye oferta.",
    })


def simulate_loan(event: dict) -> dict:
    body = _parse_body(event)
    try:
        amount = _positive_amount(body.get("amount"))
        months = int(body.get("months", 36))
        rate_ea = float(body.get("rate_ea", 18.0)) / 100
        if not 1 <= months <= 360 or not 0 < rate_ea < 1:
            raise ValueError("months in [1, 360] and rate_ea in (0, 100)")
    except (TypeError, ValueError) as exc:
        return _response(400, {"error": f"Invalid input: {exc}"})
    monthly_rate = (1 + rate_ea) ** (1 / 12) - 1
    payment = amount * monthly_rate / (1 - (1 + monthly_rate) ** -months)
    return _response(200, {
        "amount": round(amount, 2),
        "months": months,
        "rate_ea_pct": round(rate_ea * 100, 4),
        "monthly_rate_pct": round(monthly_rate * 100, 4),
        "monthly_payment": round(payment, 2),
        "total_paid": round(payment * months, 2),
        "total_interest": round(payment * months - amount, 2),
        "currency": DATA["currency"],
        "disclaimer": "Simulacion ficticia de entrenamiento, no constituye oferta.",
    })


def get_exchange_rates(_event: dict) -> dict:
    return _response(200, {
        "base_currency": DATA["currency"],
        "rates": {k: v for k, v in DATA["exchange_rates_reference"].items() if not k.startswith("_")},
        "note": "Valores de referencia estaticos del API ficticio. Para valores en vivo use la herramienta WebSearch.",
    })


ROUTES = {
    ("GET", "/customers/{customer_id}/products"): get_products,
    ("GET", "/customers/{customer_id}/transactions"): get_transactions,
    ("POST", "/simulations/cdt"): simulate_cdt,
    ("POST", "/simulations/loan"): simulate_loan,
    ("GET", "/exchange-rates"): get_exchange_rates,
}


def handler(event, _context):
    route = (event.get("httpMethod"), event.get("resource"))
    LOGGER.info("Request route=%s caller=%s", route, (event.get("requestContext") or {}).get("identity", {}).get("userArn"))
    func = ROUTES.get(route)
    if not func:
        return _response(404, {"error": f"Route {route} not found"})
    return func(event)
