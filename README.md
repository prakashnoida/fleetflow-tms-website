# FleetFlow TMS (full stack)

A Transportation Management System website for an asset-based US trucking carrier: **user registration and login + Python REST API + SQLite database + JavaScript front end**. A load moves through **Booked → Planned → Dispatched → In Transit → Delivered → Invoiced**, and every screen reads and writes the database through the API.

> The business data is real and persistent (stored in `fleetflow.db`). The *external systems* — Motive telematics, customer EDI, accounting/ERP — are **simulated by the server**; no third-party API is called.

## Run it

Requires **Python 3.9 or newer**. No packages to install (standard library only).

```bash
python app.py
```

Open **http://localhost:8000**. You land on the public home page: choose **Create account**, register, and you are taken to the dashboard. On Windows, if `python` is not found use `py app.py`; on macOS/Linux use `python3 app.py`.

| Option | Purpose |
|---|---|
| `python app.py --port 5000` | use another port |
| `python app.py --reset` | wipe the database and reload the sample data |

The database file `fleetflow.db` is created on first run. Stop and restart the server: your data is still there. The **Reset demo data** button in the sidebar restores the starting data (user accounts are kept).

### Run the tests

```bash
python -m unittest discover tests
```

## Pages

| URL | Page | Access |
|---|---|---|
| `/` | Company home page with live fleet figures | Public |
| `/login.html` | Sign in / create account | Public |
| `/app.html` | TMS: dashboard, orders, dispatch, tracking, fleet, billing, integrations | Signed-in users |

FleetFlow is a fictional company; phone numbers and email addresses on the home page are placeholders.

## Online payments (PayPal / Razorpay)

Open invoices on **Billing & Settlement** have a **Pay online** button. The payment is real and goes through the gateway; test/sandbox keys move no money.

