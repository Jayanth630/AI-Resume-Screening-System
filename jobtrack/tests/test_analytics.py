import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from app import create_app


class AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "analytics-test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-only-analytics-key",
                "DATABASE": self.database_path,
            }
        )
        self.client = self.app.test_client()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO users (id, username, email, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (
                    (1, "alex", "alex@example.com", "unused-test-hash"),
                    (2, "sam", "sam@example.com", "unused-test-hash"),
                ),
            )
            self.month_dates = self._month_dates()
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, application_status,
                    applied_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (1, "Acme", "Engineer", "Applied", self.month_dates[0]),
                    (1, "Acme", "Designer", "Interview", self.month_dates[0]),
                    (1, "Beta", "Analyst", "Selected", self.month_dates[0]),
                    (1, "Zulu", "Engineer", "Applied", self.month_dates[1]),
                    (1, "Acme", "Manager", "Rejected", self.month_dates[1]),
                    (1, "Zulu", "Engineer", "Interview", self.month_dates[2]),
                    (2, "Private Company", "Secret Role", "Selected", self.month_dates[0]),
                ),
            )
            connection.commit()
        self._login(1, "alex")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _month_dates() -> list[str]:
        current = date.today().replace(day=15)
        previous = (current.replace(day=1) - timedelta(days=1)).replace(day=15)
        older = (previous.replace(day=1) - timedelta(days=1)).replace(day=15)
        outside_range = older.replace(day=1)
        for _ in range(13):
            outside_range = (outside_range.replace(day=1) - timedelta(days=1)).replace(day=1)
        return [
            current.isoformat(),
            previous.isoformat(),
            older.isoformat(),
            outside_range.isoformat(),
        ]

    def _login(self, user_id: int, username: str) -> None:
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = user_id
            user_session["username"] = username

    def _chart_data(self, page: str) -> dict[str, object]:
        match = re.search(
            r'<script id="analytics-data" type="application/json">(.*?)</script>',
            page,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_analytics_shows_user_scoped_status_totals_and_rates(self) -> None:
        response = self.client.get("/applications/analytics")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Hi alex", page)
        self.assertIn("Analytics", page)
        self.assertIn(">6</strong>", page)
        self.assertIn("Interview conversion", page)
        self.assertIn(">33.3%</strong>", page)
        self.assertIn("Selection rate", page)
        self.assertIn(">16.7%</strong>", page)
        self.assertNotIn("Private Company", page)
        self.assertNotIn("Secret Role", page)
        self.assertIn('id="status-chart"', page)
        self.assertIn('id="monthly-chart"', page)

    def test_charts_use_real_status_and_monthly_database_counts(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (1, "Zulu", "Engineer", "Applied", self.month_dates[3]),
            )
            connection.commit()

        response = self.client.get("/applications/analytics")
        chart_data = self._chart_data(response.get_data(as_text=True))

        self.assertEqual(
            chart_data["statusLabels"],
            ["Applied", "Interview", "Selected", "Rejected"],
        )
        self.assertEqual(chart_data["statusValues"], [3, 2, 1, 1])
        self.assertEqual(len(chart_data["monthlyLabels"]), 12)
        self.assertEqual(sum(chart_data["monthlyValues"]), 6)
        self.assertEqual(chart_data["monthlyValues"][-3:], [1, 2, 3])
        self.assertEqual(chart_data["companyLabels"], ["Acme", "Zulu", "Beta"])
        self.assertEqual(chart_data["companyValues"], [3, 3, 1])

    def test_top_companies_and_recent_activity_are_user_scoped(self) -> None:
        response = self.client.get("/applications/analytics")
        page = response.get_data(as_text=True)

        self.assertIn("Top companies", page)
        self.assertIn("Acme", page)
        self.assertIn("3 applications", page)
        self.assertIn("Recent activity", page)
        self.assertNotIn("Private Company", page)
        self.assertNotIn("Secret Role", page)

    def test_empty_analytics_has_zero_rates_and_empty_chart_data(self) -> None:
        self._login(2, "sam")
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "DELETE FROM applications WHERE user_id = ?", (2,)
            )
            connection.commit()

        response = self.client.get("/applications/analytics")
        page = response.get_data(as_text=True)
        chart_data = self._chart_data(page)

        self.assertEqual(response.status_code, 200)
        self.assertIn("No applications", page)
        self.assertIn(">0.0%</strong>", page)
        self.assertEqual(chart_data["statusValues"], [0, 0, 0, 0])
        self.assertEqual(chart_data["monthlyValues"], [0] * 12)
        self.assertEqual(chart_data["companyLabels"], [])
        self.assertIn("will appear here", page)

    def test_analytics_requires_authentication(self) -> None:
        with self.client.session_transaction() as user_session:
            user_session.clear()

        response = self.client.get("/applications/analytics")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")


if __name__ == "__main__":
    unittest.main()
