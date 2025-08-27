# Study Helper Backend API

A FastAPI-based backend application for the Study Helper project, featuring AI-powered content generation, community collaboration, and comprehensive quiz management.

## 🚀 Features

### Authentication & User Management ✅

- ✅ **User Authentication & Authorization**
  - JWT-based secure authentication system
  - User registration with email verification
  - Password reset functionality with secure token verification
  - Role-based access control (Admin, User roles)
  - Session management and tracking
  - Account activation system

- ✅ **User Management**
  - Comprehensive user profile management
  - User search and listing (admin functionality)
  - Profile updates and customization
  - User activity tracking and last login monitoring
  - Admin user management capabilities

### File Handling & AI Integration ✅

- ✅ **File Management**
  - Multi-format file upload support (PDF, DOCX, TXT, audio, images)
  - File access control and sharing between users
  - File deduplication using SHA256 hashing
  - File metadata management and organization

- ✅ **AI-Powered Content Generation**
  - AI-powered summary generation from multiple files and text
  - AI file caching for efficiency (Gemini File API integration)
  - Support for both file-based and text-based content processing
  - Smart caching system to avoid redundant AI API calls

### MCQ and Quiz Functionality ✅

- ✅ **MCQ Generation & Management**
  - AI-powered Multiple Choice Question (MCQ) generation from files
  - Manual MCQ creation and editing
  - Question tagging and categorization system
  - Difficulty level management (Easy, Medium, Hard)
  - Comprehensive question metadata and analytics

- ✅ **Quiz System**
  - Interactive quiz creation and management
  - Quiz sessions with real-time scoring
  - Comprehensive quiz history and analytics
  - Quiz sharing and collaboration features
  - Performance tracking and progress monitoring

### Community Features ✅

- ✅ **Community Management**
  - Community creation with unique shareable codes
  - Role-based access control (Admin, Moderator, Member)
  - Private and public community support
  - Community invitation and membership management
  - Community statistics and engagement analytics

- ✅ **Content Organization**
  - Subject management and linking to communities
  - File association with community subjects
  - Permission-based content curation
  - Collaborative content sharing and organization

### Interaction and Engagement Features ✅

- ✅ **Content Interactions**
  - Comment system for all content types (files, summaries, quizzes)
  - Threaded comments with reply functionality
  - Content rating system (1-5 stars)
  - Content analytics and engagement metrics

- ✅ **Notifications & Preferences**
  - Real-time notification system
  - Customizable user preferences
  - Email notification settings
  - Theme and display preferences
  - Notification filtering and management

### Advanced Features ✅

- ✅ **Content Versioning**
  - Automatic content version tracking
  - Version comparison and restoration
  - Content history and change tracking
  - Version analytics and insights

- ✅ **Analytics & Monitoring**
  - Comprehensive content analytics
  - User engagement metrics
  - System performance monitoring
  - Background task management
  - Content popularity tracking

- ✅ **AI Integration & Management**
  - Multi-provider AI API key management (Gemini, OpenAI)
  - API usage tracking and limits
  - Free tier usage monitoring
  - Secure API key encryption and storage

### Core Infrastructure Features ✅

- ✅ **Security & Performance**
  - Comprehensive security middleware
  - Rate limiting and request validation
  - Input sanitization and output encoding
  - Request/response logging and monitoring
  - Error handling and exception management

- ✅ **System Management**
  - Health check endpoints with detailed diagnostics
  - Background task processing
  - Database migration management
  - Configurable application settings
  - Comprehensive logging system

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
│   .........
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

2. **Create and activate virtual environment**

   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file with:

   ```env
   # Database Configuration
   DB_HOST=localhost
   DB_PORT=5432
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_NAME=study_helper
   
   # Security Settings
   JWT_SECRET_KEY=your-super-secret-key-change-this-in-production
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   
   # AI Integration
   GEMINI_API_KEY=your-gemini-api-key
   OPENAI_API_KEY=your-openai-api-key-optional
   
   # Default Admin User (optional)
   DEFAULT_ADMIN_USERNAME=admin
   DEFAULT_ADMIN_EMAIL=admin@studyhelper.com
   DEFAULT_ADMIN_PASSWORD=admin123
   
   # Default Free User (optional)
   DEFAULT_FREE_USER_USERNAME=freeuser
   DEFAULT_FREE_USER_EMAIL=free@studyhelper.com
   DEFAULT_FREE_USER_PASSWORD=free123
   
   # Email Configuration (optional)
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   EMAIL_FROM=noreply@studyhelper.com
   
   # File Upload Settings
   MAX_FILE_SIZE_MB=50
   FILE_UPLOAD_PATH=cache/file_uploads
   
   # Community Settings
   MAX_COMMUNITIES_PER_USER=3
   MAX_COMMUNITY_MEMBERSHIPS_PER_USER=10
   
   # Logging
   LOG_LEVEL=INFO
   ENABLE_ACCESS_LOGS=true
   ```

