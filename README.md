# Study Helper Backend API

A FastAPI-based backend application for the Study Helper project, featuring AI-powered content generation, community collaboration, and comprehensive quiz management.

## 🚀 Features

### File Handling & AI Integration

- ✅ File upload and management (DOCS, AUDIO, IMAGE)
- ✅ AI-powered summary generation from multiple files
- ✅ File access control and sharing between users
- ✅ AI file caching for efficiency (Gemini File API integration)
- ✅ Support for both file-based and text-based content processing

### MCQ and Quiz Functionality

- ✅ AI-powered Multiple Choice Question (MCQ) generation from files
- ✅ Question tagging and categorization system
- ✅ Quiz creation and management
- ✅ Interactive quiz sessions with scoring
- ✅ Comprehensive quiz history and analytics
- ✅ Manual MCQ creation and editing
- ✅ Difficulty level management (Easy, Medium, Hard)

### Community Features (Under Development)

- ✅ Community creation with unique shareable codes
- ✅ Role-based access control (Admin, Moderator, Member)
- ✅ Subject management and linking to communities
- ✅ File association with community subjects
- ✅ Community membership management (join/leave/invite)
- ✅ Permission-based content curation
- ✅ Private and public community support
- ✅ Community statistics and analytics
- ✅ User limits and validation (configurable limits)

### Core Features

- 🔐 JWT-based authentication and authorization
- 👤 User registration and profile management
- 🔧 Configurable settings and environment management
- 📊 Comprehensive API documentation (OpenAPI/Swagger)
- 🧪 Extensive test coverage for all phases

## 🏗️ Architecture

```plaintext
study_helper_backend/
├── core/                   # Core utilities and configuration
│   ├── config.py          # Application settings
│   ├── security.py        # Authentication and security
│   └── file_utils.py      # File handling utilities
├── models/                 # SQLAlchemy database models
│   └── models.py          # All database models and relationships
├── schemas/                # Pydantic schemas for validation
│   ├── auth.py            # Authentication schemas
│   ├── user.py            # User-related schemas
│   ├── file.py            # File management schemas
│   ├── summary.py         # Summary generation schemas
│   ├── mcq.py             # MCQ and quiz schemas
│   ├── community.py       # Community feature schemas
│   └── subject.py         # Subject management schemas
├── routers/                # FastAPI route handlers
│   ├── auth.py            # Authentication endpoints
│   ├── users.py           # User management endpoints
│   ├── files.py           # File upload and management
│   ├── summaries.py       # AI summary generation
│   ├── mcqs.py            # MCQ and quiz management
│   └── communities.py     # Community features
├── services/               # Business logic layer
│   ├── ai_manager.py      # AI integration (Gemini/OpenAI)
│   ├── summary_service.py # Summary generation logic
│   ├── mcq_service.py     # MCQ generation logic
│   └── community_service.py # Community management logic
├── tests/                  # Comprehensive test suite
│   ├── test_phase3.py     # File and AI integration tests
│   ├── test_phase4.py     # MCQ and quiz functionality tests
│   └── test_phase5.py     # Community features tests
├── cache/                  # File storage and caching
│   ├── file_uploads/      # User uploaded files
│   └── test_files/        # Test file storage
├── prompts/                # AI prompt templates
│   ├── mcq/               # MCQ generation prompts
│   └── summary/           # Summary generation prompts
└── migrations/             # Database migration files
    └── versions/          # Alembic migration versions
```

## 🛠️ Setup and Installation

### Prerequisites

- Python 3.8+
- PostgreSQL
- Google Gemini API key (for AI features)

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd study-helper-backend
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Configuration**
   Create a `.env` file with:

   ```env
   # Database
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_NAME=study_helper
   
   # Security
   JWT_SECRET_KEY=your-secret-key-change-this
   
   # AI Integration
   GEMINI_API_KEY=your-gemini-api-key
   ```

4. **Database Setup**

   ```bash
   # Initialize database
   alembic upgrade head
   ```

5. **Run the application**

   ```bash
   python -m uvicorn main:app --reload
   ```

## 🧪 Testing

Run comprehensive tests for all phases:

```bash
# Test Phase 3: File handling and AI integration
python tests/test_phase3.py

# Test Phase 4: MCQ and quiz functionality
python tests/test_phase4.py

# Test Phase 5: Community features
python tests/test_phase5.py
```

## 📚 API Documentation

Once the application is running, access the interactive API documentation:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

## 🔧 Configuration

### Community Settings

- `MAX_COMMUNITIES_PER_USER`: Maximum communities a user can create (default: 3)
- `MAX_COMMUNITY_MEMBERSHIPS_PER_USER`: Maximum communities a user can join (default: 10)
- `COMMUNITY_CODE_LENGTH`: Length of community invitation codes (default: 8)

### File Upload Settings

- `MAX_FILE_SIZE_MB`: Maximum file size in MB (default: 50)
- `ALLOWED_FILE_TYPES`: Supported file extensions (default: .pdf, .txt, .docx, .doc)

### AI Integration Settings

- `FREE_TIER_GEMINI_LIMIT`: Free tier API call limit for Gemini (default: 10)
- `FREE_TIER_OPENAI_LIMIT`: Free tier API call limit for OpenAI (default: 5)

## 🚦 API Endpoints

### Authentication

- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `GET /users/me` - Get current user profile

### File Management

- `POST /files/upload` - Upload files
- `GET /files` - List user files
- `POST /files/{file_id}/share` - Share files with other users

### AI Features

- `POST /summaries/generate` - Generate AI summaries from files/text
- `POST /mcqs/generate` - Generate MCQs from files using AI

### Quiz Management

- `GET /mcqs/questions` - List MCQ questions
- `POST /mcqs/questions` - Create manual MCQ questions
- `GET /mcqs/quizzes` - List quizzes
- `POST /mcqs/quizzes` - Create quizzes
- `POST /mcqs/quizzes/{quiz_id}/sessions` - Start quiz sessions

### Community Features

- `POST /communities` - Create communities
- `GET /communities` - List communities
- `POST /communities/join` - Join community with code
- `GET /communities/{id}/members` - Get community members
- `POST /communities/{id}/subjects` - Add subjects to community
- `POST /communities/{id}/files` - Associate files with community subjects

## Future Enhancements

- Content interaction features (comments, ratings, notifications)
- Advanced analytics and content versioning
- Comprehensive testing and deployment preparation

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
