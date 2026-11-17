"""Business logic. Every function takes an open SQLite connection and reads/writes the database."""
import math
import random
from datetime import datetime, timedelta

ON_LOAD = ("Planned", "Dispatched", "In Transit")
ROAD_FACTOR = 1.18        # straight-line miles -> practical road miles
EDI_RATE_PER_MILE = 2.35  # contract rate used for EDI tenders
INVOICE_TERMS_DAYS = 30
DRIVER_REPLIES = ["10-4, copy that.", "Got it 👍", "Will do. Traffic is light."]


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- helpers
def clock():
    return datetime.now().strftime("%H:%M:%S")


def day(offset, hhmm):
    return f"{datetime.now() + timedelta(days=offset):%b %d}, {hhmm}"


def add_log(con, system, direction, type_, ref, status, msg, fix=None):
    con.execute("INSERT INTO logs (t,sys,dir,type,ref,st,msg,fix) VALUES (?,?,?,?,?,?,?,?)",
                (clock(), system, direction, type_, ref, status, msg, fix))


def miles(con, origin, dest):
    pts = {r["name"]: (r["lat"], r["lon"])
           for r in con.execute("SELECT * FROM cities WHERE name IN (?,?)", (origin, dest))}
    if origin not in pts or dest not in pts:
        raise ApiError("Unknown origin or destination city")
    (la1, lo1), (la2, lo2) = pts[origin], pts[dest]
    rad = math.radians
    h = math.sin(rad(la2 - la1) / 2) ** 2 + math.cos(rad(la1)) * math.cos(rad(la2)) * math.sin(rad(lo2 - lo1) / 2) ** 2
    return round(2 * 3959 * math.asin(math.sqrt(h)) * ROAD_FACTOR)


def get_load(con, load_id):
    row = con.execute("SELECT * FROM loads WHERE id=?", (load_id,)).fetchone()
    if not row:
        raise ApiError(f"Load {load_id} not found", 404)
    return row


def get_driver(con, driver_id):
    row = con.execute("SELECT * FROM drivers WHERE id=?", (driver_id,)).fetchone()
    if not row:
        raise ApiError(f"Driver {driver_id} not found", 404)
    return row


def truck_of(con, driver_id):
    return con.execute("SELECT t.* FROM trucks t JOIN drivers d ON d.truck=t.id WHERE d.id=?", (driver_id,)).fetchone()


def next_load_id(con):
    n = con.execute("SELECT MAX(CAST(SUBSTR(id,4) AS INTEGER)) FROM loads").fetchone()[0] or 24100
    return f"LD-{n + 1}"


