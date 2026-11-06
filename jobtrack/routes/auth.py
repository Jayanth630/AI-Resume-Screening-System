import hmac
import logging
import re
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import closing
from functools import wraps
from typing import Any, TypeVar, cast

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
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_connection


auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)
ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z")
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{3,30}\Z")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def generate_csrf_token() -> str:
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token() -> bool:
    submitted_token = request.form.get("csrf_token", "")
    session_token = session.get("_csrf_token", "")
    return bool(submitted_token and session_token) and hmac.compare_digest(
        submitted_token, session_token
    )


def login_required(view: ViewFunction) -> ViewFunction:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session:
            flash("Please log in to view your dashboard.", "info")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped_view)


def _render_registration(
    username: str = "", email: str = "", status: int = 200
) -> tuple[str, int]:
    return render_template(
        "register.html", username=username, email=email
    ), status


def _render_login(email: str = "", status: int = 200) -> tuple[str, int]:
    return render_template("login.html", email=email), status


@auth_bp.route("/register", methods=["GET", "POST"])
def register() -> Any:
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return _render_registration()
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        return _render_registration(status=400)

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not USERNAME_PATTERN.fullmatch(username):
        flash(
            "Username must be 3–30 characters and contain only letters, "
            "numbers, dots, underscores, or hyphens.",
            "error",
        )
        return _render_registration(username, email, 400)
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        flash("Enter a valid email address.", "error")
        return _render_registration(username, email, 400)
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        flash(
            f"Password must be between {MIN_PASSWORD_LENGTH} and "
            f"{MAX_PASSWORD_LENGTH} characters.",
            "error",
        )
        return _render_registration(username, email, 400)

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            with connection:
                existing_user = connection.execute(
                    "SELECT id FROM users WHERE lower(email) = ?",
                    (email,),
                ).fetchone()
                if existing_user is not None:
                    flash("An account with that email already exists.", "error")
                    return _render_registration(username, email, 409)

                connection.execute(
                    """
                    INSERT INTO users (username, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (username, email, generate_password_hash(password)),
                )
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error):
            flash("An account with that email already exists.", "error")
            return _render_registration(username, email, 409)
        logger.exception("Could not register user because of a database constraint")
        flash("We could not create your account. Please try again.", "error")
        return _render_registration(username, email, 500)
    except sqlite3.Error:
        logger.exception("Database error while registering a user")
        flash("We could not create your account. Please try again.", "error")
        return _render_registration(username, email, 500)

    flash("Your account is ready. Please log in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Any:
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return _render_login()
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        return _render_login(status=400)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if (
        len(email) > 254
        or not EMAIL_PATTERN.fullmatch(email)
        or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
    ):
        flash("Enter a valid email address and password.", "error")
        return _render_login(email, 400)

    try:
        with closing(get_connection(current_app.config["DATABASE"])) as connection:
            user = connection.execute(
                """
                SELECT id, username, email, password_hash
                FROM users
                WHERE lower(email) = ?
                """,
                (email,),
            ).fetchone()
    except sqlite3.Error:
        logger.exception("Database error while logging in")
        flash("We could not log you in right now. Please try again.", "error")
        return _render_login(email, 500)

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return _render_login(email, 401)

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    flash("Welcome back.", "success")
    return redirect(url_for("dashboard"))


@auth_bp.post("/logout")
def logout() -> Any:
    if not validate_csrf_token():
        flash("Your form expired. Please try again.", "error")
        return redirect(url_for("dashboard" if "user_id" in session else "auth.login"))
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))