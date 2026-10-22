# Gideon Backend Service

FastAPI backend service powering Gideon, a personal AI assistant.

## Features
- **FastAPI** with modular architecture (Routes, Services, Repositories).
- **SQLAlchemy 2.x** models and **Alembic** migrations.
- **SQLite** default local development fallback and **PostgreSQL** support.
- **Pluggable AI Provider**: Runs with local offline `DemoAIProvider` out-of-the-box.
- **Pytest** automated testing suite with isolated test database.

## Quickstart (Windows PowerShell)

```powershell
# Create virtual environment
python -m venv .venv

# Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run migrations
.\.venv\Scripts\alembic.exe upgrade head

# Run server
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

## Running Tests

```powershell
.\.venv\Scripts\pytest.exe -v
```

## API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health
