# JobTrack

JobTrack is a Flask web application for keeping a personal job search organized. It lets each user record opportunities, follow their progress through an application pipeline, and review dashboard and analytics views. The application stores data in SQLite and renders its pages with Flask and Jinja.

> **Project status:** The features and routes described as implemented below are present in this repository. Deployment guidance is a suggested procedure, not a claim that the application is currently deployed or production-certified. Planned ideas are listed separately.

## Project overview and objectives

JobTrack provides a single place to:

- Record job applications and their details.
- Track status changes from application through interview, selection, or rejection.
- Search, filter, and sort a user's own application list.
- Review counts, recent opportunities, and job-search activity over time.

The project also demonstrates a small full-stack web application: Flask routing and session authentication, relational data persistence, server-rendered templates, client-side charts, and automated tests.

## Technology stack

| Area | Technology |
|---|---|
| Language | Python 3.10+ |
| Web framework | Flask 3.1+ |
| HTTP and security utilities | Werkzeug 3.1+ |
| Database | SQLite |
| UI | HTML, CSS, JavaScript, and Jinja templates |
| Charts | Chart.js, loaded by the analytics page from a CDN with Subresource Integrity |
| Tests | pytest 8.3+ and Python `unittest` test cases |

Dependency ranges are recorded in [`requirements.txt`](requirements.txt). No JavaScript package manager or ORM is used.

## Implemented features

- Account registration, login, and logout.
- Password hashing and verification using Werkzeug.
- Session-backed authentication and access control for user pages.
- CSRF token validation on state-changing form submissions.
- User-scoped application creation, listing, editing, and deletion.
- Application fields for company, role, location, salary, status, date, and job notes.
- Search by company or role; location and status filters; six sort modes for date, company, and salary.
- Dashboard with status totals, search, status filtering, and up to ten recent matching applications.
- Analytics page with status totals, interview and selection rates, a 12-month activity chart, top companies, and recent activity.
- Responsive interface with empty states and client-side analytics charts.
- Form validation, output escaping through Jinja, and secure cookie options.
- Database initialization on application startup, without inserting sample records.

### Not implemented

- A public or private JSON REST API; the application exposes HTML pages and form workflows.
- Resume parsing, AI or automated candidate matching, notifications, or external job-board integrations.
- Pagination for the complete application list.
- Password reset, email verification, or multi-factor authentication.
- A production deployment configuration or a managed database setup.

## Project structure

```text
jobtrack/
├── app.py                     # Flask app factory, dashboard route, and development entry point
├── config.py                  # Secret key and default database configuration
├── requirements.txt           # Python dependency ranges
├── database/
│   └── db.py                  # SQLite connection and idempotent schema initialization
├── routes/
│   ├── auth.py                # Registration, login, logout, CSRF, and auth decorator
│   └── applications.py        # Application list, analytics, create, update, and delete
├── templates/
│   ├── base.html              # Shared page layout
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── applications.html
│   ├── application_form.html
│   └── analytics.html
├── static/
│   ├── css/style.css
│   └── js/
│       ├── script.js
│       └── analytics.js
├── tests/
│   ├── test_auth.py
│   ├── test_applications.py
│   ├── test_dashboard.py
│   ├── test_analytics.py
│   └── test_security.py
└── instance/
    └── jobtrack.db             # Local SQLite database, created/used at runtime
```

Virtual environments and test caches are local development artifacts and are not part of the application source tree.

## Application architecture

1. **Application setup:** `app.py` creates the Flask app, loads `Config`, checks that a session secret exists, initializes SQLite, registers route blueprints, and provides a CSRF token to templates.
2. **Request handling:** The root dashboard route is in `app.py`. Authentication routes are grouped in the `auth` blueprint. Application list, analytics, and CRUD routes are grouped under `/applications` in the `applications` blueprint.
3. **Authentication and request protection:** Successful login stores the user ID and username in Flask's signed session. Protected views use `login_required`. POST forms use a session token and constant-time comparison for CSRF validation.
4. **Persistence:** Route handlers use parameterized SQLite queries through helpers in `database/db.py`. The `applications` queries include the authenticated user's ID to keep records scoped to their owner.
5. **Presentation:** Flask renders Jinja templates using database-backed view data. The analytics route embeds chart data in the page; `static/js/analytics.js` uses Chart.js to render charts in the browser.

