import logging
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import date, timedelta
from typing import Any

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database.db import get_connection
from routes.auth import login_required, validate_csrf_token


applications_bp = Blueprint("applications", __name__, url_prefix="/applications")
logger = logging.getLogger(__name__)
APPLICATION_STATUSES = ("Applied", "Interview", "Selected", "Rejected")
FIELD_LIMITS = {
    "company_name": 120,
    "job_role": 120,
    "job_location": 120,
    "salary": 80,
    "job_description": 5000,
}
APPLICATION_COLUMNS = """
    id, company_name, job_role, job_location, salary,
    application_status, applied_date, job_description
"""
APPLICATION_SORTS = {
    "date_newest": (
        "Application date: newest first",
        "applied_date DESC, created_at DESC, id DESC",
    ),
    "date_oldest": (
        "Application date: oldest first",
        "applied_date ASC, created_at ASC, id ASC",
    ),
    "company_az": (
        "Company name: A–Z",
        "company_name COLLATE NOCASE ASC, id ASC",
    ),
    "company_za": (
        "Company name: Z–A",
        "company_name COLLATE NOCASE DESC, id DESC",
    ),
    "salary_high": (
        "Salary: highest first",
        "CASE WHEN salary IS NULL OR trim(salary) = '' THEN 1 ELSE 0 END ASC, "
        "CAST(REPLACE(REPLACE(REPLACE(REPLACE(salary, '$', ''), ',', ''), "
        "' ', ''), 'USD', '') AS REAL) DESC, "
        "applied_date DESC, id DESC",
    ),
    "salary_low": (
        "Salary: lowest first",
        "CASE WHEN salary IS NULL OR trim(salary) = '' THEN 1 ELSE 0 END ASC, "
        "CAST(REPLACE(REPLACE(REPLACE(REPLACE(salary, '$', ''), ',', ''), "
        "' ', ''), 'USD', '') AS REAL) ASC, "
        "applied_date DESC, id DESC",
    ),
}


