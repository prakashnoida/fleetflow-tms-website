"""Payment flows against a temporary database with the gateway HTTP calls faked.  Run:  python -m unittest discover tests"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import db, payments, services  # noqa: E402

LOAD = "LD-24097"  # delivered, POD missing in the seed data


def run(fn, *args):
    con = db.connect()
    try:
        out = fn(con, *args)
        con.commit()
        return out
    finally:
        con.close()


class FakeGateway:
    def __init__(self):
        self.calls, self.orders, self.pay_status, self.capture_amount = [], {}, "captured", None

    def __call__(self, method, url, headers=None, body=None, form=None):
        self.calls.append((method, url, body))
        if url.endswith("/v1/oauth2/token"):
            return 200, {"access_token": "tok", "expires_in": 3600}
        if url.endswith("/v2/checkout/orders"):
            self.orders["PP1"] = body["purchase_units"][0]["amount"]
            return 201, {"id": "PP1", "status": "CREATED"}
        if "/v2/checkout/orders/" in url and url.endswith("/capture"):
            amt = dict(self.orders["PP1"])
            if self.capture_amount:
                amt["value"] = self.capture_amount
            return 201, {"id": "PP1", "status": "COMPLETED", "purchase_units": [
                {"payments": {"captures": [{"id": "CAP1", "status": "COMPLETED", "amount": amt}]}}]}
        if url.endswith("/v1/orders"):
            self.orders["order_R1"] = (body["amount"], body["currency"])
            return 200, {"id": "order_R1", "amount": body["amount"], "currency": body["currency"]}
        if "/v1/payments/" in url:
            amount, cur = self.orders["order_R1"]
            status = "captured" if url.endswith("/capture") else self.pay_status
            return 200, {"id": "pay_1", "order_id": "order_R1", "status": status, "amount": amount, "currency": cur}
        return 404, {"message": "unexpected " + url}


class PaymentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        con = db.connect()
        services.attach_pod(con, LOAD)
        services.invoice(con, LOAD)
        con.commit()
        con.close()
        self.env = {"PAYPAL_CLIENT_ID": "cid", "PAYPAL_CLIENT_SECRET": "csec", "RAZORPAY_KEY_ID": "rzp_test_x",
                    "RAZORPAY_KEY_SECRET": "rsec", "RAZORPAY_WEBHOOK_SECRET": "whsec", "PAYMENT_CURRENCY": "USD",
                    "PAYMENT_FX_RATE": "1"}
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.fake, self.real_http = FakeGateway(), payments._http
        payments._http = self.fake
        payments._paypal_token.update(value=None, expires=0)

    def tearDown(self):
        payments._http = self.real_http
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()

    def inv_status(self):
        return run(services.get_load, LOAD)["inv_st"]

    def expected_cents(self):
        return run(lambda c: payments.invoice_amount_minor(c, services.get_load(c, LOAD)))

    def test_paypal_checkout_and_capture(self):
        r = payments.create_checkout(run, LOAD, "paypal")
        self.assertEqual(r["orderId"], "PP1")
        self.assertEqual(payments.from_decimal_str(self.fake.orders["PP1"]["value"], "USD"), self.expected_cents())
        self.assertEqual(payments.paypal_capture(run, "PP1")["ok"], True)
        self.assertEqual(self.inv_status(), "Paid")
        self.assertTrue(run(payments._mark_paid, "paypal", "PP1", "CAP1", self.expected_cents(), "USD").get("alreadyPaid"))

    def test_paypal_amount_mismatch_rejected(self):
        payments.create_checkout(run, LOAD, "paypal")
        self.fake.capture_amount = "1.00"
        with self.assertRaises(services.ApiError) as e:
            payments.paypal_capture(run, "PP1")
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(self.inv_status(), "Open")

    def test_unknown_paypal_order_rejected(self):
        with self.assertRaises(services.ApiError):
            payments.paypal_capture(run, "NOT-OURS")

    def sign(self, order_id, payment_id, secret="rsec"):
        return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    def test_razorpay_checkout_and_verify(self):
        r = payments.create_checkout(run, LOAD, "razorpay")
        self.assertEqual(r["amount"], self.expected_cents())
        out = payments.razorpay_verify(run, {"razorpay_order_id": "order_R1", "razorpay_payment_id": "pay_1",
                                             "razorpay_signature": self.sign("order_R1", "pay_1")})
        self.assertTrue(out["ok"])
        self.assertEqual(self.inv_status(), "Paid")
        self.assertEqual(run(services.list_loads)[[l["id"] for l in run(services.list_loads)].index(LOAD)]["inv"]["via"], "razorpay")

    def test_razorpay_authorized_payment_is_captured(self):
        payments.create_checkout(run, LOAD, "razorpay")
        self.fake.pay_status = "authorized"
        payments.razorpay_verify(run, {"razorpay_order_id": "order_R1", "razorpay_payment_id": "pay_1",
                                       "razorpay_signature": self.sign("order_R1", "pay_1")})
        self.assertTrue(any(u.endswith("/pay_1/capture") for _, u, _ in self.fake.calls))
        self.assertEqual(self.inv_status(), "Paid")

    def test_razorpay_bad_signature_rejected(self):
        payments.create_checkout(run, LOAD, "razorpay")
        with self.assertRaises(services.ApiError):
            payments.razorpay_verify(run, {"razorpay_order_id": "order_R1", "razorpay_payment_id": "pay_1",
                                           "razorpay_signature": self.sign("order_R1", "pay_1", "wrong")})
        self.assertEqual(self.inv_status(), "Open")

    def test_razorpay_webhook(self):
        r = payments.create_checkout(run, LOAD, "razorpay")
        raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_1", "order_id": "order_R1", "amount": r["amount"], "currency": "USD"}}}}).encode()
        with self.assertRaises(services.ApiError):
            payments.razorpay_webhook(run, raw, "bad-signature")
        sig = hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
        payments.razorpay_webhook(run, raw, sig)
        self.assertEqual(self.inv_status(), "Paid")

    def test_cannot_pay_without_open_invoice(self):
        with self.assertRaises(services.ApiError):
            payments.create_checkout(run, "LD-24101", "paypal")  # in transit, not invoiced

    def test_fx_conversion(self):
        os.environ.update(PAYMENT_CURRENCY="INR", PAYMENT_FX_RATE="80")
        cents_usd = round(self.expected_cents() / 80)
        r = payments.create_checkout(run, LOAD, "razorpay")
        self.assertEqual(r["currency"], "INR")
        self.assertAlmostEqual(r["amount"] / 80, cents_usd, delta=1)

    def test_reset_with_payments(self):
        payments.create_checkout(run, LOAD, "paypal")
        run(lambda c: db.build(c, reset=True))
        self.assertEqual(run(payments.list_payments), [])


if __name__ == "__main__":
    unittest.main()
