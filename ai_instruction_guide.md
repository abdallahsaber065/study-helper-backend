<!-- filepath: d:\Programming\Projects\collage\study-helper\v2\ai_instruction_guide.md -->
# AI Instruction Guide: Study Helper Backend API

## 1. Project Overview

**Goal:** Develop a robust FastAPI backend for the "Study Helper" application. This API will manage users, subjects, files, generate summaries and Multiple-Choice Questions (MCQs) using AI, and support community features. The backend will serve a future Next.js frontend.

**Core Functionality:**

* User authentication and management.
* File uploads and management.
* AI-powered summary generation from text/files.
* AI-powered MCQ generation from text/files.
* Quiz creation and session management.
* Community features for collaboration.
* Content rating, commenting, and versioning.

**Key Technologies:**

* **Backend Framework:** FastAPI
* **Database:** PostgreSQL
* **ORM:** SQLAlchemy (with Alembic for migrations)
* **Authentication:** JWT (JSON Web Tokens)
* **Data Validation:** Pydantic
* **AI Integration:** Placeholder for services like OpenAI or Google Gemini (via their Python SDKs)
* **Asynchronous Operations:** `async/await` for I/O bound tasks.

## 2. General Development Guidelines for AI

* **Follow FastAPI Best Practices:** Adhere to the official FastAPI documentation and recommended patterns.
* **Pydantic for Schemas:** Use Pydantic models for request/response validation, serialization, and settings management unless the return type is dynamic.
* **SQLAlchemy for ORM:** Implement database interactions using SQLAlchemy Core and ORM. Define models based on the existing `models.py`.
* **Asynchronous Code:** Utilize `async def` for path operations and database calls to ensure non-blocking I/O.
* **Modularity:** Organize code into logical modules (e.g., `routers`, `services`, `models`, `schemas`, `core`).
* **Error Handling:** Implement comprehensive and consistent error handling. Use FastAPI's exception handling mechanisms.
* **Security:** Prioritize security:
  * Input validation for all incoming data.
  * Secure password hashing (e.g., bcrypt).
  * Protection against common web vulnerabilities (OWASP Top 10).
  * Properly configure CORS.
  * Rate limiting where appropriate.
* **Testing:** Write unit and integration tests for all endpoints and critical business logic. (Testing phase will be detailed later).
* **Documentation:**
  * Leverage FastAPI's automatic OpenAPI and ReDoc generation.
  * Write clear docstrings for functions, classes, and modules.
  * Add comments for complex logic.
* **Dependency Management:** Use `requirements.txt`
* **Database Migrations:** Use Alembic for managing database schema changes.
* **Configuration:** Manage settings using Pydantic's `BaseSettings` or environment variables (as seen in `db_config.py`).
* **Logging:** Implement structured logging for debugging and monitoring.

## 3. Development Phases

This project will be developed in phases. Each phase builds upon the previous one.

### Phase 1: Project Setup, Core Models, and Initial Database Configuration

**Objective:** Establish the project structure, configure the database, and implement foundational SQLAlchemy models.

**Tasks:**

1. **Initialize FastAPI Project:**
    * Set up a virtual environment.
    * Install FastAPI, Uvicorn, SQLAlchemy, psycopg2-binary, Alembic, Pydantic, python-dotenv.
    * Create a basic project structure:

        ```plaintext
        study_helper_backend/
        ├── app/
        │   ├── __init__.py
        │   ├── main.py             # FastAPI app instance
        │   ├── db_config.py        # (Already provided)
        │   ├── models/
        │   │   ├── __init__.py
        │   │   └── models.py       # (Partially provided, needs completion)
        │   ├── schemas/            # Pydantic schemas
        │   │   └── __init__.py
        │   ├── routers/            # API routers
        │   │   └── __init__.py
        │   ├── services/           # Business logic
        │   │   └── __init__.py
        │   └── core/               # Core utilities (e.g., config, security)
        │       └── __init__.py
        ├── alembic/                 # Alembic migration scripts
        ├── alembic.ini              # (Alembic config)
        ├── requirements.txt
        └── .env                     # Environment variables (DATABASE_URL, etc.)
        ```

