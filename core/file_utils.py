"""
Utilities for file handling operations.
"""
import os
import hashlib
import shutil
from typing import Optional, Tuple
from fastapi import UploadFile
from core.config import settings


async def save_upload_file(upload_file: UploadFile, subfolder: str = "") -> Tuple[str, str, int, str]:
    """
    Save an uploaded file to disk and return its metadata.
    
    Args:
        upload_file: The uploaded file from FastAPI
        subfolder: Optional subfolder within the upload directory
        
    Returns:
        Tuple containing (file_path, file_hash, file_size, mime_type)
    """
    # Create upload directory if it doesn't exist
    upload_dir = settings.upload_directory
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    
    # Get file content and calculate hash
    content = await upload_file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    file_size = len(content)
    
    # Use hash as part of filename to avoid collisions
    file_extension = os.path.splitext(upload_file.filename)[1].lower()
    safe_filename = f"{file_hash}{file_extension}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    # Write file to disk
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Reset file pointer for potential further processing
    await upload_file.seek(0)
    
    return file_path, file_hash, file_size, upload_file.content_type



def delete_file(file_path: str) -> bool:
    """
    Delete a file from disk.
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        # Log the error
        return False


def validate_file_type(filename: str) -> bool:
    """
    Validate if the file type is allowed.
    
    Args:
        filename: Name of the file
        
    Returns:
        bool: True if file type is allowed, False otherwise
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in settings.allowed_file_types


def validate_file_size(file_size: int) -> bool:
    """
    Validate if the file size is within allowed limits.
    
    Args:
        file_size: Size of the file in bytes
        
    Returns:
        bool: True if file size is allowed, False otherwise
    """
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    return file_size <= max_size_bytes 