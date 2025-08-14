"""Unit tests for file utilities."""

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.files.utils import (
    FileValidationError,
    calculate_file_hash,
    create_file_response,
    delete_file_from_disk,
    ensure_upload_directory,
    generate_unique_filename,
    get_file_size_human_readable,
    get_mime_type,
    is_pdf_file,
    is_text_file,
    save_file,
    validate_file,
)


class TestFileValidation:
    """Test file validation functions."""
    
    def test_validate_file_no_file(self):
        """Test validation with no file provided."""
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(None)
        
        assert "No file provided" in str(exc_info.value)
    
    def test_validate_file_no_filename(self):
        """Test validation with no filename."""
        file = MagicMock(spec=UploadFile)
        file.filename = None
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "Filename is required" in str(exc_info.value)
    
    def test_validate_file_empty_file(self):
        """Test validation with empty file."""
        file = MagicMock(spec=UploadFile)
        file.filename = "test.txt"
        file.size = 0
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "File is empty" in str(exc_info.value)
    
    @patch("app.files.utils.settings")
    def test_validate_file_too_large(self, mock_settings):
        """Test validation with file too large."""
        mock_settings.max_file_size = 1000
        mock_settings.allowed_file_types = ["text/plain"]
        
        file = MagicMock(spec=UploadFile)
        file.filename = "test.txt"
        file.size = 2000
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "exceeds maximum allowed size" in str(exc_info.value)
        assert exc_info.value.details["max_size"] == 1000
        assert exc_info.value.details["actual_size"] == 2000
    
    @patch("app.files.utils.settings")
    def test_validate_file_invalid_type(self, mock_settings):
        """Test validation with invalid file type."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        
        file = MagicMock(spec=UploadFile)
        file.filename = "test.exe"
        file.size = 1000
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        # On Windows, .exe files are detected as application/x-msdownload
        error_message = str(exc_info.value)
        assert "is not allowed" in error_message
        assert any(mime_type in error_message for mime_type in ["application/x-msdownload", "application/octet-stream"])
    
    @patch("app.files.utils.settings")
    @patch("app.files.utils.get_mime_type")
    def test_validate_file_dangerous_extension(self, mock_get_mime_type, mock_settings):
        """Test validation with dangerous file extension."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        mock_get_mime_type.return_value = "text/plain"  # Allow MIME type to pass through
        
        file = MagicMock(spec=UploadFile)
        file.filename = "malware.exe"
        file.size = 1000
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "File extension '.exe' is not allowed for security reasons" in str(exc_info.value)
    
    @patch("app.files.utils.settings")
    @patch("app.files.utils.get_mime_type")
    def test_validate_file_hidden_file(self, mock_get_mime_type, mock_settings):
        """Test validation with hidden file."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        mock_get_mime_type.return_value = "text/plain"  # Allow MIME type to pass through
        
        file = MagicMock(spec=UploadFile)
        file.filename = ".hidden"
        file.size = 1000
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "Hidden files are not allowed" in str(exc_info.value)
    
    @patch("app.files.utils.settings")
    @patch("app.files.utils.get_mime_type")
    def test_validate_file_long_filename(self, mock_get_mime_type, mock_settings):
        """Test validation with long filename."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        mock_get_mime_type.return_value = "text/plain"  # Allow MIME type to pass through
        
        file = MagicMock(spec=UploadFile)
        file.filename = "a" * 260  # Longer than 255 characters
        file.size = 1000
        
        with pytest.raises(FileValidationError) as exc_info:
            validate_file(file)
        
        assert "Filename is too long" in str(exc_info.value)
    
    @patch("app.files.utils.settings")
    def test_validate_file_success(self, mock_settings):
        """Test successful file validation."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        
        file = MagicMock(spec=UploadFile)
        file.filename = "test.txt"
        file.size = 1000
        
        # Should not raise any exception
        validate_file(file)
    
    @patch("app.files.utils.settings")
    def test_validate_file_no_size_attribute(self, mock_settings):
        """Test validation when file.size is None."""
        mock_settings.max_file_size = 10000
        mock_settings.allowed_file_types = ["text/plain"]
        
        file = MagicMock(spec=UploadFile)
        file.filename = "test.txt"
        file.size = None
        
        # Mock the file.file attribute properly
        mock_file_handle = MagicMock()
        mock_file_handle.read.return_value = b"test content"
        mock_file_handle.seek = MagicMock()
        file.file = mock_file_handle
        
        # Should not raise any exception
        validate_file(file)
        
        # Check that file pointer was reset
        file.file.seek.assert_called_once_with(0)


class TestMimeTypeDetection:
    """Test MIME type detection."""
    
    def test_get_mime_type_text(self):
        """Test MIME type detection for text files."""
        assert get_mime_type("test.txt") == "text/plain"
        # Note: .md files may not be detected as text/markdown by mimetypes on all systems
        md_type = get_mime_type("test.md")
        assert md_type in ["text/markdown", "text/x-markdown", "application/octet-stream"]
    
    def test_get_mime_type_pdf(self):
        """Test MIME type detection for PDF files."""
        assert get_mime_type("document.pdf") == "application/pdf"
    
    def test_get_mime_type_json(self):
        """Test MIME type detection for JSON files."""
        assert get_mime_type("data.json") == "application/json"
    
    def test_get_mime_type_unknown(self):
        """Test MIME type detection for unknown files."""
        assert get_mime_type("unknown.xyz") == "application/octet-stream"
    
    def test_get_mime_type_no_extension(self):
        """Test MIME type detection for files without extension."""
        assert get_mime_type("README") == "application/octet-stream"


class TestFilenameGeneration:
    """Test unique filename generation."""
    
    def test_generate_unique_filename_with_extension(self):
        """Test unique filename generation preserves extension."""
        original = "document.pdf"
        unique = generate_unique_filename(original)
        
        assert unique.endswith(".pdf")
        assert unique != original
        assert len(unique) > len(original)  # UUID makes it longer
    
    def test_generate_unique_filename_no_extension(self):
        """Test unique filename generation without extension."""
        original = "README"
        unique = generate_unique_filename(original)
        
        assert unique != original
        assert "." not in unique  # No extension preserved
    
    def test_generate_unique_filename_multiple_dots(self):
        """Test unique filename generation with multiple dots."""
        original = "my.document.v2.pdf"
        unique = generate_unique_filename(original)
        
        assert unique.endswith(".pdf")
        assert unique != original
    
    def test_generate_unique_filename_uniqueness(self):
        """Test that generated filenames are unique."""
        original = "test.txt"
        unique1 = generate_unique_filename(original)
        unique2 = generate_unique_filename(original)
        
        assert unique1 != unique2


class TestFileHashing:
    """Test file hash calculation."""
    
    def test_calculate_file_hash(self):
        """Test SHA-256 hash calculation."""
        content = b"Hello, World!"
        expected_hash = hashlib.sha256(content).hexdigest()
        
        result = calculate_file_hash(content)
        assert result == expected_hash
    
    def test_calculate_file_hash_empty(self):
        """Test hash calculation for empty content."""
        content = b""
        expected_hash = hashlib.sha256(content).hexdigest()
        
        result = calculate_file_hash(content)
        assert result == expected_hash
    
    def test_calculate_file_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = b"Hello, World!"
        content2 = b"Hello, Universe!"
        
        hash1 = calculate_file_hash(content1)
        hash2 = calculate_file_hash(content2)
        
        assert hash1 != hash2


class TestUploadDirectory:
    """Test upload directory management."""
    
    @patch("app.files.utils.settings")
    @patch("pathlib.Path.mkdir")
    @patch("os.access")
    def test_ensure_upload_directory_success(self, mock_access, mock_mkdir, mock_settings):
        """Test successful upload directory creation."""
        mock_settings.upload_dir = "/tmp/uploads"
        mock_access.return_value = True  # Directory is writable
        
        result = ensure_upload_directory()
        
        # Normalize path separators for cross-platform compatibility
        assert str(result).replace("\\", "/") == "/tmp/uploads"
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    
    @patch("app.files.utils.settings")
    @patch("pathlib.Path.mkdir")
    @patch("os.access")
    def test_ensure_upload_directory_not_writable(self, mock_access, mock_mkdir, mock_settings):
        """Test upload directory not writable."""
        mock_settings.upload_dir = "/tmp/uploads"
        mock_access.return_value = False  # Directory is not writable
        
        with pytest.raises(FileValidationError) as exc_info:
            ensure_upload_directory()
        
        assert "not writable" in str(exc_info.value)


class TestFileSaving:
    """Test file saving functionality."""
    
    @pytest.fixture
    def mock_file(self):
        """Mock UploadFile."""
        file = MagicMock(spec=UploadFile)
        file.read.return_value = b"test content"
        file.seek.return_value = None
        return file
    
    @patch("app.files.utils.ensure_upload_directory")
    @patch("builtins.open", new_callable=mock_open)
    async def test_save_file_success(self, mock_file_open, mock_ensure_dir, mock_file):
        """Test successful file saving."""
        mock_ensure_dir.return_value = Path("/tmp/uploads")
        
        file_path, content, file_size = await save_file(mock_file, "unique_filename.txt")
        
        # Normalize path separators for cross-platform compatibility
        assert file_path.replace("\\", "/") == "/tmp/uploads/unique_filename.txt"
        assert content == b"test content"
        assert file_size == 12  # len("test content")
        
        mock_file_open.assert_called_once_with(Path("/tmp/uploads/unique_filename.txt"), 'wb')
        mock_file_open().write.assert_called_once_with(b"test content")
    
    @patch("app.files.utils.ensure_upload_directory")
    @patch("builtins.open", side_effect=IOError("Permission denied"))
    async def test_save_file_io_error(self, mock_file_open, mock_ensure_dir, mock_file):
        """Test file saving with IO error."""
        mock_ensure_dir.return_value = Path("/tmp/uploads")
        
        with pytest.raises(FileValidationError) as exc_info:
            await save_file(mock_file, "unique_filename.txt")
        
        assert "Failed to save file" in str(exc_info.value)


class TestFileDeletion:
    """Test file deletion functionality."""
    
    def test_delete_file_from_disk_success(self):
        """Test successful file deletion."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"test content")
            temp_path = temp_file.name
        
        # Verify file exists
        assert Path(temp_path).exists()
        
        # Delete file
        result = delete_file_from_disk(temp_path)
        
        assert result is True
        assert not Path(temp_path).exists()
    
    def test_delete_file_from_disk_not_exists(self):
        """Test deleting non-existent file."""
        non_existent_path = "/tmp/non_existent_file.txt"
        
        result = delete_file_from_disk(non_existent_path)
        
        assert result is False
    
    @patch("pathlib.Path.unlink", side_effect=PermissionError("Permission denied"))
    @patch("pathlib.Path.exists", return_value=True)
    def test_delete_file_from_disk_permission_error(self, mock_exists, mock_unlink):
        """Test file deletion with permission error."""
        file_path = "/tmp/protected_file.txt"
        
        # Should not raise exception, just return False
        result = delete_file_from_disk(file_path)
        
        assert result is False