2. **Database Configuration (`db_config.py`):**
    * Review and ensure `db_config.py` is correctly set up to connect to PostgreSQL using environment variables.
3. **SQLAlchemy Models (`models/models.py`):**
    * Complete the SQLAlchemy model definitions based on `db_schema.rs`.
    * **Focus on these initial models for Phase 1:**
        * `User` (core fields, relationships will be expanded)
        * `UserSession`
        * `Subject`
        * `PhysicalFile`
        * `AiApiKey`
        * Define all ENUM types as Python enums and use `sqlalchemy.Enum`.
    * Ensure `Base` from `db_config.py` is used.
    * Define basic relationships (`relationship`) where straightforward (e.g., `User.sessions`). More complex ones can be refined later.
4. **Alembic Setup & Initial Migration:**
    * Initialize Alembic: `alembic init alembic`
    * Configure `alembic.ini` to point to your database URL.
    * Modify `env.py` in the alembic folder:
        * Import your `Base` metadata (`from app.db_config import Base`).
        * Set `target_metadata = Base.metadata`.
    * Generate an initial migration script: `alembic revision -m "Initial database schema"`
    * Edit the generated script to include `CREATE TYPE` statements for all PostgreSQL ENUMs defined in `db_schema.rs` *before* any tables using them are created.
    * Populate the migration script with `op.create_table()` calls for the initial models.
    * Apply the migration: `alembic upgrade head`.
5. **Basic Pydantic Schemas:**
    * Create basic Pydantic schemas in `app/schemas/` for the initial models (e.g., `UserCreate`, `UserRead`, `SubjectCreate`, `SubjectRead`).
6. **Health Check Endpoint:**
    * Create a simple `/health` endpoint in `app/main.py` that returns `{"status": "ok"}`.

### Phase 2: User Authentication & Authorization

**Objective:** Implement secure user registration, login, and basic session management.

**Tasks:**

1. **Password Hashing:**
    * Integrate a password hashing library (e.g., `passlib` with `bcrypt`).
    * Create utility functions for hashing and verifying passwords in `app/core/security.py`.
2. **User Registration:**
    * Create `UserCreate` schema in `app/schemas/user.py` (include password).
    * Create `UserRead` schema (exclude password_hash).
    * Develop an API endpoint (`/users/register` or `/auth/register`) in `app/routers/auth.py` to register new users.
        * Hash the password before saving to the database.
        * Ensure username and email are unique.
3. **User Login (JWT):**
    * Install `python-jose[cryptography]`.
    * Configure JWT settings (secret key, algorithm, expiration time) in `app/core/config.py`.
    * Implement JWT generation and decoding functions in `app/core/security.py`.
    * Create a login endpoint (`/auth/token`) that accepts username/email and password.
        * Verify credentials.
        * Return an access token upon successful authentication.
    * Store session information in the `UserSession` table.
4. **Authenticated Endpoints & Dependency:**
    * Create a dependency (e.g., `get_current_user`) in `app/core/security.py` to verify JWTs and retrieve the current user.
    * Protect relevant endpoints using this dependency.
    * Example: `/users/me` endpoint to get current user's details.
5. **User Model Updates:**
    * Ensure `User` model fields like `is_active`, `is_verified`, `role`, `last_login` are handled.
    * Implement logic for `updated_at` (SQLAlchemy events or database triggers as per `db_schema.rs`). The schema suggests a DB trigger `trigger_set_timestamp()`. Ensure this trigger is created in an Alembic migration if not already.
6. **Basic Role Stub:**
    * The `User.role` field (using `UserRoleEnum`) is present. For now, ensure it's set (e.g., default to 'user'). Actual role-based access control (RBAC) logic will be more detailed later.

