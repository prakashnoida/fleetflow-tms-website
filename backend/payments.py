"""Online invoice payments through PayPal (Orders v2) and Razorpay (Orders + Checkout).

Flow for both gateways:
  1. Browser asks  POST /api/loads/{id}/checkout {provider}  -> server creates a gateway order for the
     exact invoice amount (computed here, never trusted from the browser) and stores it in `payments`.
  2. Browser opens the gateway's checkout (PayPal Buttons / Razorpay Checkout) for that order.
  3. Browser reports back -> server confirms with the gateway itself:
       PayPal   : POST /v2/checkout/orders/{id}/capture, then checks status + amount + currency
       Razorpay : HMAC-SHA256(order_id|payment_id) signature check, then GET /v1/payments/{id}
                  (captures it if the account does not auto-capture) and checks amount + currency
  4. Only then is the invoice marked Paid. Webhooks (optional) do the same if the browser never returns.

Gateway HTTP calls are made OUTSIDE the database lock so a slow gateway never blocks other users.
Standard library only. Keys come from environment variables or a `.env` file in the project root.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .services import ApiError, add_log, get_load, miles

ROOT = Path(__file__).resolve().parent.parent
FUEL_SURCHARGE_PER_MILE = 0.48  # same as the billing screen: total = linehaul + miles * 0.48
HTTP_TIMEOUT = 20
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF", "TWD"}  # currencies without minor units


# ---------------------------------------------------------------- configuration
def load_env_file(path=ROOT / ".env"):
    """Minimal .env reader: KEY=VALUE lines, # comments. Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name, default=""):
    return os.environ.get(name, default).strip()


def paypal_enabled():
    return bool(env("PAYPAL_CLIENT_ID") and env("PAYPAL_CLIENT_SECRET"))


def razorpay_enabled():
    return bool(env("RAZORPAY_KEY_ID") and env("RAZORPAY_KEY_SECRET"))


def paypal_base():
    return "https://api-m.paypal.com" if env("PAYPAL_MODE", "sandbox").lower() == "live" else "https://api-m.sandbox.paypal.com"


def currency():
    return env("PAYMENT_CURRENCY", "USD").upper()


def fx_rate():
    """Multiplier from the TMS's USD invoice amount to PAYMENT_CURRENCY (e.g. 83.2 for USD->INR)."""
    try:
        rate = float(env("PAYMENT_FX_RATE", "1") or 1)
    except ValueError:
        raise ApiError("PAYMENT_FX_RATE must be a number", 500)
    if rate <= 0:
        raise ApiError("PAYMENT_FX_RATE must be positive", 500)
    return rate


def public_config(_con=None):
    """What the browser needs to open a checkout. Never includes secrets."""
    return {
        "currency": currency(),
        "fxRate": fx_rate(),
        "paypal": {"enabled": paypal_enabled(), "clientId": env("PAYPAL_CLIENT_ID") if paypal_enabled() else None,
                   "mode": env("PAYPAL_MODE", "sandbox").lower()},
        "razorpay": {"enabled": razorpay_enabled(), "keyId": env("RAZORPAY_KEY_ID") if razorpay_enabled() else None,
                     "merchant": env("RAZORPAY_MERCHANT_NAME", "FleetFlow TMS")},
    }


# ---------------------------------------------------------------- money
def minor_units(code):
    return 0 if code in ZERO_DECIMAL else 2


def invoice_amount_minor(con, load):
    """Invoice total in the payment currency's smallest unit (cents / paise)."""
    usd = load["rate"] + miles(con, load["origin"], load["dest"]) * FUEL_SURCHARGE_PER_MILE
    return int(round(usd * fx_rate() * 10 ** minor_units(currency())))


def to_decimal_str(amount_minor, code):
    d = minor_units(code)
    return f"{amount_minor / 10 ** d:.{d}f}"


def from_decimal_str(value, code):
    return int(round(float(value) * 10 ** minor_units(code)))


# ---------------------------------------------------------------- HTTP
def _http(method, url, headers=None, body=None, form=None):
    """Send a request, return (status, parsed JSON). Replaced by a fake in the tests."""
    data = None
    headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = form.encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except ValueError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ApiError(f"Could not reach the payment gateway: {getattr(e, 'reason', e)}", 502)