1. Copy `.env.example` to `.env` (it is git-ignored) and fill in either gateway, or both:
   - **PayPal**: [developer.paypal.com](https://developer.paypal.com/dashboard/applications), then *Apps & Credentials* gives you the sandbox Client ID and Secret. Pay with a sandbox *Personal* account.
   - **Razorpay**: Dashboard → *Account & Settings → API Keys* in **Test Mode** gives you the Key ID and Secret. Use Razorpay's test cards or UPI `success@razorpay`.
2. Restart `python app.py`. The console shows `Payment gateways: PayPal, Razorpay`.
3. Invoice a load, then *Pay online*. When the gateway confirms, the invoice turns **Paid**. A *Payments* entry is added to the Integrations log, and the record is saved in the `payments` table.

| Setting | Meaning |
|---|---|
| `PAYMENT_CURRENCY`, `PAYMENT_FX_RATE` | Invoices are USD. For an Indian Razorpay account use `INR` and a rate (e.g. `83.2`); USD on Razorpay needs international payments enabled |
| `PAYPAL_MODE` | `sandbox` (default) or `live` |
| `PAYPAL_WEBHOOK_ID`, `RAZORPAY_WEBHOOK_SECRET` | Optional webhooks (`/api/webhooks/paypal`, `/api/webhooks/razorpay`) that record a payment even if the customer closes the browser. They need a public HTTPS URL (deployed host or a tunnel such as ngrok) |

Security: the server computes the amount itself, so the browser never sets the price. It also confirms every payment with the gateway before closing an invoice: PayPal through a server-side capture with an amount and currency check, Razorpay through an HMAC signature check plus a payment lookup that captures authorised payments. Callbacks are idempotent, so a browser callback and a webhook for the same payment record it only once.

## Demo script (4 minutes)

0. **Register and sign in** – create an account, log out, sign back in; open `http://localhost:8000/api/loads` while logged out to show the API refusing with 401.
1. **Dashboard** – KPIs and exceptions are computed from the database.
2. **Orders** – *New order* (saved by `POST /api/loads`) or *Simulate EDI 204* (server creates a tendered load).
3. **Planning & Dispatch** – pick a Booked load, assign the nearest driver, *Send to Motive*.
4. Turn on **Live OBC feed** – each tick calls `POST /api/simulate/tick`; the server moves trucks, burns HOS hours and fires geofence events. Watch **Live Tracking**.
5. **Integrations** – retry the failed dispatch for `LD-24108`: the server rejects it until truck `T-1052` is mapped (*Drivers & Trucks → Trucks*).
6. **Billing** – try to invoice `LD-24097`: blocked until the POD is attached. Attach, invoice, mark paid.
7. **Prove it is dynamic** – refresh the browser, or restart the server: everything you did is still there. Open `http://localhost:8000/api/loads` to show the raw JSON, or open `fleetflow.db` in *DB Browser for SQLite*.

## Architecture

```
Browser (frontend/)  ──fetch JSON──▶  app.py (HTTP + routing)  ──▶  backend/services.py (business rules)  ──▶  SQLite (fleetflow.db)
```

- **Front end** holds no data of its own. `js/api.js` loads state from `GET /api/state`; `js/actions.js` sends every change as a `POST`, then re-reads state and re-renders.
- **Back end** validates and enforces the rules, so they hold no matter which client calls the API (browser, Postman, curl).
- Each request runs in one database transaction: commit on success, roll back on error.

### Accounts and security

| What | How |
|---|---|
| Passwords | Never stored. Salted PBKDF2-SHA256 hash (200,000 rounds), per-user random salt |
| Sessions | Random token in an `HttpOnly`, `SameSite=Lax` cookie, valid 7 days; the database keeps only its SHA-256 |
| Access control | `/app.html` redirects to the login page without a session; every `/api` route except `/api/auth/*` and `/api/public/stats` returns 401 |
| Login protection | Same error for unknown email and wrong password; 5 failed attempts lock that email for 5 minutes |
| Roles | First registered user is `Admin`, later users `Dispatcher` (shown in the top bar; not yet used for permissions) |

### Business rules enforced by the server

| Rule | Where |
|---|---|
| A load can be invoiced only when Delivered **and** the POD is received | `services.invoice` |
| A driver already on a Planned / Dispatched / In Transit load cannot be assigned again | `services.assign` |
| Dispatch fails when the truck has no telematics vehicle mapping; succeeds after mapping | `services.dispatch`, `services.map_truck` |
| EDI customers automatically receive a 210 invoice message | `services.invoice` |
| Origin ≠ destination; customer and cities must exist; weight and rate must be valid numbers | `services.create_load` |

## Project structure

```
fleetflow-tms-fullstack/
├── app.py                    Web server: static files + REST API routing
├── backend/
│   ├── schema.sql            Database tables (cities, customers, trucks, drivers, loads, logs, messages, users, sessions)
│   ├── db.py                 Connection, schema creation, first-run seed
│   ├── auth.py               Registration, login, password hashing, sessions
│   ├── services.py           Business logic and telematics simulation
│   ├── payments.py           PayPal + Razorpay checkout, verification, webhooks
│   └── seed_data.json        Sample data loaded into an empty database
├── frontend/
│   ├── index.html            Public home page (services, dispatch, portal, safety, values)
│   ├── login.html            Sign in / create account
│   ├── app.html              The TMS app (requires a session)
│   ├── css/styles.css
│   └── js/
│       ├── api.js            fetch wrapper + state loader
│       ├── actions.js        every user action → API call
│       ├── payments.js       PayPal Buttons / Razorpay Checkout
│       ├── state.js, nav.js  helpers, router
│       └── dashboard.js, orders.js, load-drawer.js, dispatch.js,
│           tracking.js, fleet.js, billing.js, integrations.js, main.js
├── tests/                    test_workflow.py (business rules), test_auth.py (accounts)
└── docs/API.md               Endpoint reference with curl examples
```

## Limitations / next steps

- Runs over plain HTTP on localhost. On a real host, put it behind HTTPS and add the `Secure` flag to the cookie.
- No email verification or password reset; roles are stored but every signed-in user can do everything.
- Dates are stored as display text (`Nov 20, 08:00`); a production schema would use ISO timestamps.
- Replace the simulated integrations with real ones: Motive OAuth 2.0 + `POST /v2/dispatches` + webhooks; EDI 204/990/214/210 through a VAN.
- For multi-user production use, move from the built-in server and SQLite to a framework (Flask/FastAPI) and PostgreSQL.

## License

MIT
