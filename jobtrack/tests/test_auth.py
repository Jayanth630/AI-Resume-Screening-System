import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from werkzeug.security import check_password_hash

from app import create_app


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test-jobtrack.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-only-session-key",
                "DATABASE": self.database_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def csrf_token(self, path: str) -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def register(self, email: str = "alex@example.com") -> None:
        token = self.csrf_token("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": "alex.morgan",
                "email": email,
                "password": "a-secure-test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_registration_stores_only_password_hash(self) -> None:
        self.register()

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT username, email, password_hash FROM users WHERE email = ?",
                ("alex@example.com",),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "alex.morgan")
        self.assertNotEqual(row[2], "a-secure-test-password")
        self.assertTrue(check_password_hash(row[2], "a-secure-test-password"))

    def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        self.register()
        token = self.csrf_token("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": "another.user",
                "email": "ALEX@example.com",
                "password": "another-secure-password",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "An account with that email already exists.",
            response.get_data(as_text=True),
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                1,
            )

    def test_login_dashboard_protection_and_logout(self) -> None:
        protected = self.client.get("/dashboard")
        self.assertEqual(protected.status_code, 302)
        self.assertEqual(protected.headers["Location"], "/login")

        self.register()
        token = self.csrf_token("/login")
        incorrect_password = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": "alex@example.com",
                "password": "incorrect-password",
            },
        )
        self.assertEqual(incorrect_password.status_code, 401)
        self.assertIn(
            "Invalid email or password.",
            incorrect_password.get_data(as_text=True),
        )

        login_response = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": "alex@example.com",
                "password": "a-secure-test-password",
            },
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers["Location"], "/dashboard")

        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Welcome back, alex.morgan", dashboard.get_data(as_text=True))
        logout_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            dashboard.get_data(as_text=True),
        ).group(1)
        logout_response = self.client.post(
            "/logout", data={"csrf_token": logout_token}
        )
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers["Location"], "/login")

        protected_after_logout = self.client.get("/dashboard")
        self.assertEqual(protected_after_logout.status_code, 302)
        self.assertEqual(protected_after_logout.headers["Location"], "/login")

    def test_invalid_registration_and_missing_csrf_are_rejected(self) -> None:
        token = self.csrf_token("/register")
        invalid_submissions = (
            (
                {"username": "x", "email": "alex@example.com", "password": "long-enough"},
                "Username must be 3",
            ),
            (
                {
                    "username": "alex.morgan",
                    "email": "not-an-email",
                    "password": "long-enough",
                },
                "Enter a valid email address.",
            ),
            (
                {"username": "alex.morgan", "email": "alex@example.com", "password": "short"},
                "Password must be between 8 and 128 characters.",
            ),
        )
        for fields, expected_message in invalid_submissions:
            with self.subTest(fields=fields):
                response = self.client.post(
                    "/register", data={"csrf_token": token, **fields}
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected_message, response.get_data(as_text=True))

        missing_csrf = self.client.post(
            "/register",
            data={
                "username": "alex.morgan",
                "email": "alex@example.com",
                "password": "a-secure-test-password",
            },
        )
        self.assertEqual(missing_csrf.status_code, 400)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
