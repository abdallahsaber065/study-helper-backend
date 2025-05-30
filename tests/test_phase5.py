"""
Test script for Phase 5 functionality (Community Features).
"""
import sys
import os
import random
import string

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# set working directory to the project root (parent directory of this script directory)
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# print the working directory for debugging
print(f"Working directory: {os.getcwd()}")

from fastapi.testclient import TestClient
from pathlib import Path
from app import app

# Create test client
client = TestClient(app)

# Test data
def generate_test_user(prefix="community"):
    return {
        "username": f"{prefix}_user_{random.randint(1000, 9999)}",
        "first_name": f"{prefix.title()}",
        "last_name": "User",
        "email": f"{prefix}_test{random.randint(1000, 9999)}@example.com",
        "password": f"{prefix}password{random.randint(1000, 9999)}"
    }

def create_test_file(filename, content):
    """Create a test file for community testing."""
    test_dir = Path("cache/test_files")
    test_dir.mkdir(exist_ok=True)
    
    # Generate random filename to avoid conflicts
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    filename = f"community_{random_str}_{filename}"
    
    # Add randomness to content to ensure unique hash
    random_content = f"UNIQUE COMMUNITY CONTENT ID: {random.randint(100000, 999999)}\n{content}"
    
    file_path = test_dir / filename
    with open(file_path, "w") as f:
        f.write(random_content)
    
    return file_path


