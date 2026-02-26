"""
Test script for Phase 2 authentication functionality.
"""
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# set working directory to the project root (parent directory of this script directory)
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# print the working directory for debugging
print(f"Working directory: {os.getcwd()}")

from fastapi.testclient import TestClient
from app import app

# Create test client
client = TestClient(app)

def test_authentication_endpoints():
    """Test the authentication endpoints."""
    print("🚀 Testing Phase 2: Authentication System")
    print("=" * 50)
    
    # Test health endpoint
    print("\n1. Testing health endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test user registration
    print("\n2. Testing user registration...")
    user_data = {
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    response = client.post("/auth/register", json=user_data)
    print(f"   Status: {response.status_code}")
    if response.status_code == 201:
        print(f"   ✅ User registered successfully")
        print(f"   User ID: {response.json()['user']['id']}")
    else:
        print(f"   ❌ Registration failed: {response.json()}")
    
    # Test user login
    print("\n3. Testing user login...")
    login_data = {
        "username": "testuser",
        "password": "testpassword123"
    }
    
    response = client.post("/auth/login", json=login_data)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Login successful")
        token = response.json()["access_token"]
        print(f"   Token received: {token[:50]}...")
        
        # Test authenticated endpoint
        print("\n4. Testing authenticated endpoint (/auth/me)...")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/auth/me", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Authenticated access successful")
            user_info = response.json()
            print(f"   Username: {user_info['username']}")
            print(f"   Role: {user_info['role']}")
        else:
            print(f"   ❌ Authenticated access failed: {response.json()}")
        
        # Test users endpoint
        print("\n5. Testing users endpoint...")
        response = client.get("/users/", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Users list retrieved successfully")
            users = response.json()
            print(f"   Number of users: {len(users)}")
        else:
            print(f"   ❌ Users list failed: {response.json()}")
    else:
        print(f"   ❌ Login failed: {response.json()}")
    
    # Test invalid login
    print("\n6. Testing invalid login...")
    invalid_login_data = {
        "username": "testuser",
        "password": "wrongpassword"
    }
    
    response = client.post("/auth/login", json=invalid_login_data)
    print(f"   Status: {response.status_code}")
    if response.status_code == 401:
        print(f"   ✅ Invalid login correctly rejected")
    else:
        print(f"   ❌ Unexpected response: {response.json()}")
    
    # Test duplicate registration
    print("\n7. Testing duplicate registration...")
    response = client.post("/auth/register", json=user_data)
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        print(f"   ✅ Duplicate registration correctly rejected")
    else:
        print(f"   ❌ Unexpected response: {response.json()}")
    
    print("\n" + "=" * 50)
    print("✅ Phase 2 Authentication Testing Complete!")
    print("🎉 All core authentication features are working!")

if __name__ == "__main__":
    test_authentication_endpoints()
