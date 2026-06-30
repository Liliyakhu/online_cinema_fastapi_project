# Online Cinema — FastAPI Project

A full-featured online cinema backend built with **FastAPI**, **SQLAlchemy (async)**, **PostgreSQL/SQLite**, **Celery**, **Stripe**, and **MinIO (S3)**.

## Features

- **Accounts** — JWT auth, registration/activation, password reset, role-based access (User / Moderator / Admin), Celery beat cleanup of expired tokens
- **Movies** — catalog with search, filters, sorting, favorites, likes, ratings, comments
- **Cart & Orders** — shopping cart, checkout, order history
- **Payments** — real Stripe Checkout integration with webhooks
- **Profiles** — user profiles with avatar upload to MinIO/S3
- **108 automated tests** (pytest), **CI/CD** via GitHub Actions

## Tech Stack

Python 3.10 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · PostgreSQL / SQLite · Celery + Redis · Stripe · MinIO · Docker & Docker Compose · Nginx · Poetry

---

## Running Locally (without Docker)

Uses SQLite — good for quick development.

```bash
# Install dependencies
poetry install

# Start MailHog + Redis (lightweight services)
docker compose up -d

# Run the app
PYTHONPATH=src uvicorn main:app --app-dir src --reload
```

App available at: `http://localhost:8000/docs`

Run tests:
```bash
poetry run pytest
```

---

## Running with Docker (full stack, PostgreSQL)

1. Copy and fill in environment variables:
   ```bash
   cp .env.sample .env
   ```
   Required values: `POSTGRES_*`, `SECRET_KEY_ACCESS`/`SECRET_KEY_REFRESH`, `MINIO_*`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `API_USER`/`API_PASSWORD` (Nginx Basic Auth).

2. Start the development stack (hot-reload, PostgreSQL, MinIO, Celery, MailHog):
   ```bash
   docker compose -f docker-compose-dev.yml up --build
   ```

3. Available services:
   - API & Swagger docs: `http://localhost:8000/docs`
   - pgAdmin: `http://localhost:3333`
   - MailHog: `http://localhost:8025`
   - MinIO console: `http://localhost:9001`

4. For local Stripe webhook testing, run in a separate terminal:
   ```bash
   stripe listen --forward-to localhost:8000/api/v1/payments/webhook/
   ```
   Copy the generated `whsec_...` into `.env` as `STRIPE_WEBHOOK_SECRET` and restart the `web` service.

### Production stack

```bash
docker compose -f docker-compose-prod.yml up --build -d
```

Uses Gunicorn + Nginx (with Basic Auth protecting `/docs`, `/redoc`, `/openapi.json`).

---

## Database Migrations

Migrations run automatically via the `migrator` service in Docker. To run manually:

```bash
docker compose -f docker-compose-prod.yml exec migrator alembic upgrade head
```

---

## CI/CD

- **CI** (`.github/workflows/main.yml`) — runs `flake8` and the full test suite on every pull request to `main`.
- **CD** (`.github/workflows/cd-pipeline.yml`) — deploys automatically to AWS EC2 on push/merge to `main`, via SSH + `commands/deploy.sh`.

Required GitHub secrets: `EC2_SSH_KEY`, `EC2_HOST`, `EC2_USER`.

---

## Live Demo

- **Swagger UI:** http://3.66.54.53/docs
Basic Auth required — 
- API_USER=admin_cinema, 
- API_PASSWORD=Jkjlis657klk2ksdmnJHPoi


## Default Test Accounts

| Email | Password | Role |
|---|---|---|
| admin@admin.com | Admin123& | Admin |
| user@user.com | User123$ | User |