def _validate_application(form: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    values = {
        "company_name": form.get("company_name", "").strip(),
        "job_role": form.get("job_role", "").strip(),
        "job_location": form.get("job_location", "").strip(),
        "salary": form.get("salary", "").strip(),
        "application_status": form.get("application_status", "").strip(),
        "applied_date": form.get("applied_date", "").strip(),
        "job_description": form.get("job_description", "").strip(),
    }
    errors = []

    for field in ("company_name", "job_role"):
        if not values[field]:
            errors.append(f"{field.replace('_', ' ').capitalize()} is required.")
        elif len(values[field]) > FIELD_LIMITS[field]:
            errors.append(
                f"{field.replace('_', ' ').capitalize()} must be "
                f"{FIELD_LIMITS[field]} characters or fewer."
            )

    for field in ("job_location", "salary", "job_description"):
        if len(values[field]) > FIELD_LIMITS[field]:
            errors.append(
                f"{field.replace('_', ' ').capitalize()} must be "
                f"{FIELD_LIMITS[field]} characters or fewer."
            )

    if values["application_status"] not in APPLICATION_STATUSES:
        errors.append("Choose a valid application status.")

    try:
        date.fromisoformat(values["applied_date"])
    except ValueError:
        errors.append("Enter a valid application date.")

    return values, errors


def _render_form(
    values: Mapping[str, Any],
    *,
    editing: bool,
    status_code: int = 200,
) -> tuple[str, int]:
    return (
        render_template(
            "application_form.html",
            application=values,
            editing=editing,
            statuses=APPLICATION_STATUSES,
        ),
        status_code,
    )


def _owned_application(application_id: int) -> sqlite3.Row | None:
    with closing(get_connection(current_app.config["DATABASE"])) as connection:
        return connection.execute(
            f"""
            SELECT {APPLICATION_COLUMNS}
            FROM applications
            WHERE id = ? AND user_id = ?
            """,
            (application_id, session["user_id"]),
        ).fetchone()


@applications_bp.get("")
@login_required
def list_applications() -> tuple[str, int] | str:
    search = request.args.get("search", "").strip()[:100]
    location = request.args.get("location", "").strip()[:100]
    selected_status = request.args.get("status", "")
    if selected_status not in APPLICATION_STATUSES:
        selected_status = ""
    selected_sort = request.args.get("sort", "date_newest")
    if selected_sort not in APPLICATION_SORTS:
        selected_sort = "date_newest"

    conditions = ["user_id = ?"]
    parameters: list[Any] = [session["user_id"]]
    if search:
        escaped_search = (
            search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped_search}%"
        conditions.append(
            "(company_name LIKE ? ESCAPE '\\' OR job_role LIKE ? ESCAPE '\\')"
        )
        parameters.extend((pattern, pattern))
    if location:
        escaped_location = location.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("job_location LIKE ? ESCAPE '\\'")
        parameters.append(f"%{escaped_location}%")
    if selected_status:
        conditions.append("application_status = ?")
        parameters.append(selected_status)

    where_clause = " AND ".join(conditions)
    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            total_count = connection.execute(
                f"SELECT COUNT(*) FROM applications WHERE {where_clause}",
                parameters,
            ).fetchone()[0]
            applications = connection.execute(
                f"""
                SELECT {APPLICATION_COLUMNS}
                FROM applications WHERE {where_clause}
                ORDER BY {APPLICATION_SORTS[selected_sort][1]}
                """,
                parameters,
            ).fetchall()
    except sqlite3.Error:
        logger.exception(
            "Could not list applications for user_id=%s", session["user_id"]
        )
        flash("Your applications could not be loaded. Please try again.", "error")
        return render_template(
            "applications.html",
            applications=(),
            total_count=0,
            statuses=APPLICATION_STATUSES,
            search=search,
            location=location,
            selected_status=selected_status,
            selected_sort=selected_sort,
            sort_options=APPLICATION_SORTS,
            filters_active=bool(search or location or selected_status),
            applications_error=True,
        ), 500

    return render_template(
        "applications.html",
        applications=applications,
        total_count=total_count,
        statuses=APPLICATION_STATUSES,
        search=search,
        location=location,
        selected_status=selected_status,
        selected_sort=selected_sort,
        sort_options=APPLICATION_SORTS,
        filters_active=bool(search or location or selected_status),
        applications_error=False,
    )


@applications_bp.get("/analytics")
@login_required
def analytics() -> tuple[str, int] | str:
    user_id = session["user_id"]
    current_month = date.today().replace(day=1)
    first_month = current_month
    for _ in range(11):
        first_month = (first_month - timedelta(days=1)).replace(day=1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)

    month_keys = []
    month = first_month
    while month < next_month:
        month_keys.append(month.strftime("%Y-%m"))
        month = (month + timedelta(days=32)).replace(day=1)

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
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
            monthly_rows = connection.execute(
                """
                SELECT substr(applied_date, 1, 7) AS month, COUNT(*) AS total
                FROM applications
                WHERE user_id = ? AND applied_date >= ? AND applied_date < ?
                GROUP BY substr(applied_date, 1, 7)
                """,
                (
                    user_id,
                    first_month.isoformat(),
                    next_month.isoformat(),
                ),
            ).fetchall()
            top_companies = connection.execute(
                """
                SELECT company_name, COUNT(*) AS total
                FROM applications
                WHERE user_id = ?
                GROUP BY company_name
                ORDER BY total DESC, company_name COLLATE NOCASE ASC
                LIMIT 5
                """,
                (user_id,),
            ).fetchall()
            recent_activity = connection.execute(
                """
                SELECT company_name, job_role, application_status,
                       applied_date, created_at
                FROM applications
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 8
                """,
                (user_id,),
            ).fetchall()
    except sqlite3.Error:
        logger.exception("Could not load analytics for user_id=%s", user_id)
        flash("Your analytics could not be loaded. Please try again.", "error")
        return render_template(
            "analytics.html",
            username=session["username"],
            analytics_error=True,
        ), 500

    total = stats["total"]
    interview_rate = round(stats["interview"] / total * 100, 1) if total else 0
    selection_rate = round(stats["selected"] / total * 100, 1) if total else 0
    monthly_totals = {row["month"]: row["total"] for row in monthly_rows}
    chart_data = {
        "statusLabels": list(APPLICATION_STATUSES),
        "statusValues": [stats[status.lower()] for status in APPLICATION_STATUSES],
        "monthlyLabels": [
            date.fromisoformat(f"{month_key}-01").strftime("%b %Y")
            for month_key in month_keys
        ],
        "monthlyValues": [monthly_totals.get(month_key, 0) for month_key in month_keys],
        "companyLabels": [row["company_name"] for row in top_companies],
        "companyValues": [row["total"] for row in top_companies],
    }

    return render_template(
        "analytics.html",
        username=session["username"],
        analytics_error=False,
        stats=stats,
        interview_rate=interview_rate,
        selection_rate=selection_rate,
        top_companies=top_companies,
        recent_activity=recent_activity,
        chart_data=chart_data,
    )


@applications_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_application() -> Any:
    values: dict[str, Any] = {
        "company_name": "",
        "job_role": "",
        "job_location": "",
        "salary": "",
        "application_status": "Applied",
        "applied_date": date.today().isoformat(),
        "job_description": "",
    }
    if request.method == "GET":
        return _render_form(values, editing=False)
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        values.update(request.form)
        return _render_form(values, editing=False, status_code=400)

    values, errors = _validate_application(request.form)
    if errors:
        for error in errors:
            flash(error, "error")
        return _render_form(values, editing=False, status_code=400)

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO applications (
                        user_id, company_name, job_role, job_location, salary,
                        application_status, applied_date, job_description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session["user_id"],
                        values["company_name"],
                        values["job_role"],
                        values["job_location"] or None,
                        values["salary"] or None,
                        values["application_status"],
                        values["applied_date"],
                        values["job_description"] or None,
                    ),
                )
    except sqlite3.Error:
        logger.exception(
            "Could not create application for user_id=%s", session["user_id"]
        )
        flash("The application could not be saved. Please try again.", "error")
        return _render_form(values, editing=False, status_code=500)

    flash("Application added successfully.", "success")
    return redirect(url_for("applications.list_applications"))