This is a compact, server-rendered monolith. It does not have a separate frontend application, service layer, ORM, or REST API.

## Database schema

The app initializes two tables with `CREATE TABLE IF NOT EXISTS`. The SQLite file defaults to `instance/jobtrack.db`. Foreign-key enforcement is enabled for application connections.

### `users`

| Column | SQLite type | Nullability / constraint | Description |
|---|---|---|---|
| `id` | INTEGER | Primary key | User identifier |
| `username` | TEXT | NOT NULL | Display name |
| `email` | TEXT | NOT NULL, UNIQUE | Account email; registration normalizes it to lowercase |
| `password_hash` | TEXT | NOT NULL | Werkzeug password hash; plaintext passwords are not stored |
| `created_at` | TEXT | NOT NULL, default `CURRENT_TIMESTAMP` | Account creation time |

### `applications`

| Column | SQLite type | Nullability / constraint | Description |
|---|---|---|---|
| `id` | INTEGER | Primary key | Application identifier |
| `user_id` | INTEGER | NOT NULL, foreign key to `users.id` with `ON DELETE CASCADE` | Owner of the application |
| `company_name` | TEXT | NOT NULL | Company |
| `job_role` | TEXT | NOT NULL | Role or position |
| `job_location` | TEXT | Nullable | Location |
| `salary` | TEXT | Nullable | Salary as entered (not a normalized numeric value) |
| `application_status` | TEXT | NOT NULL, default `Applied`; CHECK constraint | One of `Applied`, `Interview`, `Selected`, or `Rejected` |
| `applied_date` | TEXT | NOT NULL | Application date, accepted as an ISO date |
| `job_description` | TEXT | Nullable | Notes or job description |
| `created_at` | TEXT | NOT NULL, default `CURRENT_TIMESTAMP` | Row creation time |

The application validates field lengths and required values in the form handlers. Database initialization does not migrate existing schemas or seed example rows.

## Flask routes and form interface

All application endpoints return rendered HTML, redirects, or plain-text not-found responses; they are not JSON endpoints. Protected routes redirect unauthenticated users to `/login`. Mutating POST forms require the `csrf_token` field.

| Method | Path | Access | Purpose and inputs |
|---|---|---|---|
| GET, POST | `/register` | Public | Render registration form; submit `username`, `email`, and `password`. |
| GET, POST | `/login` | Public | Render login form; submit `email` and `password`. |
| POST | `/logout` | CSRF token required | Clear the current session. |
| GET | `/dashboard` | Authenticated | Dashboard totals and recent applications. Optional query parameters: `search`, `status`. |
| GET | `/applications` | Authenticated | List applications. Optional query parameters: `search` (company or role), `location`, `status`, and `sort`. |
| GET | `/applications/analytics` | Authenticated | Analytics summary and charts. |
| GET, POST | `/applications/add` | Authenticated / POST requires CSRF | Render or submit an application. Fields: `company_name`, `job_role`, `job_location`, `salary`, `application_status`, `applied_date`, and `job_description`. |
| GET, POST | `/applications/<application_id>/edit` | Authenticated / POST requires CSRF | Render or update an application owned by the current user; accepts the same fields as add. |
| POST | `/applications/<application_id>/delete` | Authenticated / CSRF protected | Delete an application owned by the current user. |

Supported `status` values are `Applied`, `Interview`, `Selected`, and `Rejected`. Supported `sort` keys are `date_newest`, `date_oldest`, `company_az`, `company_za`, `salary_high`, and `salary_low`. Invalid status or sort query values fall back to the unfiltered status or newest-date sort.

Validation errors return the form with HTTP 400; duplicate registration returns HTTP 409; invalid login returns HTTP 401; attempts to access another user's application return HTTP 404. Successful form mutations redirect to the application list or login page.

## Installation and local execution