### Phase 3: File Handling & Core AI Integration (Summaries)

**Objective:** Implement file uploading, storage, and the first AI feature: summary generation.

**Tasks:**

1. **File Upload Endpoint:**
    * Create Pydantic schemas for file metadata.
    * Develop an API endpoint (e.g., `/files/upload`) in `app/routers/files.py` to handle file uploads (`UploadFile` from FastAPI).
    * Store file metadata in the `PhysicalFile` table (file_hash, file_name, file_path, file_type, file_size_bytes, mime_type, user_id).
    * Store the actual file on the server (e.g., in a configured `mediafiles/` directory, ensure this is in `.gitignore` if not already) or a cloud storage solution (e.g., S3 - for future consideration). For now, local storage is fine.
    * Generate a unique `file_path` for storage.
    * Calculate `file_hash` (e.g., SHA256) to identify unique files.
2. **User File Access (`UserFileAccess`):**
    * Implement logic and endpoints to manage user access to files (e.g., linking a `PhysicalFile` to a `User` with an access level). This table is important for shared/community files later.
3. **Summary Model & Schemas:**
    * Ensure `Summary` model is complete in `models.py`.
    * Create Pydantic schemas for summary creation and retrieval (`SummaryCreate`, `SummaryRead`) in `app/schemas/summary.py`.
4. **AI Service Integration (Placeholder/Mock):**
    * Create a service module `app/services/ai_service.py`.
    * Define a function `generate_summary_from_text(text: str) -> str`.
    * Initially, this can be a mock implementation (e.g., returns the first N words of the text or a fixed string).
    * Later, this will integrate with an actual AI SDK (e.g., Gemini).
5. **Summary Generation Endpoint:**
    * Create an endpoint (e.g., `/summaries/generate/from-file/{file_id}`) in `app/routers/summaries.py`.
    * This endpoint should:
        * Retrieve the file content (requires reading the physical file).
        * Call the `ai_service.generate_summary_from_text()`.
        * Save the generated summary to the `Summary` table, linking it to the user and optionally the `PhysicalFile`.
        * Return the generated summary.
6. **Gemini File Cache (`GeminiFileCache`):**
    * Implement the `GeminiFileCache` model.
    * Before calling the AI service for a file, check if a cached response exists for that `physical_file_id` and `processing_type` (e.g., 'summary').
    * If cached, return the cached response. Otherwise, call the AI service and store the result in the cache.
