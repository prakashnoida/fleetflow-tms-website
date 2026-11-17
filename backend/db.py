"""Database access: connection, schema creation and first-run seed data."""
import json
import os
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("FLEETFLOW_DB", BASE.parent / "fleetflow.db"))
TABLES = ["payments", "messages", "logs", "loads", "drivers", "trucks", "customers", "cities"]


def connect():
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(reset=False):
    """Create tables if needed; load the sample data when the database is empty."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # e.g. a mounted volume at /data
    con = connect()
    try:
        build(con, reset)
        con.commit()
    finally:
        con.close()


def build(con, reset=False):
    if reset:
        for t in TABLES:
            con.execute(f"DROP TABLE IF EXISTS {t}")
    con.executescript((BASE / "schema.sql").read_text(encoding="utf-8"))
    if con.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 0:
        seed(con)


def seed(con):
    data = json.loads((BASE / "seed_data.json").read_text(encoding="utf-8"))
    con.executemany("INSERT INTO cities VALUES (?,?,?)",
                    [(n, lat, lon) for n, (lat, lon) in data["cities"].items()])
    con.executemany("INSERT INTO customers VALUES (?,?)",
                    [(c, int(c in data["ediCustomers"])) for c in data["customers"]])
    con.executemany("INSERT INTO trucks VALUES (?,?,?,?,?,?)",
                    [(t["id"], t["unit"], t["motive"], t["odo"], t["fuel"], t["fault"]) for t in data["trucks"]])
    con.executemany("INSERT INTO drivers VALUES (?,?,?,?,?,?,?,?,?)",
                    [(d["id"], d["name"], d["truck"], d["status"], d["drive"], d["shift"], d["cycle"], d["loc"], d["phone"])
                     for d in data["drivers"]])
    for i, l in enumerate(data["loads"]):
        inv = l.get("inv") or {}
        con.execute(
            "INSERT INTO loads (id,seq,cust,origin,dest,pickup,delivery,status,driver,equip,weight,rate,prog,pod,late,"
            "dispatch_err,inv_no,inv_st,inv_due) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (l["id"], -i, l["cust"], l["o"], l["d"], l["pu"], l["del"], l["status"], l["driver"], l["equip"], l["weight"],
             l["rate"], l["prog"], int(l["pod"]), int(l["late"]), int(l.get("dispatchErr", False)),
             inv.get("no"), inv.get("st"), inv.get("due")))
    con.executemany("INSERT INTO logs (t,sys,dir,type,ref,st,msg,fix) VALUES (?,?,?,?,?,?,?,?)",
                    [(x["t"], x["sys"], x["dir"], x["type"], x["ref"], x["st"], x["msg"], x.get("fix")) for x in data["logs"]])
    for load_id, items in data["msgs"].items():
        con.executemany("INSERT INTO messages (load_id,me,text,t) VALUES (?,?,?,?)",
                        [(load_id, int(m["me"]), m["text"], m["t"]) for m in items])