def _gateway_error(name, status, data):
    msg = (data.get("message") or (data.get("error") or {}).get("description")
           or data.get("error_description") or data.get("name") or f"HTTP {status}")
    details = data.get("details")
    if isinstance(details, list) and details:
        msg += f" ({details[0].get('issue') or details[0].get('description', '')})"
    return ApiError(f"{name} error: {msg}", 502)


# ---------------------------------------------------------------- PayPal client
_paypal_token = {"value": None, "expires": 0}


def paypal_token():
    if _paypal_token["value"] and time.time() < _paypal_token["expires"] - 60:
        return _paypal_token["value"]
    basic = base64.b64encode(f"{env('PAYPAL_CLIENT_ID')}:{env('PAYPAL_CLIENT_SECRET')}".encode()).decode()
    status, data = _http("POST", paypal_base() + "/v1/oauth2/token",
                         headers={"Authorization": f"Basic {basic}"}, form="grant_type=client_credentials")
    if status != 200 or "access_token" not in data:
        raise _gateway_error("PayPal", status, data)
    _paypal_token.update(value=data["access_token"], expires=time.time() + int(data.get("expires_in", 300)))
    return data["access_token"]


def paypal_call(method, path, body=None, request_id=None):
    headers = {"Authorization": f"Bearer {paypal_token()}"}
    if request_id:
        headers["PayPal-Request-Id"] = request_id  # makes retries idempotent on PayPal's side
    return _http(method, paypal_base() + path, headers=headers, body=body)


# ---------------------------------------------------------------- Razorpay client
def razorpay_call(method, path, body=None):
    basic = base64.b64encode(f"{env('RAZORPAY_KEY_ID')}:{env('RAZORPAY_KEY_SECRET')}".encode()).decode()
    return _http(method, "https://api.razorpay.com/v1" + path, headers={"Authorization": f"Basic {basic}"}, body=body)


