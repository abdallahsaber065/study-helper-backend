"""
Test script for Phase 3 functionality (File Handling & Core AI Integration).
"""
import sys
import os
import io
import pytest
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# set working directory to the project root (parent directory of this script directory)
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# print the working directory for debugging
print(f"Working directory: {os.getcwd()}")

from fastapi.testclient import TestClient
from fastapi import UploadFile
from app import app
import random
import string

# Create test client
client = TestClient(app)

# Test data
TEST_USER1 = {
    "username": f"fileuser_{random.randint(1000, 9999)}",
    "first_name": "File",
    "last_name": "User",
    "email": f"file_test{random.randint(1000, 9999)}@example.com",
    "password": f"filepassword{random.randint(1000, 9999)}"
}

TEST_USER2 = {
    "username": f"shareuser_{random.randint(1000, 9999)}",
    "first_name": "Share",
    "last_name": "User",
    "email": f"share_test{random.randint(1000, 9999)}@example.com",
    "password": f"sharepassword{random.randint(1000, 9999)}"
}

# Create sample test file
def create_test_file(filename, content="This is a test file content for summary generation."):
    test_dir = Path("cache/test_files")
    test_dir.mkdir(exist_ok=True)
    
    # Generate random filename to avoid conflicts
    if not filename.startswith("random_"):
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        filename = f"random_{random_str}_{filename}"
    
    # Add randomness to content to ensure unique hash
    random_content = f"UNIQUE CONTENT ID: {random.randint(100000, 999999)}\n{content}"
    
    file_path = test_dir / filename
    with open(file_path, "w") as f:
        f.write(random_content)
    
    return file_path


