# AI Resume Screening & Candidate Matching System

A modular Flask project scaffold for an AI-assisted resume screening and candidate matching system. The project targets Python 3.9.12.

## Project structure

- `app.py` — reserved entry point for the Flask application.
- `config.py` — reserved for application configuration.
- `requirements.txt` — declares Flask as the web framework dependency.
- `resume_screening/` — Python package for the application.
  - `routes/` — reserved for HTTP routes and blueprints.
  - `services/` — reserved for application and domain services.
  - `models/` — reserved for domain and data models.
  - `utils/` — reserved for shared utilities.
  - `templates/` — Flask/Jinja templates.
  - `static/` — CSS, JavaScript, and image assets.
- `uploads/` — local storage location for uploaded files; uploaded content is excluded from version control.
- `tests/` — automated tests.

## Setup

Create and activate a virtual environment using Python 3.9.12, then install the declared dependencies with:

```text
python -m pip install -r requirements.txt
```

No application behavior has been implemented yet.
