import logging
import os
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from typing import Any

from flask import Flask, flash, render_template, request, session

from config import Config
from database.db import get_connection, init_db
from routes.auth import auth_bp, generate_csrf_token, login_required
from routes.applications import applications_bp


logger = logging.getLogger(__name__)
APPLICATION_STATUSES = ("Applied", "Interview", "Selected", "Rejected")


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("JOBTRACK_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"}
    )
    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "Set the JOBTRACK_SECRET_KEY environment variable before starting JobTrack."
        )

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    init_db(app.config["DATABASE"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(applications_bp)

    @app.context_processor
    def inject_csrf_token() -> dict[str, Any]:
        return {"csrf_token": generate_csrf_token}

    @app.get("/dashboard")
    @login_required
    def dashboard() -> tuple[str, int] | str:
        search = request.args.get("search", "").strip()[:100]
        selected_status = request.args.get("status", "")
        if selected_status not in APPLICATION_STATUSES:
            selected_status = ""

        user_id = session["user_id"]
        try:
            with closing(get_connection(app.config["DATABASE"])) as connection:
                stats = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN application_status = ? THEN 1 ELSE 0 END), 0) AS applied,
                        COALESCE(SUM(CASE WHEN application_status = ? THEN 1 ELSE 0 END), 0) AS interview,
                        COALESCE(SUM(CASE WHEN application_status = ? THEN 1 ELSE 0 END), 0) AS selected,
                        COALESCE(SUM(CASE WHEN application_status = ? THEN 1 ELSE 0 END), 0) AS rejected
                    FROM applications
                    WHERE user_id = ?
                    """,
                    (*APPLICATION_STATUSES, user_id),
                ).fetchone()

                conditions = ["user_id = ?"]
                parameters: list[Any] = [user_id]
                if search:
                    escaped_search = (
                        search.replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
                    pattern = f"%{escaped_search}%"
                    conditions.append(
                        "(company_name LIKE ? ESCAPE '\\' "
                        "OR job_role LIKE ? ESCAPE '\\' "
                        "OR job_location LIKE ? ESCAPE '\\')"
                    )
                    parameters.extend((pattern, pattern, pattern))
                if selected_status:
                    conditions.append("application_status = ?")
                    parameters.append(selected_status)

                applications = connection.execute(
                    f"""
                    SELECT id, company_name, job_role, job_location, salary,
                           application_status, applied_date
                    FROM applications
                    WHERE {" AND ".join(conditions)}
                    ORDER BY applied_date DESC, created_at DESC, id DESC
                    LIMIT 10
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error:
            logger.exception(
                "Could not load dashboard for user_id=%s", user_id
            )
            flash(
                "Your dashboard could not be loaded. Please try again.",
                "error",
            )
            return render_template(
                "dashboard.html",
                username=session["username"],
                stats=None,
                applications=(),
                statuses=APPLICATION_STATUSES,
                search=search,
                selected_status=selected_status,
                dashboard_error=True,
            ), 500

        return render_template(
            "dashboard.html",
            username=session["username"],
            stats=stats,
            applications=applications,
            statuses=APPLICATION_STATUSES,
            search=search,
            selected_status=selected_status,
            dashboard_error=False,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run()