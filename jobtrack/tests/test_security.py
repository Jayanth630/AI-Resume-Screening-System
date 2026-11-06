import sqlite3
from contextlib import closing

import pytest

from app import create_app


@pytest.fixture
def application(tmp_path):
    database_path = tmp_path / "security-test.db"
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-security-key",
            "DATABASE": database_path,
        }
    )
    return app


def test_secure_cookie_environment_sets_secure_session_cookie(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JOBTRACK_COOKIE_SECURE", "true")
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-cookie-key",
            "DATABASE": tmp_path / "secure-cookie.db",
        }
    )

    response = app.test_client().get("/login")

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert "Secure" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]


def test_analytics_chart_library_uses_subresource_integrity(application):
    client = application.test_client()
    with client.session_transaction() as user_session:
        user_session["user_id"] = 1
        user_session["username"] = "alex"

    response = client.get("/applications/analytics")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert (
        'integrity="sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC"'
        in page
    )
    assert 'crossorigin="anonymous"' in page


def test_application_text_is_html_escaped(application):
    database_path = application.config["DATABASE"]
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, email, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (1, "alex", "alex@example.com", "unused-test-hash"),
        )
        connection.execute(
            """
            INSERT INTO applications (
                user_id, company_name, job_role, application_status, applied_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                1,
                "<script>alert(1)</script>",
                "Engineer",
                "Applied",
                "2026-10-25",
            ),
        )
        connection.commit()

    client = application.test_client()
    with client.session_transaction() as user_session:
        user_session["user_id"] = 1
        user_session["username"] = "alex"

    response = client.get("/applications")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


@pytest.mark.parametrize(
    ("path", "method", "payload"),
    [
        ("/applications/add", "post", {"company_name": "Acme"}),
        ("/applications/1/edit", "post", {"company_name": "Changed", "id": "999"}),
        ("/applications/1/delete", "post", {}),
        ("/logout", "post", {}),
    ],
)
def test_state_changing_requests_require_csrf(application, path, method, payload):
    with closing(sqlite3.connect(application.config["DATABASE"])) as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, email, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (1, "alex", "alex@example.com", "unused-test-hash"),
        )
        connection.execute(
            """
            INSERT INTO applications (
                id, user_id, company_name, job_role, application_status, applied_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, 1, "Acme", "Engineer", "Applied", "2026-10-25"),
        )
        connection.commit()

    client = application.test_client()
    with client.session_transaction() as user_session:
        user_session["user_id"] = 1
        user_session["username"] = "alex"
        user_session["_csrf_token"] = "expected-token"

    response = getattr(client, method)(path, data=payload)

    if path == "/logout":
        assert response.status_code == 302
        with client.session_transaction() as user_session:
            assert user_session["user_id"] == 1
    else:
        assert response.status_code == 400
        if path == "/applications/1/edit":
            assert (
                'action="/applications/1/edit"'
                in response.get_data(as_text=True)
            )
