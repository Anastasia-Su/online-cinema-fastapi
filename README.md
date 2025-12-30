# Movie Store Backend API

A fully asynchronous backend API for an online movie store built with **FastAPI**, **SQLAlchemy (async)**, **PostgreSQL**, **Redis**, **Celery**, and **Docker**. The project supports movie browsing, ratings, likes, favorites, carts, orders, payments, authentication, and role-based access control.

## Installing / Getting started
* Run: 
```bash
git clone https://github.com/Anastasia-Su/online-cinema-fastapi.git
cd online-cinema-fastapi
python -m venv venv
venv\Scripts\activate (on Windows)
source venv/bin/activate (on macOS)
pip install poetry
poetry install
```
alembic upgrade head

* Create .env file and set it according to .env.sample.
* Upgrade alembic and populate db:
```bash
alembic upgrade head
python -m src.database.populate_db_run
```

## Features

* **Authentication & Authorization**

  * JWT-based authentication
  * Role-based access (User / Moderator / Admin)
  * Token revocation via Redis (logout)

* **Movies**

  * Browse catalog with pagination, filtering, and sorting
  * Movie details with genres, stars, directors
  * Likes / dislikes
  * Favorites

* **Ratings**

  * Rate movies (create/update/delete)
  * Automatic rating count & average calculation

* **Comments**

  * Nested comments with replies
  * Like tracking

* **Cart & Orders**

  * Shopping cart per user
  * Prevent duplicate purchases
  * Order creation and cancellation

* **Payments**

  * Payment records with status tracking
  * Paid items automatically removed from cart

* **Infrastructure**

  * Async PostgreSQL via SQLAlchemy
  * Redis for token revocation
  * S3-compatible storage (via aioboto3)
  * Docker & Docker Compose


## 🧵 Celery & Background Tasks

Celery is used for:

- Sending emails (activation, payment, comments)
- Comment notifications
- Payment notifications
- Cleanup & async background jobs

### Celery Configuration

- **Broker:** Redis
- **Result backend:** Redis
- **Worker module:** `src.tasks.celery_app`

Commands:

```bash
celery -A src.tasks.celery_app worker -Q default,comment_notifications,maintenance --pool=solo -l info
```
```bash
celery -A src.tasks.celery_app beat -l info
```

## Running with Docker

```bash
docker-compose up --build
```

Services started:

* FastAPI app
* PostgreSQL
* Redis
* MinIO (S3-compatible storage)
* Mailhog
* Celery

API will be available at:

```
http://localhost:8000
```

### docker/
Contains Dockerfiles for various services used in the project, facilitating containerization and orchestration.

### Docker Compose Files
Manage multi-container Docker applications, defining services, networks, and volumes.

`docker-compose-dev.yml`: Configuration for the development environment, including services, volumes, and ports tailored for development workflows.
`docker-compose-prod.yml`: Configuration for the production environment, optimized for performance, security, and scalability.
`docker-compose-tests.yml`: Configuration for running tests within Docker containers, ensuring isolation and consistency during testing.

## API Documentation

Once the app is running:

* **Swagger UI**: `http://localhost:8000/docs`
* **ReDoc**: `http://localhost:8000/redoc`


## Testing

Run tests locally:
```bash
pytest
```

Integration tests live in:
```
tests/test_integration/
```

e2e tests live in:
```
tests/test_e2e/
```

## Role-Based Access

* **User**: browse, rate, comment, purchase
* **Moderator**: view users, perform CRUD on movies
* **Admin**: full access


## Links
* DockerHub: 