From the `jobtrack` project directory, create and activate a virtual environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The application requires a private Flask session key. Generate a fresh random key in the current PowerShell session; do not commit it:

```powershell
$env:JOBTRACK_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

Start the local development server:

```powershell
python app.py
```

Open `http://127.0.0.1:5000/register` to create an account. The application initializes the default database at startup. The Flask development server is for local development only.

If PowerShell activation is unavailable, run commands with `.\.venv\Scripts\python.exe` instead of `python`.

## Environment variables and configuration

| Variable | Required | Default / accepted values | Purpose |
|---|---|---|---|
| `JOBTRACK_SECRET_KEY` | Yes | No default; application startup fails if unset or empty | Flask session signing key. Generate a strong, random value and store it outside source control. |
| `JOBTRACK_COOKIE_SECURE` | No | Disabled unless set to `1`, `true`, or `yes` (case-insensitive) | Adds the `Secure` attribute to session cookies; enable when serving the site over HTTPS. |

Session cookies also use `HttpOnly` and `SameSite=Lax`. The database location is set in `config.py` to `instance/jobtrack.db`; it is not currently controlled by an environment variable. Tests override it with temporary database files.

This project does not load a `.env` file. Set environment variables in the process environment or deployment platform's secret/configuration settings. Never put real keys in this README, source code, or a committed environment file.

## Testing

Run the test suite from the project directory after setting `JOBTRACK_SECRET_KEY`:

```powershell
$env:JOBTRACK_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python -m pytest -q
```

Tests create temporary SQLite databases. Coverage in the current suite includes authentication and password hashing, input validation, CSRF checks, user-specific data access, application CRUD, search/filter/sort behavior, dashboard and analytics calculations, output escaping, and session-cookie settings.

**Verified result:** On November 6, 2026, `.\.venv\Scripts\python.exe -m pytest -q` completed with **34 passed, 13 subtests passed** in 8.04 seconds on the available Windows environment, with a temporary `JOBTRACK_SECRET_KEY` set for the run. Running pytest without that variable set fails during collection because importing the application requires its secret; this is expected behavior, not a test failure in the configured run.

## GitHub setup

To publish JobTrack as its own repository:

1. Create an empty repository on GitHub (do not initialize it with another README if you plan to push this README).
2. Work from the `jobtrack` directory and initialize a Git repository if needed:

   ```powershell
   git init -b main
   ```

3. Before staging, create a `.gitignore` in the repository root with rules for local-only files. For example:

   ```gitignore
   .venv/
   instance/*.db
   .env
   __pycache__/
   *.py[cod]
   .pytest_cache/
   ```

   Do not publish a real session key or local user data.
4. Stage the source, tests, requirements, and README—not virtual environments, caches, uploaded files, or the local database—then commit and add your repository URL:

   ```powershell
   git add .gitignore README.md app.py config.py requirements.txt database routes static templates tests
   git commit -m "Document JobTrack project"
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
   git push -u origin main
   ```

   Review `git status` and the staged file list before committing. If a local database or other private data was staged, unstage it and fix the ignore rules before pushing.

The current workspace also contains files outside the `jobtrack` folder. For a dedicated JobTrack repository, initialize Git from `jobtrack` and publish only this application's files.

**Suggested GitHub repository description:**  
`A Flask and SQLite job application tracker with secure accounts, searchable application management, dashboards, and analytics.`

## Deployment guidance

No hosting platform, production WSGI server, or deployment pipeline is configured or verified in this repository. The following is a starting point for a small deployment, not a claim that JobTrack is production-ready:

1. Provision a supported Python runtime and install `requirements.txt`.
2. Configure `JOBTRACK_SECRET_KEY` using the host's secret manager. Set `JOBTRACK_COOKIE_SECURE=true` when HTTPS is enabled.
3. Use a production WSGI server rather than `python app.py`. For example, on Windows, install Waitress in the deployment environment (`python -m pip install waitress`) and run from the project directory:

   ```powershell
   waitress-serve --host=127.0.0.1 --port=8000 app:app
   ```

   Place a trusted HTTPS reverse proxy in front of the WSGI server if the site is publicly accessible; configure the host firewall and proxy appropriately.
