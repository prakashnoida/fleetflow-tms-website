# API reference

Base URL: `http://localhost:8000`. All bodies and responses are JSON. Errors return `{"error": "message"}` with status 400 (rule or validation failure), 404 (not found) or 500.

## Accounts

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/api/auth/register` | `name, email, password` | Create an account and sign in (201, sets the session cookie) |
| POST | `/api/auth/login` | `email, password` | Sign in (sets the session cookie); 401 on wrong credentials, 429 when locked |
| POST | `/api/auth/logout` | – | End the session |
| GET | `/api/auth/me` | – | The signed-in user, or 401 |

Every route below needs the session cookie and returns 401 without it. With curl, save and send it:
`curl -c cookies.txt -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"you@example.com","password":"your-password"}'` then add `-b cookies.txt` to later calls. In Postman the cookie is kept automatically.

## Public

| Method | Path | Returns |
|---|---|---|
| GET | `/api/public/stats` | Counts of trucks, drivers, cities and loads on the road (no sign-in needed) |

## Read

| Method | Path | Returns |
|---|---|---|
| GET | `/api/state` | Everything the UI needs: cities, customers, drivers, trucks, loads, logs, messages |
| GET | `/api/loads` | All loads, newest first |
| GET | `/api/drivers` | Drivers with HOS hours |
| GET | `/api/trucks` | Trucks with telematics mapping |
| GET | `/api/logs` | Integration event log, newest first |

## Write

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/api/loads` | `cust, o, d, pu, del, equip, weight, rate` | Create a Booked load |
| POST | `/api/edi/204` | – | Simulate an inbound EDI load tender |
| POST | `/api/loads/{id}/assign` | `driver` | Booked → Planned |
| POST | `/api/loads/{id}/unassign` | – | Planned → Booked |
| POST | `/api/loads/{id}/dispatch` | – | Planned → Dispatched (fails if truck is unmapped) |
| POST | `/api/loads/{id}/pod` | – | Attach proof of delivery |
| POST | `/api/loads/{id}/invoice` | – | Delivered → Invoiced (requires POD) |
| POST | `/api/loads/{id}/pay` | – | Invoice Open → Paid |
| POST | `/api/loads/{id}/messages` | `text` | Message the driver (a simulated reply follows) |
| POST | `/api/trucks/{id}/map` | – | Map truck to a telematics vehicle |
| POST | `/api/logs/{id}/retry` | – | Retry a failed integration event |
| POST | `/api/simulate/tick` | – | Advance the telematics simulation one step |
| POST | `/api/reset` | – | Restore the sample data |

## Payments

| Method | Path | Body | Effect |
|---|---|---|---|
| GET | `/api/payments/config` | – | Enabled gateways, public keys, currency |
| GET | `/api/payments` | – | All payment attempts |
| POST | `/api/loads/{id}/checkout` | `provider` (`paypal` / `razorpay`) | Create a gateway order for the open invoice |
| POST | `/api/payments/paypal/capture` | `orderId` | Capture the approved PayPal order; invoice → Paid |
| POST | `/api/payments/razorpay/verify` | `razorpay_order_id, razorpay_payment_id, razorpay_signature` | Verify and capture; invoice → Paid |
| POST | `/api/webhooks/paypal` | PayPal event | No session; signature verified with PayPal |
| POST | `/api/webhooks/razorpay` | Razorpay event | No session; `X-Razorpay-Signature` HMAC verified |

## Examples

```bash
# create an order
curl -X POST http://localhost:8000/api/loads -H "Content-Type: application/json" \
  -d '{"cust":"Northwind Foods","o":"Chicago, IL","d":"Dallas, TX","pu":"Nov 20, 08:00","del":"Nov 21, 14:00","equip":"53'"'"' Reefer","weight":38000,"rate":2850}'
# → {"ok": true, "id": "LD-24109", "toast": "LD-24109 created"}

# assign and dispatch
curl -X POST http://localhost:8000/api/loads/LD-24109/assign -H "Content-Type: application/json" -d '{"driver":"D-03"}'
curl -X POST http://localhost:8000/api/loads/LD-24109/dispatch

# business rule: invoicing without POD is rejected
curl -X POST http://localhost:8000/api/loads/LD-24097/invoice
# → 400 {"error": "Only a Delivered load can be invoiced"} or {"error": "POD required before invoicing"}
```

On Windows PowerShell use `curl.exe` and escape quotes, or test with Postman.
