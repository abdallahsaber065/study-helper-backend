# Phase 3: File Upload & Management System

## Overview

Phase 3 implements a comprehensive file upload and management system that allows authenticated users to securely upload, store, list, and delete files. The system focuses on security, performance, and user experience while preparing for AI processing in future phases.

## Architecture & Design Decisions

### Security-First Approach

The file management system implements multiple layers of security to protect against common file upload vulnerabilities:

- **File Type Validation**: Only allows PDF, plain text, and Markdown files
- **Size Restrictions**: 10MB maximum file size to prevent abuse
- **Malicious Extension Blocking**: Blocks executable and script files
- **Hash-based Deduplication**: Prevents users from uploading identical files
- **Secure File Naming**: UUID-based filenames prevent path traversal attacks
- **MIME Type Detection**: Validates actual file content against extensions

### Database Schema

#### FileMetadata Model

```python
class FileMetadata(Base):
    __tablename__ = "file_metadata"
    
    id: str (UUID)              # Primary key, unique identifier
    user_id: int                # Foreign key to users table
    original_filename: str      # User's original filename
    stored_filename: str        # UUID-based storage filename
    file_path: str             # Full path to stored file
    file_size: int             # File size in bytes
    mime_type: str             # Detected MIME type
    file_hash: str             # SHA-256 hash for deduplication
    description: str (optional) # User-provided description
    is_processed: bool         # Flag for AI processing status
    created_at: datetime       # Upload timestamp
    updated_at: datetime       # Last modification timestamp
```

#### Key Design Features

1. **UUID Primary Keys**: Prevents enumeration attacks and provides globally unique identifiers
2. **User Isolation**: All file operations are scoped to the authenticated user
3. **Hash-based Deduplication**: Saves storage space and prevents duplicate uploads
4. **Processing Status**: Tracks whether files have been processed by AI systems
5. **Audit Trail**: Timestamps for creation and updates

### File Storage Strategy

#### Local Development Storage

- **Directory Structure**: `uploads/` directory in project root
- **File Naming**: UUID + original extension (e.g., `abc123-def456.pdf`)
- **Access Control**: Files are stored outside web root for security
- **Cleanup**: Automatic cleanup when database records are deleted

#### Production Considerations

The current implementation uses local file storage for development. For production deployment:

- **S3-Compatible Storage**: Ready for AWS S3, DigitalOcean Spaces, or MinIO
- **CDN Integration**: Can be enhanced with CloudFront or similar CDN
- **Pre-signed URLs**: Secure file access without exposing server resources
- **Backup Strategy**: Regular backups of both files and metadata

### API Endpoints

#### File Upload: `POST /files/upload`

**Features:**

- Multi-part form upload with file validation
- Optional description field
- Automatic deduplication
- Comprehensive error handling

**Security Measures:**

- File type validation against whitelist
- Size limit enforcement (10MB)
- Malicious extension detection
- Hash calculation for integrity

**Response Structure:**

```json
{
  "id": "uuid-string",
  "original_filename": "document.pdf",
  "file_size": 1024000,
  "mime_type": "application/pdf",
  "created_at": "2025-01-14T12:00:00Z",
  "message": "File uploaded successfully"
}
```

#### File Listing: `GET /files/`

**Features:**

- Pagination support (configurable page size)
- Search by filename (case-insensitive)
- MIME type filtering
- Total count and size aggregation
- Newest-first ordering

**Query Parameters:**

- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 20, max: 100)
- `search`: Search term for filenames
- `mime_type`: Filter by specific MIME type

**Response Structure:**

```json
{
  "files": [...],
  "total_count": 150,
  "total_size": 52428800,
  "page": 1,
  "per_page": 20,
  "has_next": true
}
```

#### File Download: `GET /files/{id}/download`

**Features:**

- Secure file streaming
- Proper MIME type headers
- Original filename preservation
- Access control validation

#### File Metadata: `GET /files/{id}`

**Features:**

- Complete metadata retrieval
- Processing status information
- File statistics

#### File Update: `PUT /files/{id}`

**Features:**

- Description updates only
- Input validation and sanitization
- Audit trail maintenance

#### File Deletion: `DELETE /files/{id}`

**Features:**

- Secure file removal from disk
- Database record cleanup
- Error handling for missing files

#### Bulk Deletion: `DELETE /files/`

**Features:**

- Confirmation required (`confirm=true` parameter)
- Batch processing for performance
- Complete cleanup of files and metadata

### Error Handling & Validation

#### Validation Layers

1. **Schema Validation**: Pydantic models validate all input data
2. **Business Rules**: File size, type, and naming restrictions
3. **Security Checks**: Malicious extension and content validation
4. **Database Constraints**: Foreign key and uniqueness validation

#### Error Response Format

```json
{
  "error": "validation_error",
  "message": "File type 'application/exe' is not allowed",
  "details": {
    "detected_type": "application/exe",
    "allowed_types": ["application/pdf", "text/plain", "text/markdown"]
  }
}
```

#### Common Error Types

- `validation_error`: File validation failures
- `duplicate_file`: Hash-based duplicate detection
- `file_not_found`: Requested file doesn't exist
- `upload_failed`: Server-side upload errors
- `confirmation_required`: Bulk operations without confirmation

### Performance Optimizations

#### Database Level

- **Indexed Columns**: User ID, file hash, and creation date
- **Efficient Queries**: Optimized pagination and filtering
- **Connection Pooling**: PostgreSQL connection management
- **Query Optimization**: Minimal data transfer for list operations

#### File Operations

