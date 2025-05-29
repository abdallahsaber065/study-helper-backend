# Study Helper Backend API

A robust FastAPI backend for the "Study Helper" application. This API manages users, subjects, files, and generates AI-powered summaries and multiple-choice questions.

## Features

- User authentication and management
- File uploads and management
- AI-powered summary generation
- AI file caching for efficient processing
- Extensive data models for academic content

## Tech Stack

- **Backend Framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy with Alembic for migrations
- **Authentication:** JWT (JSON Web Tokens)
- **AI Integration:** Google Gemini and OpenAI

## Prerequisites

- Python 3.8+
- PostgreSQL
- API keys for AI services (optional)

## Setup

1. Clone the repository:

    ```bash
    git clone <repository-url>
    cd study-helper-backend
    ```

2. Create a virtual environment and activate it:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

4. Create a `.env` file in the project root with the following variables:

    ```env
    # Database settings
    DB_HOST=localhost
    DB_PORT=5432
    DB_USER=your_db_user
    DB_PASSWORD=your_db_password
    DB_NAME=study_helper_db

    # JWT settings
    JWT_SECRET_KEY=your_secret_key
    JWT_ALGORITHM=HS256
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

    # AI settings (optional)
    GEMINI_API_KEY=your_gemini_api_key
    OPENAI_API_KEY=your_openai_api_key
    ```

5. Run database migrations:

```bash
alembic upgrade head
```

## Running the Application

Start the development server:

```bash
uvicorn main:app --reload
```

The API will be available at <http://127.0.0.1:8000>.

API documentation is available at:

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

## API Endpoints

### Authentication

- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and get JWT token
- `POST /auth/logout` - Logout and invalidate session
- `GET /auth/me` - Get current user info

### Users

- `GET /users/` - List users (admin or filtered for regular users)
- `GET /users/{user_id}` - Get user by ID
- `GET /users/username/{username}` - Get user by username

### Files

- `POST /files/upload` - Upload a file
- `GET /files/` - List user's files
- `GET /files/{file_id}` - Get file by ID
- `POST /files/{file_id}/share` - Share a file with another user
- `DELETE /files/{file_id}/share/{user_id}` - Revoke file access

### Summaries

- `POST /summaries/generate/from-file` - Generate summary from a file
- `POST /summaries/generate/from-text` - Generate summary from text
- `GET /summaries/` - List user's summaries
- `GET /summaries/{summary_id}` - Get summary by ID
- `PUT /summaries/{summary_id}` - Update a summary
- `DELETE /summaries/{summary_id}` - Delete a summary

## Development

The project follows a modular structure:

- `app.py` - FastAPI application instance
- `db_config.py` - Database configuration
- `models/` - SQLAlchemy models
- `schemas/` - Pydantic schemas
- `routers/` - API route handlers
- `services/` - Business logic
- `core/` - Utilities and common functions

## License

[MIT License](LICENSE)