4. Persist and back up the `instance` directory, which contains the SQLite database. Ensure its filesystem permissions restrict access to the application process.
5. Run the tests and verify registration, login, CRUD, and analytics on the target environment before exposing the service.

SQLite is the only implemented database backend. For multi-instance deployments or higher write concurrency, plan and test a migration to a managed relational database before scaling out. Production hardening, operational monitoring, backup recovery, and deployment-specific configuration remain deployment responsibilities.

## Future improvements (planned, not implemented)

- Add schema migration tooling and an environment-configurable database connection.
- Add pagination and export/import for application records.
- Add password reset and email verification workflows, with a mail provider.
- Consider a JSON API if integrations or a separate frontend become requirements.
- Add accessibility checks and end-to-end browser tests.
- Evaluate rate limiting, operational logging/monitoring, and production deployment automation.
- Consider PostgreSQL for multi-instance or higher-concurrency deployments.

## Resume bullets

- Built **JobTrack**, a Flask and SQLite application for managing job applications, with account registration, password hashing, session authentication, and CSRF-protected form workflows.
- Implemented user-scoped application CRUD with validated inputs, search and combined filters, and six sorting options across date, company, and salary.
- Created dashboard and analytics views with status metrics, conversion rates, 12-month activity visualizations, and automated pytest coverage for core workflows and security controls.

## Two-minute interview explanation

> JobTrack is a full-stack web application I built to make a job search easier to organize. Users can register and log in, then create a record for each opportunity with the company, role, location, salary, application date, status, and notes. They can search and filter their applications, update a status as the process moves forward, and use the dashboard and analytics page to see how their pipeline is developing.
>
> The backend is a Flask application organized around an application factory, an authentication blueprint, and an applications blueprint. SQLite stores users and applications, with each application linked to its owner. I made the queries user-scoped and added form validation, Werkzeug password hashing, session-based authentication, and CSRF checks on state-changing forms. The interface uses Jinja-rendered pages, with JavaScript and Chart.js for analytics visualizations.
>
> I focused on end-to-end behavior and testability. The pytest suite exercises account workflows, authorization and data isolation, CRUD, filtering and sorting, analytics calculations, CSRF behavior, and output escaping. In the verified run documented here, all 34 tests and 13 subtests passed. The project is currently a server-rendered web app rather than a JSON API, and deployment hardening and database migrations are areas I would address before scaling it.

## Technical interview questions and answers

**1. How does JobTrack keep one user from seeing another user's applications?**  
The authenticated user ID is stored in the Flask session. Application queries include that ID in their `WHERE` clauses, including reads, updates, and deletes. The tests verify that another account cannot access or change an application by guessing its ID.

**2. How are passwords and sessions handled?**  
Passwords are stored as Werkzeug-generated password hashes and checked with Werkzeug's verification helper. After successful login, the app clears the prior session and stores the user ID and username. Flask signs the session cookie with `JOBTRACK_SECRET_KEY`; the cookie is HttpOnly and SameSite=Lax, and can be marked Secure with `JOBTRACK_COOKIE_SECURE`.

**3. What protections are in place for form submissions?**  
The app generates a random CSRF token in the session, includes it in forms, and compares submitted tokens using `hmac.compare_digest`. State-changing routes validate the token. Inputs are validated server-side and SQL values are passed as query parameters. Jinja autoescaping is used when rendering user-provided text.

**4. Why use SQLite, and what are its tradeoffs here?**  
SQLite keeps local setup simple and is sufficient for a small, single-instance tracker. It also supports the application's relational constraints without a separate database service. It has concurrency and operational limits for larger or multi-instance workloads, so a managed database such as PostgreSQL is a potential future step, not an implemented option.

**5. How are the analytics figures produced?**  
The analytics route computes status totals, monthly application counts for the current and preceding eleven months, the five most-used companies, and recent activity with SQL queries scoped to the current user. It calculates interview and selection percentages from the total application count and passes chart data to the template, where Chart.js renders the status and monthly charts.