@applications_bp.route("/<int:application_id>/edit", methods=["GET", "POST"])
@login_required
def edit_application(application_id: int) -> Any:
    try:
        application = _owned_application(application_id)
    except sqlite3.Error:
        logger.exception(
            "Could not load application %s for user_id=%s",
            application_id,
            session["user_id"],
        )
        flash("The application could not be loaded. Please try again.", "error")
        return redirect(url_for("applications.list_applications")), 303

    if application is None:
        return "Application not found.", 404

    if request.method == "GET":
        return _render_form(dict(application), editing=True)
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        values = dict(application)
        values.update(
            {key: value for key, value in request.form.items() if key != "id"}
        )
        return _render_form(values, editing=True, status_code=400)

    values, errors = _validate_application(request.form)
    if errors:
        for error in errors:
            flash(error, "error")
        return _render_form(values, editing=True, status_code=400)

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE applications
                    SET company_name = ?, job_role = ?, job_location = ?,
                        salary = ?, application_status = ?, applied_date = ?,
                        job_description = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        values["company_name"],
                        values["job_role"],
                        values["job_location"] or None,
                        values["salary"] or None,
                        values["application_status"],
                        values["applied_date"],
                        values["job_description"] or None,
                        application_id,
                        session["user_id"],
                    ),
                )
                if cursor.rowcount != 1:
                    return "Application not found.", 404
    except sqlite3.Error:
        logger.exception(
            "Could not update application %s for user_id=%s",
            application_id,
            session["user_id"],
        )
        flash("The application could not be updated. Please try again.", "error")
        return _render_form(values, editing=True, status_code=500)

    flash("Application updated successfully.", "success")
    return redirect(url_for("applications.list_applications"))


@applications_bp.post("/<int:application_id>/delete")
@login_required
def delete_application(application_id: int) -> Any:
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        return redirect(url_for("applications.list_applications")), 400

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM applications WHERE id = ? AND user_id = ?",
                    (application_id, session["user_id"]),
                )
                if cursor.rowcount != 1:
                    return "Application not found.", 404
    except sqlite3.Error:
        logger.exception(
            "Could not delete application %s for user_id=%s",
            application_id,
            session["user_id"],
        )
        flash("The application could not be deleted. Please try again.", "error")
        return redirect(url_for("applications.list_applications")), 500

    flash("Application deleted successfully.", "success")
    return redirect(url_for("applications.list_applications"))