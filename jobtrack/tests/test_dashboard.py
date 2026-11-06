import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "dashboard-test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-only-dashboard-key",
                "DATABASE": self.database_path,
            }
        )
        self.client = self.app.test_client()
        self._seed_applications()
        self._login(1, "alex")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_applications(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO users (id, username, email, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (
                    (1, "alex", "alex@example.com", "unused-test-hash"),
                    (2, "sam", "sam@example.com", "unused-test-hash"),
                    (3, "taylor", "taylor@example.com", "unused-test-hash"),
                ),
            )
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, job_location,
                    application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (1, "Northstar Labs", "Python Engineer", "Remote", "Applied", "2026-10-10"),
                    (1, "Brightside", "Platform Engineer", "Boston", "Interview", "2026-10-12"),
                    (1, "Greenfield", "Backend Developer", "Remote", "Selected", "2026-10-14"),
                    (1, "Orbit Works", "API Engineer", "Austin", "Rejected", "2026-10-16"),
                    (1, "Northstar Labs", "Staff Engineer", "Remote", "Interview", "2026-10-18"),
                    (2, "Private Company", "Secret Role", "Private City", "Selected", "2026-10-20"),
                ),
            )
            connection.commit()

    def _login(self, user_id: int, username: str) -> None:
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = user_id
            user_session["username"] = username

    def test_dashboard_shows_user_scoped_statistics_and_recent_rows(self) -> None:
        response = self.client.get("/dashboard")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Welcome back, alex", page)
        for expected in (
            "Total applications",
            "Applied",
            "Interview",
            "Selected",
            "Rejected",
            ">5</strong>",
            ">1</strong>",
            ">2</strong>",
        ):
            self.assertIn(expected, page)
        self.assertIn("Northstar Labs", page)
        self.assertNotIn("Private Company", page)
        self.assertNotIn("Secret Role", page)
        self.assertIn("status-interview", page)
        self.assertIn("My Applications", page)
        self.assertIn("Add Application", page)
        self.assertIn('action="/logout"', page)

    def test_search_and_status_filter_are_applied_to_user_applications(self) -> None:
        response = self.client.get(
            "/dashboard?search=northstar&status=Interview"
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Northstar Labs", page)
        self.assertIn("Staff Engineer", page)
        self.assertNotIn("Python Engineer", page)
        self.assertNotIn("Brightside", page)
        self.assertNotIn("Private Company", page)
        self.assertIn('option value="Interview" selected', page)

    def test_search_treats_wildcards_as_literals_and_status_is_allowlisted(self) -> None:
        wildcard = self.client.get("/dashboard?search=%25")
        self.assertIn(
            "No matching applications", wildcard.get_data(as_text=True)
        )

        invalid_status = self.client.get("/dashboard?status=Anything")
        page = invalid_status.get_data(as_text=True)
        self.assertEqual(invalid_status.status_code, 200)
        self.assertIn("Northstar Labs", page)
        self.assertIn("Brightside", page)

    def test_application_table_is_limited_to_ten_most_recent_matches(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        1,
                        f"Recent Company {day:02d}",
                        "Engineer",
                        "Applied",
                        f"2026-11-{day:02d}",
                    )
                    for day in range(1, 13)
                ),
            )
            connection.commit()

        page = self.client.get("/dashboard").get_data(as_text=True)

        self.assertEqual(page.count('class="company-cell"'), 10)
        self.assertLess(page.index("Recent Company 12"), page.index("Recent Company 03"))
        self.assertIn("Recent Company 03", page)
        self.assertNotIn("Recent Company 02", page)
        self.assertIn("Showing the 10 most recent matches.", page)

    def test_empty_dashboard_displays_real_zero_counts_and_empty_state(self) -> None:
        self._login(3, "taylor")
        response = self.client.get("/dashboard")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Welcome back, taylor", page)
        self.assertIn("Your pipeline starts here", page)
        self.assertRegex(
            page,
            re.compile(r"Total applications</span>.*?<strong>0</strong>", re.DOTALL),
        )
        self.assertNotIn("Northstar Labs", page)

    def test_unauthenticated_dashboard_redirects_to_login(self) -> None:
        with self.client.session_transaction() as user_session:
            user_session.clear()

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")


if __name__ == "__main__":
    unittest.main()
