"""File utilities for validation, storage, and processing."""

import hashlib
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings

settings = get_settings()


class FileValidationError(Exception):
    """Custom exception for file validation errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


def validate_file(file: UploadFile) -> None:
    """
    Validate uploaded file against security and business rules.
    
    Args:
        file: FastAPI UploadFile object
        
    Raises:
        FileValidationError: If file fails validation
    """
    # Check if file is provided
    if not file:
        raise FileValidationError("No file provided")
    
    # Check filename
    if not file.filename:
        raise FileValidationError("Filename is required")
    
    # Check file size
    if file.size is None:
        # Read file to get size if not provided
        content = file.file.read()
        file_size = len(content)
        file.file.seek(0)  # Reset file pointer
    else:
        file_size = file.size
    
    if file_size == 0:
        raise FileValidationError("File is empty")
    
    if file_size > settings.max_file_size:
        raise FileValidationError(
            f"File size ({file_size} bytes) exceeds maximum allowed size ({settings.max_file_size} bytes)",
            details={"max_size": settings.max_file_size, "actual_size": file_size}
        )
    
    # Check MIME type
    detected_mime_type = get_mime_type(file.filename)
    if detected_mime_type not in settings.allowed_file_types:
        raise FileValidationError(
            f"File type '{detected_mime_type}' is not allowed",
            details={
                "detected_type": detected_mime_type,
                "allowed_types": settings.allowed_file_types
            }
        )
    
    # Additional security checks
    filename_lower = file.filename.lower()
    
    # Check for dangerous file extensions
    dangerous_extensions = [
        '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.vbe',
        '.js', '.jar', '.php', '.asp', '.aspx', '.jsp', '.sh', '.ps1'
    ]
    
    for ext in dangerous_extensions:
        if filename_lower.endswith(ext):
            raise FileValidationError(
                f"File extension '{ext}' is not allowed for security reasons"
            )
    
    # Check for hidden files or files with suspicious names
    if filename_lower.startswith('.'):
        raise FileValidationError("Hidden files are not allowed")
    
    # Check filename length
    if len(file.filename) > 255:
        raise FileValidationError("Filename is too long (max 255 characters)")


def get_mime_type(filename: str) -> str:
    """
    Get MIME type for a filename.
    
    Args:
        filename: Name of the file
        
    Returns:
        MIME type string
    """
    mime_type, _ = mimetypes.guess_type(filename)
    
    # Default to octet-stream if type cannot be determined
    if mime_type is None:
        mime_type = 'application/octet-stream'
    
    return mime_type


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename while preserving the extension.
    
    Args:
        original_filename: Original filename
        
    Returns:
        Unique filename with UUID
    """
    # Get file extension
    file_extension = Path(original_filename).suffix
    
    # Generate UUID-based filename
    unique_id = str(uuid.uuid4())
    return f"{unique_id}{file_extension}"


def calculate_file_hash(content: bytes) -> str:
    """
    Calculate SHA-256 hash of file content.
    
    Args:
        content: File content as bytes
        
    Returns:
        SHA-256 hash as hexadecimal string
    """
    return hashlib.sha256(content).hexdigest()


def ensure_upload_directory() -> Path:
    """
    Ensure upload directory exists and return Path object.
    
    Returns:
        Path object for upload directory
    """
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    
    # Check if directory is writable
    if not os.access(upload_path, os.W_OK):
        raise FileValidationError(
            f"Upload directory '{upload_path}' is not writable"
        )
    
    return upload_path


async def save_file(file: UploadFile, stored_filename: str) -> Tuple[str, bytes, int]:
    """
    Save uploaded file to disk.
    
    Args:
        file: FastAPI UploadFile object
        stored_filename: Unique filename to store as
        
    Returns:
        Tuple of (file_path, content, file_size)
    """
    upload_dir = ensure_upload_directory()
    file_path = upload_dir / stored_filename
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Reset file pointer for any subsequent reads
    await file.seek(0)
    
    # Write file to disk
    try:
        with open(file_path, 'wb') as f:
            f.write(content)
    except IOError as e:
        raise FileValidationError(f"Failed to save file: {str(e)}")
    
    return str(file_path), content, file_size


def delete_file_from_disk(file_path: str) -> bool:
    """
    Delete file from disk.
    
    Args:
        file_path: Path to file to delete
        
    Returns:
        True if file was deleted, False if file didn't exist
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            return True
        return False
    except Exception:
        # Log error but don't fail - file might already be deleted
        return False


def get_file_size_human_readable(size_bytes: int) -> str:
    """
    Convert file size to human readable format.
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        Human readable file size
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    size = size_bytes
    unit_index = 0
    
    while size >= 1024 and unit_index < len(size_names) - 1:
        size /= 1024.0
        unit_index += 1
    
    if unit_index == 0:
        return f"{size:.0f} {size_names[unit_index]}"
    else:
        return f"{size:.1f} {size_names[unit_index]}"


def create_file_response(file_path: str, filename: str) -> FileResponse:
    """
    Create FastAPI FileResponse for file download.
    
    Args:
        file_path: Path to file on disk
        filename: Original filename to use in response
        
    Returns:
        FastAPI FileResponse
        
    Raises:
        HTTPException: If file not found
    """
    path = Path(file_path)
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get MIME type for proper headers
    mime_type = get_mime_type(filename)
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=mime_type
    )


def is_text_file(mime_type: str) -> bool:
    """
    Check if a MIME type represents a text file.
    
    Args:
        mime_type: MIME type string
        
    Returns:
        True if text file, False otherwise
    """
    text_types = [
        'text/plain',
        'text/markdown',
        'text/html',
        'text/csv',
        'application/json',
        'application/xml',
        'text/xml'
    ]
    
    return mime_type in text_types or mime_type.startswith('text/')


def is_pdf_file(mime_type: str) -> bool:
    """
    Check if a MIME type represents a PDF file.
    
    Args:
        mime_type: MIME type string
        
    Returns:
        True if PDF file, False otherwise
    """
    return mime_type == 'application/pdf'


def get_file_content(file_path: str) -> str:
    """
    Read and return file content as string.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File content as string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        UnicodeDecodeError: If file cannot be decoded as text
        IOError: If file cannot be read
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Try to read as text file
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # If UTF-8 fails, try with different encoding
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()
                
    except IOError as e:
        raise IOError(f"Failed to read file {file_path}: {str(e)}")