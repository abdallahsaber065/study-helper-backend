# Phase 2: Authentication System Implementation

## Overview

Phase 2 implements a comprehensive JWT-based authentication system with user registration, login, and protected routes. This phase establishes the foundation for secure user management and access control throughout the application.

## Architecture Overview

### Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Database
    participant JWT

    Client->>API: POST /auth/register
    API->>Database: Create user with hashed password
    Database-->>API: User created
    API-->>Client: UserResponse (without password)

    Client->>API: POST /auth/token (login)
    API->>Database: Verify user credentials
    Database-->>API: User data
    API->>JWT: Generate access & refresh tokens
    JWT-->>API: Tokens
    API-->>Client: Token response

    Client->>API: GET /users/me (with Bearer token)
    API->>JWT: Verify token
    JWT-->>API: User ID
    API->>Database: Fetch user data
    Database-->>API: User data
    API-->>Client: User profile
```

### Security Architecture

- **Password Security**: bcrypt hashing with salt rounds
- **JWT Tokens**: HS256 algorithm with configurable expiration
- **Token Types**: Access tokens (30 min) and refresh tokens (7 days)
- **Input Validation**: Pydantic models with strict validation
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries

## Data Models

### User Model

```python
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
```

**Field Descriptions:**

- `id`: Primary key, auto-incrementing integer
- `email`: Unique email address, used as username
- `hashed_password`: bcrypt-hashed password (never stored in plain text)
- `is_active`: Account status (for soft deletion/deactivation)
- `is_verified`: Email verification status (for future email verification)
- `created_at`: Account creation timestamp (UTC)
- `updated_at`: Last modification timestamp (UTC)

## Authentication Components

### 1. Password Management (`app/auth/utils.py`)

**Password Hashing:**

```python
def hash_password(password: str) -> str:
    """Hash password using bcrypt with automatic salt generation."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)
```

**Security Features:**

- bcrypt algorithm with automatic salt generation
- Configurable rounds (default: 12)
- Timing-safe comparison

### 2. JWT Token Management

**Token Creation:**

```python
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with configurable expiration."""
    
