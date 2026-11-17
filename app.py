#!/usr/bin/env python3
"""FleetFlow TMS — web server.

Serves the front end from ./frontend and a JSON REST API under /api, backed by SQLite.
Public home page at /, sign-in at /login.html, the app at /app.html.
The app and every /api route except /api/auth/* and /api/public/* require a session.
Standard library only: run with  `python app.py`  (Python 3.9+), then open http://localhost:8000
"""
import argparse
import json
import mimetypes
import re
import sys
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend import auth, db, payments, services  # noqa: E402

FRONTEND = Path(__file__).resolve().parent / "frontend"
LOCK = threading.Lock()  # one writer at a time keeps SQLite simple and safe
MAX_BODY = 1_000_000     # bytes; webhooks and forms are far smaller


def post_message(con, load_id, body):
    result = services.send_message(con, load_id, body.get("text"))
    threading.Timer(2.5, run, args=(services.driver_reply, load_id)).start()  # driver answers shortly after
    return result


def reset(con, body):
    db.build(con, reset=True)
    return {"ok": True, "toast": "Demo data reset"}


# (method, URL pattern, handler(con, url_match, json_body))
ROUTES = [
    ("GET",  r"/api/state",                    lambda c, m, b: services.state(c)),
    ("GET",  r"/api/loads",                    lambda c, m, b: services.list_loads(c)),
    ("GET",  r"/api/drivers",                  lambda c, m, b: services.list_drivers(c)),
    ("GET",  r"/api/trucks",                   lambda c, m, b: services.list_trucks(c)),
    ("GET",  r"/api/logs",                     lambda c, m, b: services.list_logs(c)),
    ("POST", r"/api/loads",                    lambda c, m, b: services.create_load(c, b)),
    ("POST", r"/api/edi/204",                  lambda c, m, b: services.edi_204(c)),
    ("POST", r"/api/loads/([\w-]+)/assign",    lambda c, m, b: services.assign(c, m[1], b.get("driver"))),
    ("POST", r"/api/loads/([\w-]+)/unassign",  lambda c, m, b: services.unassign(c, m[1])),
    ("POST", r"/api/loads/([\w-]+)/dispatch",  lambda c, m, b: services.dispatch(c, m[1])),
    ("POST", r"/api/loads/([\w-]+)/pod",       lambda c, m, b: services.attach_pod(c, m[1])),
    ("POST", r"/api/loads/([\w-]+)/invoice",   lambda c, m, b: services.invoice(c, m[1])),
    ("POST", r"/api/loads/([\w-]+)/pay",       lambda c, m, b: services.mark_paid(c, m[1])),
    ("POST", r"/api/loads/([\w-]+)/messages",  lambda c, m, b: post_message(c, m[1], b)),
    ("POST", r"/api/trucks/([\w-]+)/map",      lambda c, m, b: services.map_truck(c, m[1])),
    ("POST", r"/api/logs/(\d+)/retry",         lambda c, m, b: services.retry_log(c, int(m[1]))),
    ("POST", r"/api/simulate/tick",            lambda c, m, b: services.tick(c)),
    ("POST", r"/api/reset",                    lambda c, m, b: reset(c, b)),
    ("GET",  r"/api/payments",                 lambda c, m, b: payments.list_payments(c)),
]

# Payment routes call the gateway over the network, so they manage their own short transactions
# (via run) instead of holding the database lock for the whole request.
PAYMENT_ROUTES = [
    ("GET",  r"/api/payments/config",          lambda m, b: payments.public_config()),
    ("POST", r"/api/loads/([\w-]+)/checkout",  lambda m, b: payments.create_checkout(run, m[1], b.get("provider"))),
    ("POST", r"/api/payments/paypal/capture",  lambda m, b: payments.paypal_capture(run, b.get("orderId"))),
    ("POST", r"/api/payments/razorpay/verify", lambda m, b: payments.razorpay_verify(run, b)),
]


def session_cookie(token, max_age=auth.SESSION_SECONDS):
    """HttpOnly: page scripts cannot read it. SameSite=Lax: other sites cannot send it with a POST."""
    return f"session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"