7. **API Key Management (`AiApiKey`):**
    * Endpoints for users to add/manage their AI provider API keys (e.g., OpenAI, Google).
    * Store keys securely (encrypted in the `AiApiKey` table's `encrypted_api_key` field). Use a library like `cryptography.fernet`.
    * The AI service should use the user's key if available.

### Phase 4: MCQ and Quiz Functionality

**Objective:** Implement models and APIs for creating, managing, and taking quizzes with MCQs, including AI generation for questions.

**Tasks:**

1. **MCQ & Quiz Models:**
    * Complete/Verify SQLAlchemy models:
        * `McqQuestion`
        * `QuestionTag`
        * `McqQuestionTagLink` (association table)
        * `McqQuiz`
        * `McqQuizQuestionLink` (association table)
        * `QuizSession`
    * Ensure all relationships and constraints (like `correct_option` check) are defined.
2. **Pydantic Schemas:**
    * Create schemas for all MCQ and Quiz related models (Create, Read, Update).
3. **CRUD for `QuestionTag`:**
    * Endpoints for creating, listing, updating, deleting tags.
4. **CRUD for `McqQuestion`:**
    * Endpoints for creating, retrieving, updating, deleting MCQs.
    * Handle linking questions to tags via `McqQuestionTagLink`.
    * AI Integration: Endpoint to generate MCQs from text/file content (similar to summary generation, using `ai_service.py` and `GeminiFileCache` with a different `processing_type` like 'mcq_generation').
5. **CRUD for `McqQuiz`:**
    * Endpoints for creating, retrieving, updating, deleting quizzes.
    * Allow associating `McqQuestion`s with an `McqQuiz` via `McqQuizQuestionLink`, including `display_order`.
    * Handle `is_public` and linking to `subject_id` and `community_id` (optional for now).
6. **Quiz Session Management (`QuizSession`):**
    * Endpoint to start a quiz session for a user and a quiz (`/quiz-sessions/start`).
        * Initialize `session_start`, `current_answers` (empty JSONB).
    * Endpoint to submit answers during a quiz session (`/quiz-sessions/{session_id}/answer`).
        * Update `current_answers` JSONB.
    * Endpoint to end/submit a quiz session (`/quiz-sessions/{session_id}/submit`).
        * Calculate `score`, `time_taken_seconds`.
        * Set `session_end`, `is_completed`.
    * Endpoint to retrieve quiz session results.

### Phase 5: Community Features

**Objective:** Implement features for users to form communities, share resources, and collaborate.

**Tasks:**

1. **Community Models:**
    * Complete/Verify SQLAlchemy models:
        * `Community`
        * `CommunityMember` (association object with role)
        * `CommunitySubjectLink` (linking subjects to communities)
        * `CommunitySubjectFile` (linking files to subjects within a community)
2. **Pydantic Schemas:**
    * Create schemas for all Community related models.
3. **CRUD for `Community`:**
    * Endpoints for creating, listing, retrieving (details), updating, deleting communities.
    * Handle `creator_id`, `is_private`.
4. **Community Membership (`CommunityMember`):**
    * Endpoints for users to join/leave communities.
    * Endpoints for community admins/moderators to manage members (add, remove, change role - `CommunityRoleEnum`).
5. **Linking Subjects to Communities (`CommunitySubjectLink`):**
    * Endpoints for community admins/moderators to add/remove subjects from a community.
6. **Linking Files to Community Subjects (`CommunitySubjectFile`):**
    * Endpoints for community members (with appropriate permissions) to add/remove files to/from a subject within a community.
    * Handle `file_category` (`CommunityFileCategoryEnum`).

### Phase 6: Interaction and Engagement Features

**Objective:** Add features for user interaction like comments, ratings, notifications, and preferences.

**Tasks:**

1. **Interaction Models:**
    * Complete/Verify SQLAlchemy models:
        * `ContentComment` (polymorphic: for files, summaries, quizzes)
        * `ContentRating` (polymorphic: for files, summaries, quizzes)
        * `Notification`
        * `UserPreference`
2. **Pydantic Schemas:**
    * Create schemas for these models.
3. **Content Comments (`ContentComment`):**
    * Endpoints to add comments to content (e.g., `/summaries/{summary_id}/comments`).
    * Support for `parent_comment_id` for threaded comments.
    * Endpoints to list comments for a piece of content.
    * Handle `content_type` and `content_id` for polymorphism.
4. **Content Ratings (`ContentRating`):**
    * Endpoints for users to rate content (1-5 stars using `RatingValueEnum`).
    * Handle `content_type` and `content_id`.
    * Endpoint to get average rating for a piece of content.
5. **Notifications (`Notification`):**
    * Service to create notifications (e.g., `app/services/notification_service.py`).
    * Trigger notifications for events like:
        * New content in a community.
        * Reply to a user's comment.
        * Quiz result available.
        * Community invite.
        * User mention.
    * Endpoints for users to list their notifications (unread/all).
    * Endpoint to mark notifications as read.
6. **User Preferences (`UserPreference`):**
    * Endpoints for users to get/update their preferences (e.g., `email_notifications_enabled`, `default_theme`).
    * Store dynamic preferences in `preferences_json` if needed.

### Phase 7: Advanced Features and Refinements

**Objective:** Implement advanced functionalities, improve robustness, and prepare for production.

**Tasks:**

1. **Content Versioning (`ContentVersion`):**
    * Implement logic to store previous versions of content (e.g., summaries) when they are updated.
    * Handle `content_type`, `content_id`, `version_number`, `version_data` (JSONB snapshot).
    * Endpoints to list versions and retrieve a specific version.
2. **Content Analytics (`ContentAnalytics`):**
    * Implement logic to track views, likes (could be derived from ratings or a separate like system), shares, comment counts.
    * Update these counts based on user actions (e.g., via background tasks or direct updates).
    * Endpoints to retrieve analytics for content.
3. **Refine AI Integration:**
    * Replace mock AI services with actual SDK calls to Gemini/OpenAI.
    * Use API keys from `AiApiKey` table.
    * Implement proper error handling for AI service calls.
    * Consider asynchronous AI calls using background tasks (e.g., FastAPI's `BackgroundTasks` or Celery) for long-running AI processes to avoid blocking API responses.
4. **Enhanced Error Handling & Validation:**
    * Review all endpoints for comprehensive input validation (Pydantic).
    * Implement custom exception handlers for common errors.
    * Ensure consistent error response formats.
5. **Background Tasks:**
    * Identify long-running operations (e.g., complex AI processing, sending email notifications) and move them to background tasks.
6. **Logging and Monitoring:**
    * Set up structured logging throughout the application.
    * Integrate with a monitoring service if applicable (e.g., Sentry, Prometheus/Grafana - for future).
7. **Security Hardening:**
    * Review all security aspects: authentication, authorization, input validation, output encoding.
    * Implement rate limiting (e.g., using `slowapi`).
    * Ensure proper CORS configuration (`CORSMiddleware`).
    * Regularly update dependencies.
8. **Database Optimizations:**
    * Review database queries for performance.
    * Add indexes where necessary (some are already suggested in `db_schema.rs`, ensure they are in Alembic migrations).
    * Example indexes from schema: `content_comment (content_type, content_id)`, `notification (user_id, is_read, created_at)`, `content_rating (content_type, content_id)`.

### Phase 8: Testing, Documentation, and Deployment Preparation

**Objective:** Ensure the API is well-tested, documented, and ready for deployment.

**Tasks:**

1. **Unit Tests:**
    * Write unit tests for services, utility functions, and complex logic.
    * Use a testing framework like `pytest`.
    * Mock external services (database, AI APIs) where appropriate.
2. **Integration Tests:**
    * Write integration tests for API endpoints.
    * Use FastAPI's `TestClient`.
    * Test against a real (test) database.
3. **API Documentation Review:**
    * Ensure FastAPI's auto-generated OpenAPI docs (`/docs`, `/redoc`) are accurate and comprehensive.
    * Add descriptions and examples to Pydantic models and path operations where needed.
4. **Database Migrations Finalization:**
    * Ensure all schema changes are captured in Alembic migrations and the database is up-to-date.
5. **Configuration for Environments:**
    * Ensure configuration can be easily managed for different environments (development, staging, production) using environment variables and Pydantic settings.
6. **Containerization (Docker):**
    * Create a `Dockerfile` to containerize the FastAPI application.
    * Create `docker-compose.yml` for local development (app + PostgreSQL database).
7. **Deployment Strategy (Outline):**
    * Outline steps for deploying to a cloud platform (e.g., AWS, Google Cloud, Heroku, DigitalOcean). This is for planning; actual deployment is a separate major task.

## 4. Next Steps (Post-Backend Development)

* Develop the Next.js frontend to consume this API.
* Set up CI/CD pipelines for automated testing and deployment.
* Implement more sophisticated AI features and model fine-tuning if required.

This phased approach should allow for systematic development and testing. Remember to commit changes frequently and use branches for different features/phases.