def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token for session extension."""
```

**Token Structure:**

```json
{
  "sub": "user_id",
  "exp": "expiration_timestamp",
  "iat": "issued_at_timestamp"
}
```

**Security Features:**

- HS256 algorithm (HMAC with SHA-256)
- Configurable expiration times
- Subject claim contains user ID
- Automatic expiration validation

### 3. Authentication Dependencies (`app/auth/dependencies.py`)

**Dependency Hierarchy:**

1. `get_current_user`: Extract and validate user from JWT
2. `get_current_active_user`: Ensure user is active
3. `get_current_verified_user`: Ensure user is verified
4. `get_optional_current_user`: Optional authentication

## API Endpoints

### Authentication Endpoints (`/auth`)

#### 1. User Registration

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (201 Created):**

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_verified": false,
  "created_at": "2025-01-14T10:30:00Z",
  "updated_at": null
}
```

**Validation Rules:**

- Email: Valid email format, unique
- Password: Minimum 8 characters, maximum 100 characters

#### 2. Token Login (OAuth2 Compatible)

```http
POST /auth/token
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=securepassword123
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### 3. JSON Login (Alternative)

```http
POST /auth/login
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "securepassword123"
}
```

#### 4. Logout

```http
POST /auth/logout
Authorization: Bearer <access_token>
```

**Response (200 OK):**

```json
{
  "message": "Successfully logged out",
  "detail": "Please remove the token from client storage"
}
```

### User Management Endpoints (`/users`)

#### 1. Get Current User Profile

```http
GET /users/me
Authorization: Bearer <access_token>
```

**Response (200 OK):**

```json
{
  "id": 1,
  "email": "user@example.com",
  "is_active": true,
  "is_verified": false,
  "created_at": "2025-01-14T10:30:00Z",
  "updated_at": null
}
```

#### 2. Update Current User

```http
PUT /users/me
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email": "newemail@example.com",
  "is_active": true
}
```

#### 3. Deactivate Account

```http
DELETE /users/me
Authorization: Bearer <access_token>
```

**Note:** Requires verified user. Performs soft deletion (sets `is_active = false`).

## Schema Definitions

### Request Schemas

```python
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)

class LoginRequest(BaseModel):
    username: EmailStr  # OAuth2 compatibility
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
```

### Response Schemas

```python
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime]

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
```

## Security Considerations

### 1. Password Security

- **Hashing**: bcrypt with automatic salt generation
- **Validation**: Minimum 8 characters, maximum 100 characters
- **Storage**: Never store plain text passwords
- **Timing Attacks**: Use timing-safe comparison

### 2. JWT Security

- **Algorithm**: HS256 (HMAC with SHA-256)
- **Secret**: Minimum 32-character secret key
- **Expiration**: Short-lived access tokens (30 minutes)
- **Refresh**: Longer-lived refresh tokens (7 days)
- **Validation**: Automatic signature and expiration validation

### 3. Input Validation

- **Email**: Pydantic EmailStr validation
- **SQL Injection**: SQLAlchemy ORM prevents injection
- **XSS**: JSON responses, no HTML rendering
- **CSRF**: Stateless JWT tokens

### 4. Error Handling

- **Generic Errors**: No sensitive information in error messages
- **Rate Limiting**: Prepared for future implementation
- **Audit Logging**: Structured logging for security events

## Database Schema

### Migration: `20250814_0212_f8c4a37a9ad1_add_user_model_for_authentication.py`

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_id ON users (id);
```

## Configuration

### Environment Variables

```env
# Security
SECRET_KEY="your-super-secret-key-here-at-least-32-chars"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL="postgresql://user:password@localhost:5432/database"
```

### Security Requirements

- `SECRET_KEY`: Minimum 32 characters for JWT signing
- `DATABASE_URL`: PostgreSQL connection string
- Strong password policy (enforced by Pydantic)

## Testing Strategy

### Unit Tests

- Password hashing and verification
- JWT token creation and validation
- User model validation
- Schema validation

### Integration Tests

- Registration flow
- Login flow
- Protected route access
- Token expiration handling
- Error responses

### Security Tests

- SQL injection attempts
- Invalid token handling
- Password strength validation
- Rate limiting (future)

## Error Responses

### Common Error Formats

```json
{
  "detail": "Error description",
  "error_code": "SPECIFIC_ERROR_CODE"
}
```

### Authentication Errors

| Status | Error | Description |
|--------|-------|-------------|
| 400 | Email already registered | Registration with existing email |
| 401 | Incorrect email or password | Invalid login credentials |
| 401 | Token has expired | JWT token expired |
| 401 | Could not validate credentials | Invalid or malformed JWT |
| 400 | Inactive user | User account deactivated |
| 400 | User email not verified | Action requires verified user |

## Future Enhancements

### Phase 3+ Features

- Email verification system
- Password reset functionality
- Multi-factor authentication (MFA)
- OAuth2 social login integration
- Role-based access control (RBAC)
- Session management and blacklisting
- Account lockout after failed attempts

### Security Improvements

- Rate limiting per endpoint
- IP-based restrictions
- Device fingerprinting
- Suspicious activity detection
- Security headers middleware
- OWASP compliance audit

## Usage Examples

### Client Integration

```javascript
// Registration
const registerResponse = await fetch('/auth/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'securepassword123'
  })
});

// Login
const loginResponse = await fetch('/auth/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=user@example.com&password=securepassword123'
});

const tokens = await loginResponse.json();

// Authenticated Request
const profileResponse = await fetch('/users/me', {
  headers: { 
    'Authorization': `Bearer ${tokens.access_token}` 
  }
});
```

### Python Client

```python
import httpx

# Registration
async with httpx.AsyncClient() as client:
    register_response = await client.post(
        'http://localhost:8000/auth/register',
        json={'email': 'user@example.com', 'password': 'securepassword123'}
    )
    
    # Login
    login_response = await client.post(
        'http://localhost:8000/auth/token',
        data={'username': 'user@example.com', 'password': 'securepassword123'}
    )
    
    tokens = login_response.json()
    
    # Authenticated request
    profile_response = await client.get(
        'http://localhost:8000/users/me',
        headers={'Authorization': f"Bearer {tokens['access_token']}"}
    )
```

## Troubleshooting

### Common Issues

1. **"Field required" for SECRET_KEY**
   - Ensure `.env` file exists with proper SECRET_KEY
   - Verify SECRET_KEY is at least 32 characters

2. **Database connection errors**
   - Check PostgreSQL is running
   - Verify DATABASE_URL in `.env` file
   - Ensure database and user exist

3. **Token validation errors**
   - Check token format (Bearer prefix)
   - Verify token hasn't expired
   - Ensure SECRET_KEY matches between token creation and validation

4. **Migration issues**
   - Run `alembic upgrade head` to apply migrations
   - Check database permissions
   - Verify alembic.ini configuration

## Deployment Notes

### Production Considerations

- Use strong, randomly generated SECRET_KEY
- Enable HTTPS for all authentication endpoints
- Configure proper CORS origins
- Set up monitoring for authentication events
- Implement rate limiting
- Regular security audits

### Environment Setup

- PostgreSQL database with proper user permissions
- Redis for future session management
- Load balancer with SSL termination
- Monitoring and logging infrastructure

**Next Phase**: [Phase 3 - File Upload & Management System](./phase3_file_management.md)
