# Study Assistant Backend

AI-powered Quiz & Summary Generation Platform Backend built with FastAPI, PostgreSQL, and modern Python practices.

## Features

- 🔐 **JWT Authentication** - Secure user authentication and authorization
- 📁 **File Management** - Upload and manage PDF/text documents
- 🤖 **AI Integration** - Generate summaries and quizzes using AI models
- ⚡ **Async Processing** - Celery task queue for background processing
- 📊 **Real-time Updates** - WebSocket support for live progress tracking
- 🔒 **Security First** - OWASP compliance and security best practices
- 📈 **Monitoring** - Prometheus metrics and structured logging
- 🧪 **Testing** - Comprehensive test suite with >90% coverage

## Tech Stack

- **Framework**: FastAPI 0.110+
- **Language**: Python 3.12+
- **Database**: PostgreSQL 15+ with SQLAlchemy 2.0
- **Cache/Queue**: Redis 7+ with Celery 5.3+
- **Authentication**: JWT with PassLib
- **Validation**: Pydantic v2
- **Migrations**: Alembic

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis 7+
- Poetry (recommended) or pip

### Installation

1. **Clone and navigate to the backend directory**

   ```bash
   cd backend
   ```

2. **Install dependencies**

   ```bash
   # Using Poetry (recommended)
   poetry install

   # Or using pip
   pip install -r requirements.txt
   ```

3. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Set up the database**

   ```bash
   # Run migrations
   poetry run alembic upgrade head
   ```

5. **Start the development server**

   ```bash
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

The API will be available at `http://localhost:8000`

- **Documentation**: <http://localhost:8000/docs>
- **Health Check**: <http://localhost:8000/health>

## Environment Configuration

Copy `.env.example` to `.env` and configure the following key variables:

```env
# Security
SECRET_KEY="your-super-secret-key-here-at-least-32-chars"

# Database
DATABASE_URL="postgresql://username:password@localhost:5432/study_assistant"

# Redis
REDIS_URL="redis://localhost:6379"

# AI Services
OPENAI_API_KEY="sk-your-openai-api-key"
ANTHROPIC_API_KEY="sk-ant-your-anthropic-api-key"
```

## Development

### Code Quality

```bash
# Format code
poetry run black .
poetry run isort .

# Lint code
poetry run ruff check .

# Type checking
poetry run mypy .

# Security scanning
poetry run bandit -r app/
```

### Testing

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=app --cov-report=html

# Run specific test
poetry run pytest tests/test_auth.py::test_login
```

### Database Management

```bash
# Create new migration
poetry run alembic revision --autogenerate -m "description"

# Apply migrations
poetry run alembic upgrade head

# Rollback migration
poetry run alembic downgrade -1
```

## Project Structure

```bash
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration management
│   ├── database.py          # Database configuration
│   ├── auth/                # Authentication module
│   ├── users/               # User management
│   ├── tasks/               # Background tasks
│   └── schemas/             # Pydantic models
├── alembic/                 # Database migrations
├── docs/                    # Documentation
├── tests/                   # Test suite
├── pyproject.toml           # Poetry dependencies
├── alembic.ini              # Migration configuration
└── .env.example             # Environment template
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

## Contributing

1. Follow the existing code style and patterns
2. Add tests for new features
3. Update documentation as needed
4. Ensure all tests pass and linting is clean

## License

This project is licensed under the MIT License.