- **Streaming Uploads**: Memory-efficient file handling
- **Hash Calculation**: Single-pass processing during upload
- **Lazy Loading**: Metadata-only operations when possible
- **Cleanup Strategies**: Automatic file deletion with database records

### Security Implementation

#### Input Validation

- **File Extension Whitelist**: Only PDF, TXT, and MD files
- **MIME Type Verification**: Content-based validation
- **Size Limits**: Configurable maximum file size
- **Filename Sanitization**: Prevents path traversal attacks

#### Access Control

- **User Isolation**: Files are strictly scoped to uploading user
- **Authentication Required**: All endpoints require valid JWT tokens
- **Authorization Checks**: Per-request user validation
- **Session Management**: Secure token handling

#### File Storage Security

- **UUID Naming**: Prevents filename-based attacks
- **Directory Structure**: Files stored outside web root
- **Permission Control**: Restricted file system permissions
- **Hash Verification**: Integrity checks during operations

## Integration Points

### Authentication System

- **JWT Integration**: Seamless integration with Phase 2 authentication
- **User Relationships**: Files are linked to authenticated users
- **Permission Checks**: All operations validate user ownership

### Database System

- **SQLAlchemy Integration**: Uses existing ORM configuration
- **Migration Support**: Alembic-managed schema changes
- **Relationship Management**: Proper foreign key constraints

### Configuration System

- **Environment Variables**: Configurable upload limits and paths
- **Settings Management**: Centralized configuration via Pydantic
- **Development/Production**: Environment-specific settings

## Future Enhancements (Phase 4+ Ready)

### AI Processing Integration

- **Processing Status**: `is_processed` flag tracks AI operation status
- **Metadata Extension**: Ready for AI-generated summaries and quizzes
- **Queue Integration**: Prepared for Celery task processing
- **Progress Tracking**: Foundation for real-time processing updates

### Advanced Features

- **File Versioning**: Track multiple versions of the same document
- **Collaboration**: Share files between users with permissions
- **Advanced Search**: Full-text search within document content
- **Backup/Restore**: Automated backup and recovery procedures

## Testing Strategy

### Unit Tests

- File validation logic
- Hash calculation accuracy
- Error handling scenarios
- Utility function behavior

### Integration Tests

- Complete upload/download workflows
- Authentication integration
- Database operations
- Error response validation

### Security Tests

- Malicious file upload attempts
- Path traversal prevention
- Access control validation
- Input sanitization verification

## Monitoring & Observability

### Metrics Collection

- Upload success/failure rates
- File size distributions
- Storage utilization
- API response times

### Logging Strategy

- Structured JSON logging
- Security event tracking
- Error correlation IDs
- Performance monitoring

### Health Checks

- File system availability
- Storage capacity monitoring
- Database connectivity
- Upload directory permissions

## Deployment Considerations

### Development Environment

- Local file storage in `uploads/` directory
- SQLite or PostgreSQL database
- Debug logging enabled
- Relaxed CORS settings

### Production Environment

- S3-compatible object storage
- PostgreSQL with connection pooling
- Structured logging to external systems
- Security headers and rate limiting
- Regular backup procedures

## Configuration Reference

### Environment Variables

```env
# File Upload Settings
UPLOAD_DIR=uploads
MAX_FILE_SIZE=10485760  # 10MB in bytes
ALLOWED_FILE_TYPES=["application/pdf", "text/plain", "text/markdown"]

# Database Settings
DATABASE_URL=postgresql://user:pass@localhost/db
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Security Settings
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### File Type Configuration

The system currently supports:

- **PDF Files**: `application/pdf`
- **Plain Text**: `text/plain`
- **Markdown**: `text/markdown`

Additional types can be added by updating the `allowed_file_types` configuration.

## API Usage Examples

### Upload a File

```bash
curl -X POST "http://localhost:8000/files/upload" \
  -H "Authorization: Bearer your-jwt-token" \
  -F "file=@document.pdf" \
  -F "description=Important document"
```

### List Files with Search

```bash
curl -X GET "http://localhost:8000/files/?search=document&page=1&per_page=10" \
  -H "Authorization: Bearer your-jwt-token"
```

### Download a File

```bash
curl -X GET "http://localhost:8000/files/{file-id}/download" \
  -H "Authorization: Bearer your-jwt-token" \
  --output downloaded-file.pdf
```

### Delete a File

```bash
curl -X DELETE "http://localhost:8000/files/{file-id}" \
  -H "Authorization: Bearer your-jwt-token"
```

## Success Metrics

Phase 3 implementation provides:

✅ **Secure File Upload**: Multi-layer validation and security checks  
✅ **Efficient Storage**: UUID-based naming and hash deduplication  
✅ **User Experience**: Pagination, search, and filtering capabilities  
✅ **Scalable Architecture**: Ready for S3 and CDN integration  
✅ **Audit Trail**: Complete tracking of file operations  
✅ **Error Handling**: Comprehensive error responses and recovery  
✅ **Performance**: Optimized queries and streaming file operations  
✅ **Integration Ready**: Prepared for AI processing in Phase 4  

## Phase 4 Preparation

The file management system is now ready for AI processing integration:

- Files are stored with processing status flags
- Metadata structure supports AI-generated content
- Hash-based integrity ensures reliable AI input
- User isolation maintains security during processing
- Error handling accommodates async processing workflows

This foundation enables seamless integration with summary and quiz generation features in subsequent phases while maintaining security, performance, and user experience standards.

**Next Phase**: [Phase 4 - AI Processing Integration](./phase4_ai_summary_system.md)