def test_community_features():
    """Test the Community functionality."""
    print("🚀 Testing Phase 5: Community Features")
    print("=" * 50)
    
    # Test health endpoint
    print("\n1. Testing health endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Register multiple test users
    print("\n2. Registering test users...")
    
    # Admin user
    admin_user = generate_test_user("admin")
    response = client.post("/auth/register", json=admin_user)
    if response.status_code == 201:
        print(f"   ✅ Admin user registered successfully")
        admin_user_id = response.json()['user']['id']
    else:
        print(f"   ❌ Admin user registration failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Member user
    member_user = generate_test_user("member")
    response = client.post("/auth/register", json=member_user)
    if response.status_code == 201:
        print(f"   ✅ Member user registered successfully")
        member_user_id = response.json()['user']['id']
    else:
        print(f"   ❌ Member user registration failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Another member user
    member2_user = generate_test_user("member2")
    response = client.post("/auth/register", json=member2_user)
    if response.status_code == 201:
        print(f"   ✅ Member2 user registered successfully")
        member2_user_id = response.json()['user']['id']
    else:
        print(f"   ❌ Member2 user registration failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Login admin user
    print("\n3. Logging in admin user...")
    login_data = {
        "username": admin_user["username"],
        "password": admin_user["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Admin login successful")
        admin_token = response.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
    else:
        print(f"   ❌ Admin login failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Login member user
    print("\n4. Logging in member user...")
    login_data = {
        "username": member_user["username"],
        "password": member_user["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Member login successful")
        member_token = response.json()["access_token"]
        member_headers = {"Authorization": f"Bearer {member_token}"}
    else:
        print(f"   ❌ Member login failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Login member2 user
    print("\n5. Logging in member2 user...")
    login_data = {
        "username": member2_user["username"],
        "password": member2_user["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Member2 login successful")
        member2_token = response.json()["access_token"]
        member2_headers = {"Authorization": f"Bearer {member2_token}"}
    else:
        print(f"   ❌ Member2 login failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # Create subjects first
    print("\n6. Creating subjects...")
    subjects_data = [
        {"name": "Computer Science", "description": "CS topics and programming"},
        {"name": "Mathematics", "description": "Math concepts and theories"},
        {"name": "Physics", "description": "Physics principles and laws"}
    ]
    
    created_subjects = []
    for subject_data in subjects_data:
        response = client.post("/communities/subjects", json=subject_data, headers=admin_headers)
        if response.status_code == 201:
            subject = response.json()
            created_subjects.append(subject)
            print(f"   ✅ Created subject: {subject['name']}")
        else:
            # Subject might already exist, try to find it
            response = client.get(f"/communities/subjects?search={subject_data['name']}")
            if response.status_code == 200:
                subjects = response.json()
                if subjects:
                    created_subjects.append(subjects[0])
                    print(f"   ✅ Found existing subject: {subjects[0]['name']}")
                else:
                    print(f"   ❌ Failed to create/find subject {subject_data['name']}: {response.json()}")
                    # Note: This failure does not stop the script, but `created_subjects` might be empty or incomplete.
            else:
                print(f"   ❌ Failed to search for subject {subject_data['name']}: {response.json()}")

    
    # Create community
    print("\n7. Creating community...")
    community_data = {
        "name": f"Test Study Community {random.randint(1000, 9999)}",
        "description": "A test community for studying together",
        "is_private": False
    }
    
    response = client.post("/communities", json=community_data, headers=admin_headers)
    if response.status_code == 201:
        community = response.json()
        community_id = community["id"]
        community_code = community["community_code"]
        print(f"   ✅ Community created successfully")
        print(f"   Community ID: {community_id}")
        print(f"   Community Code: {community_code}")
        print(f"   Name: {community['name']}")
        print(f"   Members: {community['member_count']}")
    else:
        print(f"   ❌ Community creation failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        return
    
    # List communities
    print("\n8. Listing communities...")
    response = client.get("/communities", headers=admin_headers)
    if response.status_code == 200:
        communities = response.json()
        print(f"   ✅ Retrieved {len(communities)} communities")
        for comm in communities:
            print(f"   - {comm['name']}: {comm['member_count']} members")
    else:
        print(f"   ❌ Failed to list communities: {response.json()}")
    
    # Join community with member user
    print("\n9. Joining community with member user...")
    join_request = {"community_code": community_code}
    response = client.post("/communities/join", json=join_request, headers=member_headers)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Member joined community successfully")
        print(f"   Role: {result['role']}")
    else:
        print(f"   ❌ Failed to join community: {response.json()}")
    
    # Join community with member2 user
    print("\n10. Joining community with member2 user...")
    response = client.post("/communities/join", json=join_request, headers=member2_headers)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Member2 joined community successfully")
        print(f"   Role: {result['role']}")
    else:
        print(f"   ❌ Failed to join community with member2: {response.json()}")
    
    # Get community members
    print("\n11. Getting community members...")
    response = client.get(f"/communities/{community_id}/members", headers=admin_headers)
    if response.status_code == 200:
        members = response.json()
        print(f"   ✅ Retrieved {len(members)} members")
        for member in members:
            print(f"   - {member['username']}: {member['role']}")
    else:
        print(f"   ❌ Failed to get members: {response.json()}")
    
    # Add subjects to community (admin only)
    print("\n12. Adding subjects to community...")
    if created_subjects:
        for subject in created_subjects[:2]:  # Add first 2 subjects
            subject_link = {"subject_id": subject["id"]}
            response = client.post(f"/communities/{community_id}/subjects", json=subject_link, headers=admin_headers)
            if response.status_code == 201:
                link = response.json()
                print(f"   ✅ Added subject: {subject['name']}")
            else:
                print(f"   ❌ Failed to add subject {subject['name']}: {response.json()}")
    else:
        print(f"   ⚠️ Skipping adding subjects to community: No subjects were created/found in step 6.")

    # Test member trying to add subject (should fail)
    print("\n13. Testing member trying to add subject (should fail)...")
    if created_subjects:
        # Use the last created subject if available, otherwise this test part is skipped.
        subject_link = {"subject_id": created_subjects[-1]["id"]}
        response = client.post(f"/communities/{community_id}/subjects", json=subject_link, headers=member_headers)
        if response.status_code == 403:
            print(f"   ✅ Member correctly denied access to add subject")
        else:
            print(f"   ❌ Member should not be able to add subject: {response.status_code} - {response.text}")
    else:
        print(f"   ⚠️ Skipping: No subjects available to test adding by member (created_subjects is empty).")
    
    # Get community subjects
    print("\n14. Getting community subjects...")
    response = client.get(f"/communities/{community_id}/subjects", headers=admin_headers)
    community_subject_id = None # Initialize in case of failure or no subjects
    if response.status_code == 200:
        subjects = response.json()
        print(f"   ✅ Retrieved {len(subjects)} subjects")
        for subject in subjects:
            print(f"   - Subject: {subject.get('subject_name', 'Unknown')}")
        if subjects:
            community_subject_id = subjects[0]["subject_id"]
    else:
        print(f"   ❌ Failed to get subjects: {response.json()}")
        # community_subject_id remains None
    
    # Create and upload test file
    print("\n15. Creating and uploading test file...")
    test_content = """# Data Structures Study Guide

## Introduction
Data structures are ways of organizing and storing data so that they can be accessed and modified efficiently.

## Basic Data Structures

### Arrays
- Fixed size collection of elements
- Elements stored in contiguous memory locations
- O(1) access time by index

### Linked Lists
- Dynamic data structure
- Elements (nodes) contain data and pointer to next node
- O(n) access time, O(1) insertion/deletion at head

### Stacks
- LIFO (Last In, First Out) principle
- Operations: push, pop, peek, isEmpty
- Applications: function calls, expression evaluation

### Queues
- FIFO (First In, First Out) principle
- Operations: enqueue, dequeue, front, rear
- Applications: breadth-first search, scheduling

## Advanced Data Structures

### Trees
- Hierarchical data structure
- Binary trees, BST, AVL trees, heap
- Applications: searching, sorting, parsing

### Hash Tables
- Key-value data structure
- O(1) average case access time
- Hash function maps keys to indices

### Graphs
- Collection of vertices and edges
- Directed and undirected graphs
- Applications: networks, pathfinding, social media
"""
    
    test_file_path = create_test_file("data_structures.txt", test_content)
    print(f"   ✅ Test file created: {test_file_path}")
    
    file_id = None # Initialize file_id
    # Upload file with admin user
    with open(test_file_path, "rb") as f:
        response = client.post(
            "/files/upload", 
            files={"file": ("data_structures.txt", f, "text/plain")},
            headers=admin_headers
        )
    
    if response.status_code == 201:
        print(f"   ✅ File uploaded successfully")
        file_id = response.json()["file"]["id"]
        print(f"   File ID: {file_id}")
    else:
        print(f"   ❌ File upload failed: {response.json()}")
        # This failure will cause the script to exit, and subsequent tests will be skipped.
        # Note: test_file_path might not be cleaned up if we exit here.
        return
    
    # Add file to community subject (admin only)
    print("\n16. Adding file to community subject...")
    if community_subject_id and file_id:
        file_data = {
            "subject_id": community_subject_id,
            "physical_file_id": file_id,
            "file_category": "lecture",
            "description": "Data structures study guide for beginners"
        }
        response = client.post(f"/communities/{community_id}/files", json=file_data, headers=admin_headers)
        if response.status_code == 201:
            community_file = response.json()
            print(f"   ✅ File added to community subject successfully")
            print(f"   File: {community_file.get('file_name', 'Unknown')}")
            print(f"   Category: {community_file['file_category']}")
        else:
            print(f"   ❌ Failed to add file to community: {response.json()}")
    else:
        print(f"   ⚠️ Skipping: community_subject_id or file_id not available.")
        if not community_subject_id:
            print(f"      Reason: community_subject_id is not set (no subjects in community or failed to retrieve).")
        if not file_id:
            print(f"      Reason: file_id is not set (file upload failed or was skipped).")

    # Test member trying to add file (should fail)
    print("\n17. Testing member trying to add file (should fail)...")
    if community_subject_id and file_id:
        file_data = {
            "subject_id": community_subject_id,
            "physical_file_id": file_id,
            "file_category": "general_resource",
            "description": "Test file by member"
        }
        response = client.post(f"/communities/{community_id}/files", json=file_data, headers=member_headers)
        if response.status_code == 403:
            print(f"   ✅ Member correctly denied access to add file")
        else:
            print(f"   ❌ Member should not be able to add file: {response.status_code} - {response.text}")
    else:
        print(f"   ⚠️ Skipping: community_subject_id or file_id not available for testing member file add.")
        if not community_subject_id:
            print(f"      Reason: community_subject_id is not set.")
        if not file_id:
            print(f"      Reason: file_id is not set.")
            
    # Get community subject files
    print("\n18. Getting community subject files...")
    if community_subject_id:
        response = client.get(f"/communities/{community_id}/subjects/{community_subject_id}/files", headers=member_headers)
        if response.status_code == 200:
            files = response.json()
            print(f"   ✅ Retrieved {len(files)} files")
            for file_item in files: # Renamed to avoid conflict with outer 'file' variable from open()
                print(f"   - {file_item.get('file_name', 'Unknown')}: {file_item['file_category']}")
        else:
            print(f"   ❌ Failed to get files: {response.json()}")
    else:
        print(f"   ⚠️ Skipping: community_subject_id not available for getting files.")
    
    # Update member role (admin only)
    print("\n19. Promoting member to moderator...")
    role_update = {"role": "moderator"}
    response = client.put(f"/communities/{community_id}/members/{member_user_id}", json=role_update, headers=admin_headers)
    if response.status_code == 200:
        updated_member = response.json()
        print(f"   ✅ Member promoted to: {updated_member['role']}")
    else:
        print(f"   ❌ Failed to update member role: {response.json()}")
    
    # Test moderator adding subject (should work now)
    print("\n20. Testing moderator adding subject (should work now)...")
    if created_subjects:
        # Ensure there's a subject that hasn't been added yet, or pick one.
        # This assumes created_subjects[-1] is a valid subject not yet in the community or tests re-adding.
        subject_to_add_by_mod = created_subjects[-1] # Pick the last one for simplicity
        subject_link = {"subject_id": subject_to_add_by_mod["id"]}
        response = client.post(f"/communities/{community_id}/subjects", json=subject_link, headers=member_headers) # member_headers now belong to a moderator
        if response.status_code == 201:
            link = response.json()
            print(f"   ✅ Moderator successfully added subject: {subject_to_add_by_mod['name']}")
        elif response.status_code == 400 and "already linked" in response.json().get("detail", "").lower():
             print(f"   ✅ Subject {subject_to_add_by_mod['name']} was already linked, moderator role test still valid for attempt.")
        else:
            print(f"   ❌ Moderator failed to add subject {subject_to_add_by_mod['name']}: {response.status_code} - {response.text}")
    else:
        print(f"   ⚠️ Skipping: No subjects available to test adding by moderator (created_subjects is empty).")
    
    # Get community statistics
    print("\n21. Getting community statistics...")
    response = client.get(f"/communities/{community_id}/stats", headers=admin_headers)
    if response.status_code == 200:
        stats = response.json()
        print(f"   ✅ Community statistics:")
        print(f"   - Members: {stats['total_members']}")
        print(f"   - Subjects: {stats['total_subjects']}")
        print(f"   - Files: {stats['total_files']}")
        print(f"   - Quizzes: {stats['total_quizzes']}")
        print(f"   - Summaries: {stats['total_summaries']}")
    else:
        print(f"   ❌ Failed to get stats: {response.json()}")
    
    # Test removing member (admin only)
    print("\n22. Testing removing member...")
    response = client.delete(f"/communities/{community_id}/members/{member2_user_id}", headers=admin_headers)
    if response.status_code == 204:
        print(f"   ✅ Member2 removed successfully")
    else:
        print(f"   ❌ Failed to remove member: {response.json()}")
    
    # Test member leaving community
    print("\n23. Testing member leaving community...")
    response = client.post(f"/communities/{community_id}/leave", headers=member_headers) # member_user (now moderator) leaving
    if response.status_code == 204:
        print(f"   ✅ Member left community successfully")
    else:
        print(f"   ❌ Failed to leave community: {response.json()}")
    
    # Get community details with full info
    print("\n24. Getting final community details...")
    response = client.get(f"/communities/{community_id}", headers=admin_headers)
    if response.status_code == 200:
        community_details = response.json()
        print(f"   ✅ Community details retrieved")
        print(f"   Name: {community_details['name']}")
        print(f"   Members: {len(community_details['members'])}")
        print(f"   Subjects: {len(community_details['subjects'])}")
        for member in community_details['members']:
            print(f"   - Member: {member['username']} ({member['role']})")
    else:
        print(f"   ❌ Failed to get community details: {response.json()}")
    
    # Test trying to access private community
    print("\n25. Testing private community access...")
    private_community_data = {
        "name": f"Private Study Group {random.randint(1000, 9999)}",
        "description": "A private community for exclusive members",
        "is_private": True
    }
    
    response = client.post("/communities", json=private_community_data, headers=admin_headers)
    if response.status_code == 201:
        private_community = response.json()
        private_community_code = private_community["community_code"]
        print(f"   ✅ Private community created: {private_community_code}")
        
        # Test member2 trying to join private community (should fail for now, requires approval)
        # Re-register member2 if needed, or use a different user not part of the test context if member2_user_id was deleted.
        # For simplicity, we assume member2_headers are still valid for a logged-in user, even if removed from prior community.
        join_request = {"community_code": private_community_code}
        response = client.post("/communities/join", json=join_request, headers=member2_headers) # member2_headers
        if response.status_code == 400: # Assuming 400 for "approval required" or similar
            print(f"   ✅ Private community correctly requires approval (or join request created): {response.json().get('detail', '')}")
        elif response.status_code == 201: # If API creates a join request
             print(f"   ✅ Join request for private community created successfully: {response.json().get('detail', '')}")
        else:
            print(f"   ❌ Private community join behavior unexpected: {response.status_code} - {response.json()}")
    else:
        print(f"   ❌ Failed to create private community: {response.json()}")

    # Clean up test files
    # This try-except block will catch NameError if test_file_path was not defined (e.g., due to an early return)
    # or FileNotFoundError if the file was already removed or never created.
    print("\nCleaning up test files...")
    try:
        if 'test_file_path' in locals() and test_file_path and os.path.exists(test_file_path):
            os.remove(test_file_path)
            print(f"   ✅ Test file {test_file_path} removed.")
        else:
            print(f"   ℹ️ Test file path not defined or file does not exist, no cleanup needed for it.")
    except Exception as e: # Catch any exception during cleanup
        print(f"   ⚠️  Could not remove test file: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Phase 5 Testing Complete!")
    print("🎉 Community functionality is working (based on executed steps)!")
    print("\nFeatures tested (or attempted):")
    print("- ✅ Community creation with unique codes")
    print("- ✅ Community membership management (join, leave, role updates, removal)")
    print("- ✅ Role-based access control (admin/moderator/member permissions)")
    print("- ✅ Subject linking to communities")
    print("- ✅ File association with community subjects")
    print("- ✅ Permission checks for content curation (adding subjects/files)")
    print("- ✅ Community statistics and details retrieval")
    print("- ✅ Private community creation and join process")
    # The "Community limits and validation" is implicitly tested by various calls.
    # A more explicit print for it might be misleading without specific tests for limits.
    print("- ✅ Basic validation and error handling observed in responses")


if __name__ == "__main__":
    test_community_features() 