def insert_load(con, cust, origin, dest, pickup, delivery, equip, weight, rate):
    load_id = next_load_id(con)
    seq = (con.execute("SELECT MAX(seq) FROM loads").fetchone()[0] or 0) + 1
    con.execute("INSERT INTO loads (id,seq,cust,origin,dest,pickup,delivery,equip,weight,rate) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (load_id, seq, cust, origin, dest, pickup, delivery, equip, weight, rate))
    return load_id


# ---------------------------------------------------------------- reads
def list_loads(con):
    out = []
    paid = {r["load_id"]: r for r in con.execute(
        "SELECT load_id, provider, payment_id FROM payments WHERE status='paid' ORDER BY id")}
    for r in con.execute("SELECT * FROM loads ORDER BY seq DESC"):
        l = {"id": r["id"], "cust": r["cust"], "o": r["origin"], "d": r["dest"], "pu": r["pickup"], "del": r["delivery"],
             "status": r["status"], "driver": r["driver"], "equip": r["equip"], "weight": r["weight"], "rate": r["rate"],
             "prog": r["prog"], "pod": bool(r["pod"]), "late": bool(r["late"]), "dispatchErr": bool(r["dispatch_err"])}
        if r["inv_no"]:
            l["inv"] = {"no": r["inv_no"], "st": r["inv_st"], "due": r["inv_due"]}
            if r["id"] in paid:
                l["inv"]["via"] = paid[r["id"]]["provider"]
                l["inv"]["ref"] = paid[r["id"]]["payment_id"]
        out.append(l)
    return out


def list_drivers(con):
    return [dict(r) for r in con.execute("SELECT * FROM drivers ORDER BY id")]


def list_trucks(con):
    return [dict(r) for r in con.execute("SELECT * FROM trucks ORDER BY id")]


def list_logs(con):
    return [dict(r) for r in con.execute("SELECT * FROM logs ORDER BY id DESC")]


def public_stats(con):
    """Headline counts for the public home page. No customer or load detail."""
    one = lambda sql: con.execute(sql).fetchone()[0]
    return {"trucks": one("SELECT COUNT(*) FROM trucks"), "drivers": one("SELECT COUNT(*) FROM drivers"),
            "cities": one("SELECT COUNT(*) FROM cities"),
            "active": one("SELECT COUNT(*) FROM loads WHERE status IN ('Dispatched','In Transit')")}


def state(con):
    """Everything the UI needs, in one call."""
    msgs = {}
    for r in con.execute("SELECT * FROM messages ORDER BY id"):
        msgs.setdefault(r["load_id"], []).append({"me": bool(r["me"]), "text": r["text"], "t": r["t"]})
    customers = con.execute("SELECT * FROM customers ORDER BY rowid").fetchall()
    return {
        "cities": {r["name"]: [r["lat"], r["lon"]] for r in con.execute("SELECT * FROM cities ORDER BY rowid")},
        "customers": [c["name"] for c in customers],
        "ediCustomers": [c["name"] for c in customers if c["edi"]],
        "drivers": list_drivers(con), "trucks": list_trucks(con),
        "loads": list_loads(con), "logs": list_logs(con), "msgs": msgs,
    }


# ---------------------------------------------------------------- orders
def create_load(con, body):
    required = ["cust", "o", "d", "pu", "del", "equip", "weight", "rate"]
    missing = [k for k in required if body.get(k) in (None, "")]
    if missing:
        raise ApiError("Missing field(s): " + ", ".join(missing))
    if body["o"] == body["d"]:
        raise ApiError("Origin and destination must differ")
    if not con.execute("SELECT 1 FROM customers WHERE name=?", (body["cust"],)).fetchone():
        raise ApiError("Unknown customer")
    try:
        weight, rate = int(body["weight"]), float(body["rate"])
    except (TypeError, ValueError):
        raise ApiError("Weight and rate must be numbers")
    if weight <= 0 or rate < 0:
        raise ApiError("Weight must be positive and rate cannot be negative")
    mi = miles(con, body["o"], body["d"])
    load_id = insert_load(con, body["cust"], body["o"], body["d"], str(body["pu"]), str(body["del"]),
                          str(body["equip"]), weight, rate)
    add_log(con, "Mileage", "OUT", "Route miles", load_id, "Success", f"Practical miles calculated: {mi}")
    return {"ok": True, "id": load_id, "toast": f"{load_id} created"}


def edi_204(con):
    """Simulate an inbound EDI 204 load tender from an EDI customer."""
    cities = [r["name"] for r in con.execute("SELECT name FROM cities")]
    customers = [r["name"] for r in con.execute("SELECT name FROM customers WHERE edi=1")]
    origin, dest = random.sample(cities, 2)
    cust = random.choice(customers)
    rate = round(miles(con, origin, dest) * EDI_RATE_PER_MILE / 10) * 10
    load_id = insert_load(con, cust, origin, dest, day(1, "07:00"), day(2, "10:00"), "53' Dry Van", 38000, rate)
    add_log(con, "EDI", "IN", "204 Load Tender", load_id, "Success", f"Tender from {cust} received; 990 accept sent")
    return {"ok": True, "id": load_id, "toast": f"EDI 204 received → {load_id} created"}


# ---------------------------------------------------------------- planning & dispatch
def assign(con, load_id, driver_id):
    load, driver = get_load(con, load_id), get_driver(con, driver_id)
    if load["status"] != "Booked":
        raise ApiError(f"{load_id} is already {load['status']}")
    busy = con.execute(f"SELECT id FROM loads WHERE driver=? AND status IN ({','.join('?' * len(ON_LOAD))})",
                       (driver_id, *ON_LOAD)).fetchone()
    if busy:
        raise ApiError(f"{driver['name']} is already on {busy['id']}")
    con.execute("UPDATE loads SET driver=?, status='Planned' WHERE id=?", (driver_id, load_id))
    add_log(con, "TMS", "—", "Preplan", load_id, "Success", f"{driver['name']} ({driver['truck']}) assigned")
    return {"ok": True, "toast": f"{load_id} planned with {driver['name']}"}


def unassign(con, load_id):
    if get_load(con, load_id)["status"] != "Planned":
        raise ApiError("Only a Planned load can be unassigned")
    con.execute("UPDATE loads SET driver=NULL, status='Booked' WHERE id=?", (load_id,))
    return {"ok": True, "toast": f"{load_id} unassigned"}


def dispatch(con, load_id):
    """Push the load to the driver's app (simulated Motive POST /v2/dispatches)."""
    load = get_load(con, load_id)
    if load["status"] not in ("Planned", "Dispatched") or not load["driver"]:
        raise ApiError("Assign a driver before dispatching")
    driver, truck = get_driver(con, load["driver"]), truck_of(con, load["driver"])
    if not truck["motive"]:
        con.execute("UPDATE loads SET status='Dispatched', dispatch_err=1 WHERE id=?", (load_id,))
        add_log(con, "Motive", "OUT", "Dispatch", load_id, "Error",
                f"POST /v2/dispatches rejected – truck {truck['id']} has no Motive vehicle mapping", "map")
        return {"ok": True, "error": True, "toast": f"Dispatch failed: {truck['id']} not mapped to Motive"}
    con.execute("UPDATE loads SET status='Dispatched', dispatch_err=0, ticks=0 WHERE id=?", (load_id,))
    con.execute("UPDATE logs SET st='Success' WHERE ref=? AND fix='map'", (load_id,))
    add_log(con, "Motive", "OUT", "Dispatch", load_id, "Success",
            f"POST /v2/dispatches 201 – sent to {driver['name']}'s Driver App")
    return {"ok": True, "toast": f"{load_id} sent to Motive Driver App"}


# ---------------------------------------------------------------- documents & billing
def attach_pod(con, load_id):
    get_load(con, load_id)
    con.execute("UPDATE loads SET pod=1 WHERE id=?", (load_id,))
    con.execute("UPDATE logs SET st='Success' WHERE ref=? AND fix='doc' AND st='Error'", (load_id,))
    add_log(con, "Motive", "IN", "Document", load_id, "Success", "POD scan received from Driver App and linked to load")
    return {"ok": True, "toast": "POD attached"}


def invoice(con, load_id):
    load = get_load(con, load_id)
    if load["status"] != "Delivered":
        raise ApiError("Only a Delivered load can be invoiced")
    if not load["pod"]:
        raise ApiError("POD required before invoicing")
    n = (con.execute("SELECT MAX(CAST(SUBSTR(inv_no,5) AS INTEGER)) FROM loads").fetchone()[0] or 50300) + 1
    due = f"{datetime.now() + timedelta(days=INVOICE_TERMS_DAYS):%b %d}"
    con.execute("UPDATE loads SET status='Invoiced', inv_no=?, inv_st='Open', inv_due=? WHERE id=?",
                (f"INV-{n}", due, load_id))
    add_log(con, "Accounting", "OUT", "Invoice export", load_id, "Success", f"INV-{n} posted to ERP")
    if con.execute("SELECT edi FROM customers WHERE name=?", (load["cust"],)).fetchone()["edi"]:
        add_log(con, "EDI", "OUT", "210 Freight Invoice", load_id, "Success", f"210 sent to {load['cust']}")
    return {"ok": True, "toast": f"Invoice INV-{n} created"}


def mark_paid(con, load_id):
    if get_load(con, load_id)["inv_st"] != "Open":
        raise ApiError("No open invoice on this load")
    con.execute("UPDATE loads SET inv_st='Paid' WHERE id=?", (load_id,))
    add_log(con, "Accounting", "IN", "Payment", load_id, "Success", "Payment received – invoice closed")
    return {"ok": True, "toast": "Marked as paid"}


# ---------------------------------------------------------------- fleet & integrations
def map_truck(con, truck_id):
    if not con.execute("SELECT 1 FROM trucks WHERE id=?", (truck_id,)).fetchone():
        raise ApiError(f"Truck {truck_id} not found", 404)
    motive = f"MV-{88300 + random.randrange(90)}"
    con.execute("UPDATE trucks SET motive=? WHERE id=?", (motive, truck_id))
    add_log(con, "Motive", "IN", "Vehicle mapping", truck_id, "Success", f"GET /vehicles – {truck_id} matched to {motive} by VIN")
    return {"ok": True, "toast": f"{truck_id} mapped to {motive}. Retry the failed dispatch."}


def retry_log(con, log_id):
    x = con.execute("SELECT * FROM logs WHERE id=?", (log_id,)).fetchone()
    if not x:
        raise ApiError("Log entry not found", 404)
    if x["st"] != "Error":
        return {"ok": True}
    if x["fix"] == "map":
        load = get_load(con, x["ref"])
        truck = truck_of(con, load["driver"])
        if not truck["motive"]:
            raise ApiError(f"Still failing: map {truck['id']} in Drivers & Trucks first")
        return dispatch(con, load["id"])
    con.execute("UPDATE logs SET st='Success' WHERE id=?", (log_id,))
    if x["fix"] == "scope":
        n = con.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
        add_log(con, "Motive", "IN", "HOS sync", "—", "Success",
                f"OAuth scope granted by admin; GET /hours_of_service 200 – {n} drivers synced")
        return {"ok": True, "toast": "HOS sync restored"}
    if x["fix"] == "doc":
        con.execute("UPDATE loads SET pod=1 WHERE id=?", (x["ref"],))
        add_log(con, "Motive", "IN", "Document", x["ref"], "Success", "Load reference normalised; POD linked")
        return {"ok": True, "toast": f"POD linked to {x['ref']}"}
    return {"ok": True}


# ---------------------------------------------------------------- messaging
def send_message(con, load_id, text):
    get_load(con, load_id)
    text = (text or "").strip()
    if not text:
        raise ApiError("Message is empty")
    con.execute("INSERT INTO messages (load_id,me,text,t) VALUES (?,?,?,?)", (load_id, 1, text[:500], clock()[:5]))
    add_log(con, "Motive", "OUT", "Message", load_id, "Success", "POST /messages 201 – delivered to Driver App")
    return {"ok": True}


def driver_reply(con, load_id):
    """Simulated driver answer, called a few seconds after a dispatcher message."""
    con.execute("INSERT INTO messages (load_id,me,text,t) VALUES (?,?,?,?)",
                (load_id, 0, random.choice(DRIVER_REPLIES), clock()[:5]))
    add_log(con, "Motive", "IN", "Message", load_id, "Success", "Driver reply received")


# ---------------------------------------------------------------- telematics simulation
def tick(con):
    """One simulated telematics cycle: trucks move, HOS clocks run, geofence events fire."""
    toasts = []
    for l in con.execute("SELECT * FROM loads WHERE status IN ('Dispatched','In Transit')").fetchall():
        lid, drv = l["id"], l["driver"]
        if l["status"] == "Dispatched":
            if l["dispatch_err"]:
                continue
            if l["ticks"] + 1 >= 2:
                con.execute("UPDATE loads SET status='In Transit', ticks=0 WHERE id=?", (lid,))
                con.execute("UPDATE drivers SET status='Driving' WHERE id=?", (drv,))
                add_log(con, "Motive", "IN", "Geofence event", lid, "Success", f"Departed shipper – {l['origin']}")
                toasts.append(f"{lid} departed {l['origin']}")
            else:
                con.execute("UPDATE loads SET ticks=ticks+1 WHERE id=?", (lid,))
            continue
        prog = min(1.0, l["prog"] + max(0.015, 30 / miles(con, l["origin"], l["dest"])))
        con.execute("UPDATE drivers SET drive=MAX(0,ROUND(drive-0.2,1)), shift=MAX(0,ROUND(shift-0.2,1)), "
                    "cycle=ROUND(cycle+0.2,1) WHERE id=?", (drv,))
        if prog < 1:
            con.execute("UPDATE loads SET prog=? WHERE id=?", (prog, lid))
            continue
        con.execute("UPDATE loads SET status='Delivered', prog=1, late=0 WHERE id=?", (lid,))
        con.execute("UPDATE drivers SET status='On Duty', loc=? WHERE id=?", (l["dest"], drv))
        add_log(con, "Motive", "IN", "Geofence event", lid, "Success", f"Arrived at consignee – {l['dest']}")
        toasts.append(f"{lid} delivered at {l['dest']}")
        if random.random() < 0.6:  # most drivers scan the POD straight away
            con.execute("UPDATE loads SET pod=1 WHERE id=?", (lid,))
            add_log(con, "Motive", "IN", "Document", lid, "Success", "POD scan received from Driver App")
    n = con.execute("SELECT COUNT(*) FROM loads WHERE status IN ('Dispatched','In Transit')").fetchone()[0]
    add_log(con, "Motive", "IN", "Location ping", "—", "Success", f"GET /vehicle_locations – {n} vehicles updated")
    con.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 200)")
    return {"ok": True, "toasts": toasts}
