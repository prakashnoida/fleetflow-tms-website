"""End-to-end business rules against a temporary database.  Run:  python -m unittest discover tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import db, services  # noqa: E402


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        self.con = db.connect()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def load(self, load_id):
        return services.get_load(self.con, load_id)

    def test_full_load_lifecycle(self):
        lid = services.create_load(self.con, {"cust": "Northwind Foods", "o": "Atlanta, GA", "d": "Charlotte, NC",
                                              "pu": "Nov 20, 08:00", "del": "Nov 20, 16:00", "equip": "53' Dry Van",
                                              "weight": 30000, "rate": 900})["id"]
        self.assertEqual(self.load(lid)["status"], "Booked")
        services.assign(self.con, lid, "D-03")
        self.assertEqual(self.load(lid)["status"], "Planned")
        services.dispatch(self.con, lid)
        self.assertEqual(self.load(lid)["status"], "Dispatched")
        for _ in range(60):
            services.tick(self.con)
        self.assertEqual(self.load(lid)["status"], "Delivered")
        services.attach_pod(self.con, lid)
        services.invoice(self.con, lid)
        self.assertEqual(self.load(lid)["inv_st"], "Open")
        services.mark_paid(self.con, lid)
        self.assertEqual(self.load(lid)["inv_st"], "Paid")

    def test_invoice_blocked_without_pod(self):
        with self.assertRaises(services.ApiError):
            services.invoice(self.con, "LD-24097")  # delivered, POD missing
        services.attach_pod(self.con, "LD-24097")
        services.invoice(self.con, "LD-24097")
        self.assertEqual(self.load("LD-24097")["status"], "Invoiced")

    def test_dispatch_fails_until_truck_is_mapped(self):
        self.assertTrue(services.dispatch(self.con, "LD-24108").get("error"))  # T-1052 has no mapping
        self.assertEqual(self.load("LD-24108")["dispatch_err"], 1)
        services.map_truck(self.con, "T-1052")
        self.assertFalse(services.dispatch(self.con, "LD-24108").get("error"))
        self.assertEqual(self.load("LD-24108")["dispatch_err"], 0)

    def test_busy_driver_cannot_take_second_load(self):
        with self.assertRaises(services.ApiError):
            services.assign(self.con, "LD-24104", "D-01")  # D-01 is in transit on LD-24101

    def test_validation(self):
        with self.assertRaises(services.ApiError):
            services.create_load(self.con, {"cust": "Northwind Foods", "o": "Atlanta, GA", "d": "Atlanta, GA",
                                            "pu": "x", "del": "y", "equip": "z", "weight": 1, "rate": 1})

    def test_edi_tender_creates_booked_load(self):
        before = len(services.list_loads(self.con))
        lid = services.edi_204(self.con)["id"]
        self.assertEqual(len(services.list_loads(self.con)), before + 1)
        self.assertGreater(self.load(lid)["rate"], 0)


if __name__ == "__main__":
    unittest.main()
