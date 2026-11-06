import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app import create_app


class ApplicationCrudTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "applications-test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-only-applications-key",
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
            connection.commit()
        self._login(1, "alex")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _login(self, user_id: int, username: str) -> None:
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = user_id
            user_session["username"] = username

    def _csrf_token(self, path: str) -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        return match.group(1)

    @staticmethod
    def _application_form(
        csrf_token: str, **overrides: str
    ) -> dict[str, str]:
        values = {
            "csrf_token": csrf_token,
            "company_name": "Northstar Labs",
            "job_role": "Python Engineer",
            "job_location": "Remote",
            "salary": "$120,000",
            "application_status": "Applied",
            "applied_date": "2026-10-25",
            "job_description": "Build reliable services.",
        }
        values.update(overrides)
        return values

    def _create_application(self) -> int:
        token = self._csrf_token("/applications/add")
        response = self.client.post(
            "/applications/add", data=self._application_form(token)
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/applications")
        with closing(sqlite3.connect(self.database_path)) as connection:
            return connection.execute(
                "SELECT id FROM applications WHERE user_id = ?",
                (1,),
            ).fetchone()[0]

    def test_create_and_read_application(self) -> None:
        self._create_application()
        response = self.client.get("/applications")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Northstar Labs", page)
        self.assertIn("Python Engineer", page)
        self.assertIn("Remote", page)
        self.assertIn("$120,000", page)
        self.assertIn("2026-10-25", page)
        self.assertIn("status-applied", page)
        self.assertIn("Build reliable services.", self._edit_page(1))

    def _edit_page(self, application_id: int) -> str:
        response = self.client.get(f"/applications/{application_id}/edit")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_edit_prefills_form_and_updates_all_fields(self) -> None:
        application_id = self._create_application()
        page = self._edit_page(application_id)
        self.assertIn('value="Northstar Labs"', page)
        self.assertIn('value="$120,000"', page)
        self.assertIn("Build reliable services.", page)

        token = re.search(
            r'name="csrf_token" value="([^"]+)"', page
        ).group(1)
        updated = self._application_form(
            token,
            company_name="Contoso",
            job_role="Senior Engineer",
            job_location="Boston",
            salary="$145,000",
            application_status="Interview",
            applied_date="2026-11-01",
            job_description="Meet the platform team.",
        )
        response = self.client.post(
            f"/applications/{application_id}/edit", data=updated
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("Contoso", self.client.get("/applications").get_data(as_text=True))
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                """
                SELECT company_name, job_role, job_location, salary,
                       application_status, applied_date, job_description, user_id
                FROM applications WHERE id = ?
                """,
                (application_id,),
            ).fetchone()
        self.assertEqual(
            row,
            (
                "Contoso",
                "Senior Engineer",
                "Boston",
                "$145,000",
                "Interview",
                "2026-11-01",
                "Meet the platform team.",
                1,
            ),
        )

    def test_delete_requires_csrf_and_removes_only_selected_record(self) -> None:
        application_id = self._create_application()
        missing_token = self.client.post(
            f"/applications/{application_id}/delete"
        )
        self.assertEqual(missing_token.status_code, 400)

        token = self._csrf_token("/applications")
        response = self.client.post(
            f"/applications/{application_id}/delete",
            data={"csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM applications WHERE id = ?",
                    (application_id,),
                ).fetchone()[0],
                0,
            )

    def test_validation_rejects_bad_fields_and_leaves_database_unchanged(self) -> None:
        token = self._csrf_token("/applications/add")
        response = self.client.post(
            "/applications/add",
            data=self._application_form(
                token,
                company_name="",
                application_status="Unknown",
                applied_date="not-a-date",
            ),
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Company name is required.", page)
        self.assertIn("Choose a valid application status.", page)
        self.assertIn("Enter a valid application date.", page)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0],
                0,
            )

    def test_other_users_cannot_read_edit_or_delete_application(self) -> None:
        application_id = self._create_application()
        self._login(2, "sam")

        self.assertEqual(
            self.client.get(f"/applications/{application_id}/edit").status_code,
            404,
        )
        applications_page = self.client.get("/applications")
        edit_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            applications_page.get_data(as_text=True),
        ).group(1)
        edit_response = self.client.post(
            f"/applications/{application_id}/edit",
            data=self._application_form(edit_token, company_name="Changed by Sam"),
        )
        self.assertEqual(edit_response.status_code, 404)

        delete_response = self.client.post(
            f"/applications/{application_id}/delete",
            data={"csrf_token": edit_token},
        )
        self.assertEqual(delete_response.status_code, 404)
        self.assertNotIn(
            "Northstar Labs",
            self.client.get("/applications").get_data(as_text=True),
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT company_name, user_id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
        self.assertEqual(row, ("Northstar Labs", 1))

    def test_application_routes_require_authentication(self) -> None:
        with self.client.session_transaction() as user_session:
            user_session.clear()

        response = self.client.get("/applications")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

        response = self.client.post("/applications/add", data={})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_search_and_status_filters_are_user_scoped(self) -> None:
        first_id = self._create_application()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (2, "Private Corp", "Secret Role", "Rejected", "2026-10-20"),
            )
            connection.execute(
                """
                UPDATE applications
                SET application_status = ?
                WHERE id = ? AND user_id = ?
                """,
                ("Interview", first_id, 1),
            )
            connection.commit()

        response = self.client.get("/applications?search=northstar&status=Interview")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Northstar Labs", page)
        self.assertNotIn("Private Corp", page)
        self.assertNotIn("Python Engineer", self.client.get(
            "/applications?status=Rejected"
        ).get_data(as_text=True))

    def test_company_role_location_and_status_filters_work_together(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, job_location, salary,
                    application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (1, "Acme", "Python Engineer", "New York", "$100,000", "Interview", "2026-10-10"),
                    (1, "Acme", "Python Engineer", "Remote", "$120,000", "Interview", "2026-10-11"),
                    (1, "Acme", "Designer", "New York", "$110,000", "Interview", "2026-10-12"),
                    (1, "Other Co", "Python Engineer", "New York", "$130,000", "Applied", "2026-10-13"),
                    (2, "Acme", "Python Engineer", "New York", "$999,000", "Interview", "2026-10-14"),
                ),
            )
            connection.commit()

        response = self.client.get(
            "/applications?search=python&location=new%20york&status=Interview"
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("1 matching", page)
        self.assertIn("New York", page)
        self.assertNotIn("$120,000", page)
        self.assertNotIn("$999,000", page)

        role_search = self.client.get("/applications?search=designer")
        role_page = role_search.get_data(as_text=True)
        self.assertIn("1 matching", role_page)
        self.assertIn("Designer", role_page)
        self.assertNotIn("Python Engineer", role_page)

    def test_each_application_status_filter_returns_only_that_status(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (1, f"{status} Company", "Engineer", status, "2026-10-10")
                    for status in ("Applied", "Interview", "Selected", "Rejected")
                ),
            )
            connection.commit()

        for status in ("Applied", "Interview", "Selected", "Rejected"):
            with self.subTest(status=status):
                page = self.client.get(
                    f"/applications?status={status}"
                ).get_data(as_text=True)
                self.assertIn("1 matching", page)
                self.assertIn(f"{status} Company", page)
                for other_status in set(
                    ("Applied", "Interview", "Selected", "Rejected")
                ) - {status}:
                    self.assertNotIn(f"{other_status} Company", page)

    def test_every_sort_option_orders_matching_applications(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, salary,
                    application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (1, "Bravo", "Engineer", "$20,000", "Applied", "2026-10-10"),
                    (1, "alpha", "Engineer", "$100,000", "Applied", "2026-10-12"),
                    (1, "Charlie", "Engineer", "$5,000", "Applied", "2026-10-11"),
                    (1, "Delta", "Engineer", None, "Applied", "2026-10-13"),
                ),
            )
            connection.commit()

        expected_orders = {
            "date_newest": ["Delta", "alpha", "Charlie", "Bravo"],
            "date_oldest": ["Bravo", "Charlie", "alpha", "Delta"],
            "company_az": ["alpha", "Bravo", "Charlie", "Delta"],
            "company_za": ["Delta", "Charlie", "Bravo", "alpha"],
            "salary_high": ["alpha", "Bravo", "Charlie", "Delta"],
            "salary_low": ["Charlie", "Bravo", "alpha", "Delta"],
        }
        for sort_key, expected in expected_orders.items():
            with self.subTest(sort=sort_key):
                response = self.client.get(f"/applications?sort={sort_key}")
                page = response.get_data(as_text=True)
                companies = re.findall(
                    r'<td class="company-cell">(.*?)</td>', page
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(companies, expected)
                self.assertIn("4 total", page)
                self.assertIn(f'value="{sort_key}" selected', page)

    def test_search_filter_sort_combination_count_and_clear_filters(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executemany(
                """
                INSERT INTO applications (
                    user_id, company_name, job_role, job_location, salary,
                    application_status, applied_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (1, "Acme", "Python Engineer", "Remote", "$80,000", "Interview", "2026-10-10"),
                    (1, "Acme", "Python Engineer", "Remote", "$120,000", "Interview", "2026-10-11"),
                    (1, "Acme", "Python Engineer", "Boston", "$150,000", "Applied", "2026-10-12"),
                    (2, "Acme", "Python Engineer", "Remote", "$999,000", "Interview", "2026-10-13"),
                ),
            )
            connection.commit()

        url = (
            "/applications?search=python&location=remote&status=Interview"
            "&sort=salary_high"
        )
        page = self.client.get(url).get_data(as_text=True)
        self.assertIn("2 matching", page)
        self.assertLess(page.index("$120,000"), page.index("$80,000"))
        self.assertNotIn("$150,000", page)
        self.assertNotIn("$999,000", page)
        self.assertIn("Clear filters", page)

        clear_link = re.search(
            r'<a class="clear-filters" href="([^"]+)">Clear filters</a>',
            page,
        ).group(1)
        clear_page = self.client.get(clear_link).get_data(as_text=True)
        self.assertIn("3 total", clear_page)
        self.assertNotIn("Clear filters", clear_page)

    def test_invalid_sort_is_rejected_and_no_results_are_friendly(self) -> None:
        response = self.client.get(
            "/applications?sort=company_az%3BDROP%20TABLE%20users"
            "&search=missing"
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No matching applications", page)
        self.assertIn('value="date_newest" selected', page)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertIsNotNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
                    ("table", "users"),
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