class TestFileSizeUtils:
    """Test file size utility functions."""
    
    def test_get_file_size_human_readable_bytes(self):
        """Test human readable size for bytes."""
        assert get_file_size_human_readable(0) == "0 B"
        assert get_file_size_human_readable(512) == "512 B"
        assert get_file_size_human_readable(1023) == "1023 B"
    
    def test_get_file_size_human_readable_kb(self):
        """Test human readable size for KB."""
        assert get_file_size_human_readable(1024) == "1.0 KB"
        assert get_file_size_human_readable(1536) == "1.5 KB"
    
    def test_get_file_size_human_readable_mb(self):
        """Test human readable size for MB."""
        assert get_file_size_human_readable(1024 * 1024) == "1.0 MB"
        assert get_file_size_human_readable(int(2.5 * 1024 * 1024)) == "2.5 MB"
    
    def test_get_file_size_human_readable_gb(self):
        """Test human readable size for GB."""
        assert get_file_size_human_readable(1024 * 1024 * 1024) == "1.0 GB"
    
    def test_get_file_size_human_readable_tb(self):
        """Test human readable size for TB."""
        assert get_file_size_human_readable(1024 * 1024 * 1024 * 1024) == "1.0 TB"


class TestFileResponse:
    """Test file response creation."""
    
    def test_create_file_response_success(self):
        """Test successful file response creation."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"test content")
            temp_path = temp_file.name
        
        try:
            response = create_file_response(temp_path, "test.txt")
            
            assert response.path == temp_path
            assert response.filename == "test.txt"
            assert response.media_type == "text/plain"
        finally:
            # Cleanup
            os.unlink(temp_path)
    
    def test_create_file_response_file_not_found(self):
        """Test file response with non-existent file."""
        with pytest.raises(HTTPException) as exc_info:
            create_file_response("/tmp/non_existent.txt", "test.txt")
        
        assert exc_info.value.status_code == 404
        assert "File not found" in exc_info.value.detail


class TestFileTypeChecks:
    """Test file type checking utilities."""
    
    def test_is_text_file(self):
        """Test text file type detection."""
        assert is_text_file("text/plain") is True
        assert is_text_file("text/markdown") is True
        assert is_text_file("text/html") is True
        assert is_text_file("application/json") is True
        assert is_text_file("text/csv") is True
        assert is_text_file("text/custom") is True  # Any text/* type
        
        assert is_text_file("application/pdf") is False
        assert is_text_file("image/jpeg") is False
        assert is_text_file("application/octet-stream") is False
    
    def test_is_pdf_file(self):
        """Test PDF file type detection."""
        assert is_pdf_file("application/pdf") is True
        
        assert is_pdf_file("text/plain") is False
        assert is_pdf_file("application/json") is False
        assert is_pdf_file("application/octet-stream") is False


class TestFileValidationErrorClass:
    """Test FileValidationError exception class."""
    
    def test_file_validation_error_basic(self):
        """Test basic FileValidationError creation."""
        error = FileValidationError("Test error")
        
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
    
    def test_file_validation_error_with_details(self):
        """Test FileValidationError with details."""
        details = {"max_size": 1000, "actual_size": 2000}
        error = FileValidationError("File too large", details)
        
        assert str(error) == "File too large"
        assert error.message == "File too large"
        assert error.details == details