5. **Database Setup**

   ```bash
   # Create database (PostgreSQL)
   createdb study_helper
   
   # Run database migrations
   alembic upgrade head
   ```

6. **Initialize default data (optional)**

   ```bash
   # The application will automatically create default users on startup
   # if configured in the .env file
   ```

7. **Run the application**

   ```bash
   # Development mode
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   
   # Production mode
   python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Docker Setup (Alternative)

1. **Using Docker Compose**

   ```bash
   # Copy environment file
   cp .env.example .env
   # Edit .env with your configurations
   
   # Start services
   docker-compose up -d
   
   # Run migrations
   docker-compose exec api alembic upgrade head
   ```

2. **Access the application**
   - API: <http://localhost:8000>
   - Documentation: <http://localhost:8000/docs>
   - ReDoc: <http://localhost:8000/redoc>

### Test Features

- **Unit Tests**: Individual component testing
- **Integration Tests**: API endpoint testing with real database
- **Authentication Tests**: JWT token validation and user management
- **AI Integration Tests**: Mock and real AI service testing
- **Database Tests**: Model relationships and migrations
- **Security Tests**: Input validation and access control
- **Performance Tests**: Load testing and optimization validation

## 📚 API Documentation

Once the application is running, access the interactive API documentation:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

## 🔧 Configuration

The application supports extensive configuration through environment variables and settings:

### Authentication & Security Settings

- `JWT_SECRET_KEY`: Secret key for JWT token generation
- `JWT_ALGORITHM`: JWT algorithm (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration time (default: 30)
- `PASSWORD_RESET_TOKEN_EXPIRE_HOURS`: Password reset token expiration (default: 24)

### Database Configuration

- `DB_HOST`: Database host (default: localhost)
- `DB_PORT`: Database port (default: 5432)
- `DB_USER`: Database username
- `DB_PASSWORD`: Database password
- `DB_NAME`: Database name

### AI Integration Settings

- `GEMINI_API_KEY`: Google Gemini API key
- `OPENAI_API_KEY`: OpenAI API key (optional)
- `FREE_TIER_GEMINI_LIMIT`: Free tier API call limit for Gemini (default: 10)
- `FREE_TIER_OPENAI_LIMIT`: Free tier API call limit for OpenAI (default: 5)
- `AI_CACHE_EXPIRATION_HOURS`: AI file cache expiration (default: 48)

### File Upload Settings

- `MAX_FILE_SIZE_MB`: Maximum file size in MB (default: 50)
- `ALLOWED_FILE_TYPES`: Supported file extensions
- `FILE_UPLOAD_PATH`: Directory for file storage (default: cache/file_uploads)

### Community Settings

- `MAX_COMMUNITIES_PER_USER`: Maximum communities a user can create (default: 3)
- `MAX_COMMUNITY_MEMBERSHIPS_PER_USER`: Maximum communities a user can join (default: 10)
- `COMMUNITY_CODE_LENGTH`: Length of community invitation codes (default: 8)

### Email Configuration

- `SMTP_SERVER`: SMTP server for email notifications
- `SMTP_PORT`: SMTP port (default: 587)
- `SMTP_USERNAME`: SMTP username
- `SMTP_PASSWORD`: SMTP password
- `EMAIL_FROM`: Default sender email address

### Logging & Monitoring

- `LOG_LEVEL`: Application log level (default: INFO)
- `LOG_FORMAT`: Log format configuration
- `ENABLE_ACCESS_LOGS`: Enable request/response logging (default: True)
- `LOG_ROTATION_SIZE`: Log file rotation size (default: 10MB)

## 🚦 API Endpoints

### Authentication & User Management

- `POST /auth/register` - User registration with email verification
- `POST /auth/login` - User login with JWT token generation
- `POST /auth/forgot-password` - Password reset request
- `POST /auth/reset-password` - Password reset confirmation
- `POST /auth/activate` - Account activation
- `GET /users/me` - Get current user profile
- `PUT /users/me` - Update current user profile
- `GET /users/` - List all users (admin only)
- `GET /users/{user_id}` - Get user by ID (admin only)

### File Management

- `POST /files/upload` - Upload files with metadata
- `GET /files` - List user files with filtering
- `GET /files/{file_id}` - Get file details
- `POST /files/{file_id}/share` - Share files with other users
- `DELETE /files/{file_id}` - Delete files
- `GET /files/{file_id}/download` - Download files

### AI Features

- `POST /summaries/generate` - Generate AI summaries from files/text
- `GET /summaries` - List user summaries
- `GET /summaries/{summary_id}` - Get summary details
- `POST /mcqs/generate` - Generate MCQs from files using AI
- `GET /mcqs/questions` - List MCQ questions with filtering
- `POST /mcqs/questions` - Create manual MCQ questions
- `PUT /mcqs/questions/{question_id}` - Update MCQ questions

### Quiz Management

- `GET /mcqs/quizzes` - List quizzes
- `POST /mcqs/quizzes` - Create quizzes
- `GET /mcqs/quizzes/{quiz_id}` - Get quiz details
- `POST /mcqs/quizzes/{quiz_id}/sessions` - Start quiz sessions
- `GET /mcqs/sessions/{session_id}` - Get quiz session details
- `POST /mcqs/sessions/{session_id}/submit` - Submit quiz answers

### Community Features

- `POST /communities` - Create communities
- `GET /communities` - List communities
- `GET /communities/{id}` - Get community details
- `POST /communities/join` - Join community with code
- `GET /communities/{id}/members` - Get community members
- `POST /communities/{id}/members/{user_id}/role` - Update member role
- `POST /communities/{id}/subjects` - Add subjects to community
- `POST /communities/{id}/files` - Associate files with community subjects

### Content Interactions

- `POST /interactions/comments` - Add comments to content
- `GET /interactions/comments/{content_type}/{content_id}` - Get content comments
- `POST /interactions/ratings` - Rate content
- `GET /interactions/ratings/{content_type}/{content_id}` - Get content ratings
- `GET /interactions/ratings/{content_type}/{content_id}/stats` - Get rating statistics

### Notifications & Preferences

- `GET /notifications` - List user notifications
- `PUT /notifications/{id}/read` - Mark notification as read
- `PUT /notifications/mark-all-read` - Mark all notifications as read
- `GET /preferences` - Get user preferences
- `PUT /preferences` - Update user preferences

### Analytics & Versioning

- `GET /analytics/content/{content_type}/{content_id}` - Get content analytics
- `POST /analytics/content/{content_type}/{content_id}/increment` - Increment metrics
- `GET /versioning/content/{content_type}/{content_id}/versions` - Get content versions
- `POST /versioning/content/{content_type}/{content_id}/create-version` - Create version
- `POST /versioning/content/{content_type}/{content_id}/restore/{version_id}` - Restore version

### AI API Management

- `POST /api-keys` - Create AI API keys
- `GET /api-keys` - List user API keys
- `PUT /api-keys/{key_id}` - Update API key
- `POST /api-keys/{key_id}/test` - Test API key validity
- `GET /api-keys/usage/summary` - Get API usage summary

### System & Health

- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed health check
- `GET /health/database` - Database health check
- `GET /health/ai-services` - AI services health check
- `POST /background-tasks/analytics/sync` - Sync analytics (admin)
- `GET /background-tasks/{task_id}/status` - Get task status

## 🎯 Development Status & Roadmap

### ✅ Completed Milestones

- **Project setup, core models, and database configuration
- **User authentication and authorization system
- **File handling and AI integration (summary generation)
- **MCQ and quiz functionality
- **Community features and collaboration
- **Content interaction features (comments, ratings, notifications)
- **Advanced features (analytics, versioning, AI management)

### 🚧 Current Focus

- **Comprehensive testing and deployment preparation
  - Enhanced integration testing
  - Performance optimization
  - Security hardening
  - Production deployment configuration
  - CI/CD pipeline setup

### 🔮 Future Enhancements

- **Advanced AI Features**
  - Support for additional AI providers
  - Custom AI model fine-tuning
  - Advanced content analysis and insights
  
- **Enhanced Collaboration**
  - Real-time collaborative editing
  - Live quiz sessions with multiple participants
  - Advanced community moderation tools
  
- **Performance & Scaling**
  - Redis caching layer
  - CDN integration for file delivery
  - Microservices architecture preparation
  
- **Mobile & Web Integration**
  - Progressive Web App (PWA) support
  - Mobile-optimized API endpoints
  - Offline capability for core features

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