def razorpay_signature_ok(order_id, payment_id, signature):
    expected = hmac.new(env("RAZORPAY_KEY_SECRET").encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def razorpay_webhook_signature_ok(raw_body, signature):
    secret = env("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# ---------------------------------------------------------------- database steps (run inside a transaction)
def _prepare(con, load_id, provider):
    if provider not in ("paypal", "razorpay"):
        raise ApiError("Unknown payment provider")
    if provider == "paypal" and not paypal_enabled():
        raise ApiError("PayPal is not configured. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to .env")
    if provider == "razorpay" and not razorpay_enabled():
        raise ApiError("Razorpay is not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env")
    load = get_load(con, load_id)
    if load["inv_st"] != "Open":
        raise ApiError("This load has no open invoice to pay")
    amount = invoice_amount_minor(con, load)
    if amount <= 0:
        raise ApiError("Invoice amount must be positive")
    if provider == "razorpay" and amount < 100:
        raise ApiError("Razorpay needs an amount of at least 1.00")
    return {"load_id": load_id, "inv_no": load["inv_no"], "cust": load["cust"], "amount": amount,
            "currency": currency(), "lane": f"{load['origin']} → {load['dest']}"}


def _record_order(con, provider, info, order_id):
    con.execute("INSERT INTO payments (load_id,provider,order_id,amount,currency,status,created_at) VALUES (?,?,?,?,?,?,?)",
                (info["load_id"], provider, order_id, info["amount"], info["currency"], "created", int(time.time())))
    add_log(con, "Payments", "OUT", f"{provider.title()} order", info["load_id"], "Success",
            f"{order_id} created for {to_decimal_str(info['amount'], info['currency'])} {info['currency']} ({info['inv_no']})")


def _payment_row(con, provider, order_id):
    row = con.execute("SELECT * FROM payments WHERE provider=? AND order_id=?", (provider, order_id)).fetchone()
    if not row:
        raise ApiError("Unknown payment order", 404)
    return row


def _mark_paid(con, provider, order_id, payment_id, amount, code, source="checkout"):
    """Idempotent: the browser callback and the webhook may both arrive."""
    row = _payment_row(con, provider, order_id)
    if row["status"] == "paid":
        return {"ok": True, "toast": f"Payment already recorded ({row['payment_id']})", "alreadyPaid": True}
    if amount != row["amount"] or code != row["currency"]:
        con.execute("UPDATE payments SET status='failed', error=? WHERE id=?",
                    (f"amount mismatch: got {amount} {code}", row["id"]))
        add_log(con, "Payments", "IN", f"{provider.title()} payment", row["load_id"], "Error",
                f"Amount mismatch on {order_id}: expected {row['amount']} {row['currency']}, got {amount} {code}")
        raise ApiError("Paid amount does not match the invoice. Payment not applied.", 409)
    con.execute("UPDATE payments SET status='paid', payment_id=?, paid_at=? WHERE id=?",
                (payment_id, int(time.time()), row["id"]))
    load = get_load(con, row["load_id"])
    if load["inv_st"] == "Open":
        con.execute("UPDATE loads SET inv_st='Paid' WHERE id=?", (row["load_id"],))
    add_log(con, "Payments", "IN", f"{provider.title()} payment", row["load_id"], "Success",
            f"{payment_id} captured – {to_decimal_str(amount, code)} {code} via {source}; {load['inv_no']} closed")
    return {"ok": True, "toast": f"Payment received – {load['inv_no']} paid via {provider.title()}"}


def _mark_failed(con, provider, order_id, reason):
    row = con.execute("SELECT * FROM payments WHERE provider=? AND order_id=?", (provider, order_id)).fetchone()
    if row and row["status"] == "created":
        con.execute("UPDATE payments SET status='failed', error=? WHERE id=?", (reason[:300], row["id"]))
        add_log(con, "Payments", "IN", f"{provider.title()} payment", row["load_id"], "Error", reason[:300])


def list_payments(con):
    return [dict(r) for r in con.execute(
        "SELECT id,load_id,provider,order_id,payment_id,amount,currency,status,error,created_at,paid_at FROM payments ORDER BY id DESC")]


# ---------------------------------------------------------------- orchestration (run = app.run: one transaction per call)
def create_checkout(run, load_id, provider):
    info = run(_prepare, load_id, provider)
    value = to_decimal_str(info["amount"], info["currency"])
    if provider == "paypal":
        status, data = paypal_call("POST", "/v2/checkout/orders", {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": info["load_id"], "custom_id": info["load_id"],
                "description": f"FleetFlow {info['inv_no']} · {info['load_id']} · {info['lane']}"[:127],
                "amount": {"currency_code": info["currency"], "value": value},
            }],
            "application_context": {"brand_name": env("PAYPAL_BRAND_NAME", "FleetFlow TMS"),
                                    "shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW"},
        })
        if status not in (200, 201) or "id" not in data:
            raise _gateway_error("PayPal", status, data)
        order_id = data["id"]
    else:
        status, data = razorpay_call("POST", "/orders", {
            "amount": info["amount"], "currency": info["currency"], "receipt": f"{info['inv_no']}-{int(time.time())}"[:40],
            "notes": {"load_id": info["load_id"], "invoice": info["inv_no"], "customer": info["cust"][:200]},
        })
        if status != 200 or "id" not in data:
            raise _gateway_error("Razorpay", status, data)
        order_id = data["id"]
    run(_record_order, provider, info, order_id)
    return {"ok": True, "provider": provider, "orderId": order_id, "amount": info["amount"], "display": value,
            "currency": info["currency"], "invoice": info["inv_no"], "loadId": info["load_id"], "customer": info["cust"]}


def paypal_capture(run, order_id, source="checkout"):
    if not order_id:
        raise ApiError("orderId is required")
    run(_payment_row, "paypal", order_id)  # must be an order this server created
    status, data = paypal_call("POST", f"/v2/checkout/orders/{order_id}/capture", {}, request_id=f"capture-{order_id}")
    if status == 422 and any(d.get("issue") == "ORDER_ALREADY_CAPTURED" for d in data.get("details", [])):
        status, data = paypal_call("GET", f"/v2/checkout/orders/{order_id}")
    if status not in (200, 201):
        err = _gateway_error("PayPal", status, data)
        run(_mark_failed, "paypal", order_id, str(err))
        raise err
    try:
        capture = data["purchase_units"][0]["payments"]["captures"][0]
    except (KeyError, IndexError, TypeError):
        raise ApiError(f"PayPal returned order status {data.get('status')} with no capture", 502)
    if data.get("status") != "COMPLETED" or capture.get("status") != "COMPLETED":
        reason = f"PayPal capture status {capture.get('status')} ({(capture.get('status_details') or {}).get('reason', '')})"
        run(_mark_failed, "paypal", order_id, reason)
        raise ApiError(reason + ". Invoice left open.", 402)
    code = capture["amount"]["currency_code"]
    return run(_mark_paid, "paypal", order_id, capture["id"], from_decimal_str(capture["amount"]["value"], code), code, source)