def run(fn, *args):
    """Run one unit of work in its own transaction: commit on success, roll back on error."""
    with LOCK:
        con = db.connect()
        try:
            result = fn(con, *args)
            con.commit()
            return result
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "FleetFlowTMS/1.0"

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        path = unquote(urlparse(self.path).path)
        token = self.session_token()
        if not path.startswith("/api/"):
            if method != "GET":
                return self.send_json({"error": "Not found"}, 404)
            signed_in = bool(run(auth.current_user, token))
            if path == "/app.html" and not signed_in:
                return self.redirect("/login.html")
            if path == "/login.html" and signed_in:
                return self.redirect("/app.html")
            return self.static(path)
        try:
            if method == "POST" and path.startswith("/api/webhooks/"):  # gateway servers: no session, signature-checked
                return self.webhook_route(path)
            body = self.read_json() if method == "POST" else {}
            if (method, path) == ("GET", "/api/public/stats"):  # shown on the public home page
                return self.send_json(run(services.public_stats))
            if path.startswith("/api/auth/"):
                return self.auth_route(method, path, body, token)
            if not run(auth.current_user, token):
                return self.send_json({"error": "Please sign in"}, 401)
            for verb, pattern, handler in PAYMENT_ROUTES:
                match = re.fullmatch(pattern, path)
                if match and verb == method:
                    return self.send_json(handler(match, body))
            for verb, pattern, handler in ROUTES:
                match = re.fullmatch(pattern, path)
                if match and verb == method:
                    return self.send_json(run(handler, match, body))
            self.send_json({"error": f"No route for {method} {path}"}, 404)
        except services.ApiError as e:
            self.send_json({"error": str(e)}, e.status)
        except Exception as e:  # unexpected: report it rather than dropping the connection
            self.send_json({"error": f"Server error: {e}"}, 500)

    def auth_route(self, method, path, body, token):
        if (method, path) == ("POST", "/api/auth/register"):
            user, new_token = run(auth.register, body)
            return self.send_json(user, 201, cookie=session_cookie(new_token))
        if (method, path) == ("POST", "/api/auth/login"):
            user, new_token = run(auth.login, body)
            return self.send_json(user, cookie=session_cookie(new_token))
        if (method, path) == ("POST", "/api/auth/logout"):
            if token:
                run(auth.logout, token)
            return self.send_json({"ok": True}, cookie=session_cookie("", 0))
        if (method, path) == ("GET", "/api/auth/me"):
            user = run(auth.current_user, token)
            return self.send_json(user) if user else self.send_json({"error": "Please sign in"}, 401)
        self.send_json({"error": f"No route for {method} {path}"}, 404)

    def webhook_route(self, path):
        raw = self.read_raw()
        if path == "/api/webhooks/razorpay":
            return self.send_json(payments.razorpay_webhook(run, raw, self.headers.get("X-Razorpay-Signature")))
        if path == "/api/webhooks/paypal":
            headers = {k.upper(): v for k, v in self.headers.items()}
            return self.send_json(payments.paypal_webhook(run, raw, headers))
        self.send_json({"error": "Not found"}, 404)

    def read_raw(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise services.ApiError("Request body too large", 413)
        return self.rfile.read(length) if length else b""

    def session_token(self):
        try:
            morsel = SimpleCookie(self.headers.get("Cookie") or "").get("session")
        except Exception:
            return None
        return morsel.value if morsel else None

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def read_json(self):
        raw = self.read_raw()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise services.ApiError("Request body is not valid JSON")
        if not isinstance(data, dict):
            raise services.ApiError("Request body must be a JSON object")
        return data

    def send_json(self, data, status=200, cookie=None):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def static(self, path):
        target = (FRONTEND / (path.lstrip("/") or "index.html")).resolve()
        if FRONTEND not in target.parents or not target.is_file():
            return self.send_json({"error": "Not found"}, 404)
        payload = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        if "/api/simulate/tick" not in (args[0] if args else ""):  # keep the console readable
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description="FleetFlow TMS server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reset", action="store_true", help="wipe the database and reload the sample data")
    args = parser.parse_args()

    payments.load_env_file()
    db.init_db(reset=args.reset)
    gateways = [n for n, on in (("PayPal", payments.paypal_enabled()), ("Razorpay", payments.razorpay_enabled())) if on]
    print("Payment gateways: " + (", ".join(gateways) if gateways else "none configured (see .env.example)"))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"FleetFlow TMS running at http://localhost:{args.port}   (database: {db.DB_PATH.name}, Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
