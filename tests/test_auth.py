"""Account rules against a temporary database.  Run:  python -m unittest discover tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import auth, db, services  # noqa: E402

GOOD = {"name": "Asha Rao", "email": "Asha@Example.com", "password": "correct-horse"}


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db.init_db()
        self.con = db.connect()
        auth._failed.clear()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_register_login_logout(self):
        user, token = auth.register(self.con, GOOD)
        self.assertEqual(user["email"], "asha@example.com")       # normalised
        self.assertEqual(user["role"], "Admin")                    # first account
        self.assertEqual(auth.current_user(self.con, token)["name"], "Asha Rao")
        _, token2 = auth.login(self.con, {"email": "asha@example.com", "password": "correct-horse"})
        auth.logout(self.con, token2)
        self.assertIsNone(auth.current_user(self.con, token2))
        self.assertIsNotNone(auth.current_user(self.con, token))   # other session unaffected

    def test_password_is_not_stored(self):
        auth.register(self.con, GOOD)
        row = self.con.execute("SELECT * FROM users").fetchone()
        self.assertNotIn("correct-horse", " ".join(str(v) for v in tuple(row)))
        self.assertEqual(len(row["pw_hash"]), 64)

    def test_duplicate_and_invalid_input(self):
        auth.register(self.con, GOOD)
        for body in (GOOD, {**GOOD, "email": "nope"}, {**GOOD, "email": "b@x.com", "password": "short"},
                     {**GOOD, "email": "c@x.com", "name": ""}):
            with self.assertRaises(services.ApiError):
                auth.register(self.con, body)
        second, _ = auth.register(self.con, {**GOOD, "email": "d@x.com"})
        self.assertEqual(second["role"], "Dispatcher")

    def test_wrong_password_and_lockout(self):
        auth.register(self.con, GOOD)
        for _ in range(auth.MAX_FAILED):
            with self.assertRaises(services.ApiError) as cm:
                auth.login(self.con, {"email": "asha@example.com", "password": "wrong-password"})
            self.assertEqual(cm.exception.status, 401)
        with self.assertRaises(services.ApiError) as cm:           # locked even with the right password
            auth.login(self.con, {"email": "asha@example.com", "password": "correct-horse"})
        self.assertEqual(cm.exception.status, 429)

    def test_bad_or_expired_token(self):
        _, token = auth.register(self.con, GOOD)
        self.assertIsNone(auth.current_user(self.con, "not-a-token"))
        self.con.execute("UPDATE sessions SET expires_at=0")
        self.assertIsNone(auth.current_user(self.con, token))

    def test_reset_keeps_accounts(self):
        _, token = auth.register(self.con, GOOD)
        db.build(self.con, reset=True)
        self.assertIsNotNone(auth.current_user(self.con, token))


if __name__ == "__main__":
    unittest.main()