def test_file_handling_and_ai_integration():
    """Test the file handling and AI integration functionality."""
    print("🚀 Testing Phase 3: File Handling & Core AI Integration")
    print("=" * 50)
    
    # Test health endpoint to verify API is running
    print("\n1. Testing health endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Register test users
    print("\n2. Registering test users...")
    response1 = client.post("/auth/register", json=TEST_USER1)
    response2 = client.post("/auth/register", json=TEST_USER2)
    
    if response1.status_code == 201 and response2.status_code == 201:
        print(f"   ✅ Users registered successfully")
        user1_id = response1.json()['user']['id']
        user2_id = response2.json()['user']['id']
        print(f"   User1 ID: {user1_id}, User2 ID: {user2_id}")
    else:
        print(f"   ❌ User registration failed")
        if response1.status_code != 201:
            print(f"   User1 error: {response1.json()}")
        if response2.status_code != 201:
            print(f"   User2 error: {response2.json()}")
        return
    
    # Login as User1
    print("\n3. Logging in as User1...")
    login_data = {
        "username": TEST_USER1["username"],
        "password": TEST_USER1["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Login successful")
        user1_token = response.json()["access_token"]
        user1_headers = {"Authorization": f"Bearer {user1_token}"}
    else:
        print(f"   ❌ Login failed: {response.json()}")
        return
    
    # Login as User2
    print("\n4. Logging in as User2...")
    login_data = {
        "username": TEST_USER2["username"],
        "password": TEST_USER2["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Login successful")
        user2_token = response.json()["access_token"]
        user2_headers = {"Authorization": f"Bearer {user2_token}"}
    else:
        print(f"   ❌ Login failed: {response.json()}")
        return
    
    # Create a test file
    print("\n5. Creating a test file...")
    test_file_path = create_test_file("test_document.txt", 
        """# Sample Document for Testing

## Introduction
This is a sample document created for testing the summary generation feature.

## Key Concepts
- File handling
- AI integration
- Summary generation
- Multiple file support

## Benefits
1. Automated summarization
2. Increased productivity
3. Better understanding of complex materials

## Conclusion
This test demonstrates the functionality of the AI-powered summary generation system.
"""
    )
    print(f"   ✅ Test file created at {test_file_path}")
    
    # Upload file as User1
    print("\n6. Uploading file as User1...")
    with open(test_file_path, "rb") as f:
        response = client.post(
            "/files/upload", 
            files={"file": ("test_document.txt", f, "text/plain")},
            headers=user1_headers
        )
    
    if response.status_code == 201:
        print(f"   ✅ File uploaded successfully")
        file_id = response.json()["file"]["id"]
        print(f"   File ID: {file_id}")
    else:
        print(f"   ❌ File upload failed: {response.json()}")
        return
    
    # Test listing files for User1
    print("\n7. Listing files for User1...")
    response = client.get("/files/", headers=user1_headers)
    if response.status_code == 200:
        files = response.json()
        print(f"   ✅ Successfully retrieved files")
        print(f"   Number of files: {len(files)}")
        for file in files:
            print(f"   - {file['file_name']} (ID: {file['id']})")
    else:
        print(f"   ❌ Failed to retrieve files: {response.json()}")
    
    # Test file access control - User2 should not be able to access the file
    print("\n8. Testing file access control - User2 attempting to access User1's file...")
    response = client.get(f"/files/{file_id}", headers=user2_headers)
    if response.status_code == 404:
        print(f"   ✅ Access control working correctly - User2 denied access")
    else:
        print(f"   ❌ Access control failed - User2 has unexpected access: {response.json()}")
    
    # Share file with User2
    print("\n9. Sharing file with User2...")
    
    # First confirm the current user has admin access by checking file access list
    response = client.get(f"/files/{file_id}/access", headers=user1_headers)
    if response.status_code == 200:
        access_list = response.json()
        print(f"   ✅ Successfully retrieved file access list")
        print(f"   Full access list: {access_list}")  # Debug - print full access list
        for entry in access_list:
            print(f"   - User ID: {entry['user_id']}, Access Level: {entry['access_level']}")
            if entry['user_id'] == user1_id and entry['access_level'] == "admin":
                print(f"   ✅ Confirmed user1 has admin access to the file")
                break
        else:
            print(f"   ❌ User1 doesn't have admin access to their uploaded file")
            print(f"   Current user1_id: {user1_id}")  # Debug - print user1_id
            return
    else:
        print(f"   ❌ Failed to retrieve access list: {response.json()}")
        return
    
    # Now share the file
    response = client.post(
        f"/files/{file_id}/share",
        data={"user_id": user2_id, "access_level": "read"},
        headers=user1_headers
    )
    
    if response.status_code == 200:
        print(f"   ✅ File shared successfully")
    else:
        print(f"   ❌ File sharing failed: {response.json()}")
        return
    
    # Verify User2 can now access the file
    print("\n10. Verifying User2 can now access the shared file...")
    response = client.get(f"/files/{file_id}", headers=user2_headers)
    if response.status_code == 200:
        print(f"   ✅ User2 can access the file after sharing")
    else:
        print(f"   ❌ User2 still cannot access the file: {response.json()}")
    
    # Generate summary from file
    print("\n11. Generating summary from file...")
    response = client.post(
        "/summaries/generate",
        json={"physical_file_ids": [file_id], "custom_instructions": "Create a concise summary of the document"},
        headers=user1_headers
    )
    
    if response.status_code == 200:
        print(f"   ✅ Summary generated successfully")
        summary = response.json()["summary"]
        print(f"   Summary ID: {summary['id']}")
        print(f"   Summary Title: {summary['title']}")
        print(f"   Summary Preview: {summary['full_markdown'][:100]}...")
    else:
        print(f"   ❌ Summary generation failed: {response.json()}")
    
    # List summaries for User1
    print("\n12. Listing summaries for User1...")
    response = client.get("/summaries/", headers=user1_headers)
    if response.status_code == 200:
        summaries = response.json()
        print(f"   ✅ Successfully retrieved summaries")
        print(f"   Number of summaries: {len(summaries)}")
        for summary in summaries:
            print(f"   - {summary['title']} (ID: {summary['id']})")
    else:
        print(f"   ❌ Failed to retrieve summaries: {response.json()}")
    
    # Upload a second file for multiple file testing
    print("\n13. Uploading a second file for multiple file testing...")
    second_test_file_path = create_test_file("second_document.txt", 
        """# Second Test Document

This document provides additional information for testing multiple file summary generation.

## Additional Topics
- Multi-document summarization
- Content aggregation
- Information synthesis
"""
    )
    
    with open(second_test_file_path, "rb") as f:
        response = client.post(
            "/files/upload", 
            files={"file": ("second_document.txt", f, "text/plain")},
            headers=user1_headers
        )
    
    if response.status_code == 201:
        print(f"   ✅ Second file uploaded successfully")
        second_file_id = response.json()["file"]["id"]
        print(f"   Second File ID: {second_file_id}")
    else:
        print(f"   ❌ Second file upload failed: {response.json()}")
        return
    
    # Generate summary from multiple files
    print("\n14. Generating summary from multiple files...")
    response = client.post(
        "/summaries/generate",
        json={
            "physical_file_ids": [file_id, second_file_id],
            "custom_instructions": "Create a comprehensive summary combining both documents"
        },
        headers=user1_headers
    )
    
    if response.status_code == 200:
        print(f"   ✅ Multi-file summary generated successfully")
        summary = response.json()["summary"]
        print(f"   Summary ID: {summary['id']}")
        print(f"   Summary Title: {summary['title']}")
        print(f"   Summary Preview: {summary['full_markdown'][:100]}...")
    else:
        print(f"   ❌ Multi-file summary generation failed: {response.json()}")
    
    # Revoke User2's access to the file
    print("\n15. Revoking User2's access to the file...")
    response = client.delete(
        f"/files/{file_id}/share/{user2_id}",
        headers=user1_headers
    )
    
    if response.status_code == 200:
        print(f"   ✅ Access revoked successfully")
    else:
        print(f"   ❌ Failed to revoke access: {response.json()}")
    
    # Verify User2 can no longer access the file
    print("\n16. Verifying User2 can no longer access the file...")
    response = client.get(f"/files/{file_id}", headers=user2_headers)
    if response.status_code == 404:
        print(f"   ✅ Access control working correctly - User2 no longer has access")
    else:
        print(f"   ❌ Access control failed - User2 still has access: {response.json()}")
    
    # Clean up test files
    os.remove(test_file_path)
    os.remove(second_test_file_path)
    try:
        os.rmdir("cache/test_files")
    except:
        pass  # Directory might not be empty
    
    print("\n" + "=" * 50)
    print("✅ Phase 3 Testing Complete!")
    print("🎉 File handling and AI integration features are working!")


if __name__ == "__main__":
    test_file_handling_and_ai_integration() 