def razorpay_verify(run, body):
    order_id, payment_id = body.get("razorpay_order_id"), body.get("razorpay_payment_id")
    if not (order_id and payment_id and body.get("razorpay_signature")):
        raise ApiError("razorpay_order_id, razorpay_payment_id and razorpay_signature are required")
    row = run(_payment_row, "razorpay", order_id)
    if not razorpay_signature_ok(order_id, payment_id, body["razorpay_signature"]):
        run(_mark_failed, "razorpay", order_id, f"Invalid signature for payment {payment_id}")
        raise ApiError("Payment signature is invalid. Payment not applied.", 400)
    return _razorpay_settle(run, row, payment_id, "checkout")


def _razorpay_settle(run, row, payment_id, source):
    status, pay = razorpay_call("GET", f"/payments/{payment_id}")
    if status != 200:
        raise _gateway_error("Razorpay", status, pay)
    if pay.get("order_id") != row["order_id"]:
        raise ApiError("Payment does not belong to this order", 400)
    if pay.get("status") == "authorized":  # account not set to auto-capture: capture it now
        status, pay = razorpay_call("POST", f"/payments/{payment_id}/capture",
                                    {"amount": row["amount"], "currency": row["currency"]})
        if status != 200:
            raise _gateway_error("Razorpay", status, pay)
    if pay.get("status") != "captured":
        reason = f"Razorpay payment {payment_id} is {pay.get('status')}"
        run(_mark_failed, "razorpay", row["order_id"], reason)
        raise ApiError(reason + ". Invoice left open.", 402)
    return run(_mark_paid, "razorpay", row["order_id"], payment_id, int(pay["amount"]), pay["currency"].upper(), source)


# ---------------------------------------------------------------- webhooks (no session; signature-verified)
def razorpay_webhook(run, raw_body, signature):
    if not razorpay_webhook_signature_ok(raw_body, signature):
        raise ApiError("Invalid webhook signature", 401)
    event = json.loads(raw_body.decode("utf-8"))
    kind = event.get("event")
    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    order_id = entity.get("order_id")
    if not order_id:
        return {"ok": True, "ignored": kind}
    try:
        row = run(_payment_row, "razorpay", order_id)
    except ApiError:
        return {"ok": True, "ignored": "unknown order"}  # not ours; acknowledge so Razorpay stops retrying
    if kind in ("payment.captured", "order.paid"):
        return run(_mark_paid, "razorpay", order_id, entity["id"], int(entity["amount"]), entity["currency"].upper(), "webhook")
    if kind == "payment.authorized":
        return _razorpay_settle(run, row, entity["id"], "webhook")
    if kind == "payment.failed":
        run(_mark_failed, "razorpay", order_id, f"Razorpay: {entity.get('error_description') or 'payment failed'}")
    return {"ok": True}


def paypal_webhook(run, raw_body, headers):
    webhook_id = env("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        raise ApiError("PAYPAL_WEBHOOK_ID is not configured", 401)
    event = json.loads(raw_body.decode("utf-8"))
    status, data = paypal_call("POST", "/v1/notifications/verify-webhook-signature", {
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO"), "cert_url": headers.get("PAYPAL-CERT-URL"),
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID"), "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG"),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME"), "webhook_id": webhook_id, "webhook_event": event,
    })
    if status != 200 or data.get("verification_status") != "SUCCESS":
        raise ApiError("Invalid webhook signature", 401)
    kind, res = event.get("event_type"), event.get("resource") or {}
    try:
        if kind == "CHECKOUT.ORDER.APPROVED":
            return paypal_capture(run, res.get("id"), "webhook")
        if kind == "PAYMENT.CAPTURE.COMPLETED":
            order_id = ((res.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
            code = res["amount"]["currency_code"]
            return run(_mark_paid, "paypal", order_id, res["id"], from_decimal_str(res["amount"]["value"], code), code, "webhook")
        if kind in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
            order_id = ((res.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
            run(_mark_failed, "paypal", order_id, f"PayPal: capture {kind.rsplit('.', 1)[-1].lower()}")
    except ApiError as e:
        if e.status == 404:
            return {"ok": True, "ignored": "unknown order"}
        raise
    return {"ok": True}
