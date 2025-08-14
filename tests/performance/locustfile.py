"""Locust load testing configuration for Study Assistant API."""

import json
import random
import string
from typing import Dict, Any

from locust import HttpUser, task, between, events


class StudyAssistantUser(HttpUser):
    """Simulated user for load testing Study Assistant API."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_token = None
        self.user_id = None
        self.files = []  # Store uploaded file IDs
        self.summaries = []  # Store created summary IDs
        self.quizzes = []  # Store created quiz IDs
    
    def on_start(self):
        """Called when a user starts. Register and login."""
        self.register_and_login()
    
    def on_stop(self):
        """Called when a user stops. Cleanup if needed."""
        if self.access_token:
            self.logout()
    
    def register_and_login(self) -> bool:
        """Register a new user and login."""
        # Generate unique user credentials
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        email = f"loadtest_{unique_id}@example.com"
        password = "LoadTest123!"
        
        # Register user
        register_data = {
            "email": email,
            "password": password
        }
        
        with self.client.post("/auth/register", 
                            json=register_data, 
                            name="auth_register",
                            catch_response=True) as response:
            if response.status_code == 201:
                response.success()
                self.user_id = response.json().get("id")
            else:
                response.failure(f"Registration failed: {response.status_code}")
                return False
        
        # Login to get access token
        login_data = {
            "username": email,
            "password": password
        }
        
        with self.client.post("/auth/token", 
                            data=login_data,
                            name="auth_login",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                token_data = response.json()
                self.access_token = token_data["access_token"]
                return True
            else:
                response.failure(f"Login failed: {response.status_code}")
                return False
    
    def logout(self):
        """Logout current user."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.post("/auth/logout", 
                            headers=headers,
                            name="auth_logout",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Logout failed: {response.status_code}")
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}
    
    @task(5)
    def get_user_profile(self):
        """Get current user profile."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/users/me", 
                           headers=headers,
                           name="users_me",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get profile failed: {response.status_code}")
    
    @task(3)
    def upload_file(self):
        """Upload a test file."""
        if not self.access_token:
            return
        
        # Create test file content
        file_content = "This is a test document for load testing. " * 50
        file_name = f"loadtest_doc_{random.randint(1000, 9999)}.txt"
        
        headers = self.get_auth_headers()
        files = {
            "file": (file_name, file_content, "text/plain")
        }
        
        with self.client.post("/files/upload",
                            headers=headers,
                            files=files,
                            name="files_upload",
                            catch_response=True) as response:
            if response.status_code == 201:
                response.success()
                file_data = response.json()
                self.files.append(file_data["id"])
            else:
                response.failure(f"File upload failed: {response.status_code}")
    
    @task(4)
    def list_files(self):
        """List user files."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/files/",
                           headers=headers,
                           name="files_list",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List files failed: {response.status_code}")
    
    @task(2)
    def generate_summary(self):
        """Generate summary for a random file."""
        if not self.access_token or not self.files:
            return
        
        file_id = random.choice(self.files)
        headers = self.get_auth_headers()
        
        summary_data = {
            "file_id": file_id,
            "title": f"Load Test Summary {random.randint(1, 1000)}",
            "ai_model": "gpt-3.5-turbo",
            "max_length": 500
        }
        
        with self.client.post("/summaries/generate",
                            headers=headers,
                            json=summary_data,
                            name="summaries_generate",
                            catch_response=True) as response:
            if response.status_code in [200, 202]:  # 202 for async processing
                response.success()
                if response.status_code == 200:
                    summary_data = response.json()
                    self.summaries.append(summary_data["id"])
            else:
                response.failure(f"Generate summary failed: {response.status_code}")
    
    @task(2)
    def generate_quiz(self):
        """Generate quiz for a random file."""
        if not self.access_token or not self.files:
            return
        
        file_id = random.choice(self.files)
        headers = self.get_auth_headers()
        
        quiz_data = {
            "file_id": file_id,
            "title": f"Load Test Quiz {random.randint(1, 1000)}",
            "question_count": 5,
            "difficulty": random.choice(["easy", "medium", "hard"]),
            "question_types": ["multiple_choice", "true_false"]
        }
        
        with self.client.post("/quizzes/generate",
                            headers=headers,
                            json=quiz_data,
                            name="quizzes_generate",
                            catch_response=True) as response:
            if response.status_code in [200, 202]:  # 202 for async processing
                response.success()
                if response.status_code == 200:
                    quiz_data = response.json()
                    self.quizzes.append(quiz_data["id"])
            else:
                response.failure(f"Generate quiz failed: {response.status_code}")
    
    @task(3)
    def list_summaries(self):
        """List user summaries."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/summaries/",
                           headers=headers,
                           name="summaries_list",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List summaries failed: {response.status_code}")
    
    @task(3)
    def list_quizzes(self):
        """List user quizzes."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/quizzes/",
                           headers=headers,
                           name="quizzes_list",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List quizzes failed: {response.status_code}")
    
    @task(1)
    def get_summary_detail(self):
        """Get detailed view of a random summary."""
        if not self.access_token or not self.summaries:
            return
        
        summary_id = random.choice(self.summaries)
        headers = self.get_auth_headers()
        
        with self.client.get(f"/summaries/{summary_id}",
                           headers=headers,
                           name="summaries_detail",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get summary detail failed: {response.status_code}")
    
    @task(1)
    def get_quiz_detail(self):
        """Get detailed view of a random quiz."""
        if not self.access_token or not self.quizzes:
            return
        
        quiz_id = random.choice(self.quizzes)
        headers = self.get_auth_headers()
        
        with self.client.get(f"/quizzes/{quiz_id}",
                           headers=headers,
                           name="quizzes_detail",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get quiz detail failed: {response.status_code}")
    
    @task(1)
    def check_health(self):
        """Check API health endpoint."""
        with self.client.get("/health",
                           name="health_check",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(1)
    def get_usage_stats(self):
        """Get usage statistics."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/usage/stats",
                           headers=headers,
                           name="usage_stats",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get usage stats failed: {response.status_code}")


class AdminUser(HttpUser):
    """Simulated admin user for testing admin endpoints."""
    
    weight = 1  # Lower weight than regular users
    wait_time = between(2, 5)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_token = None
    
    def on_start(self):
        """Login as admin user."""
        self.login_admin()
    
    def login_admin(self):
        """Login with admin credentials."""
        # Note: In real testing, use proper admin credentials
        admin_data = {
            "username": "admin@example.com",
            "password": "AdminPassword123!"
        }
        
        with self.client.post("/auth/token",
                            data=admin_data,
                            name="admin_login",
                            catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                token_data = response.json()
                self.access_token = token_data["access_token"]
            else:
                response.failure(f"Admin login failed: {response.status_code}")
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}
    
    @task(3)
    def get_all_users(self):
        """Get list of all users (admin only)."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/users/",
                           headers=headers,
                           name="admin_users_list",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get all users failed: {response.status_code}")
    
    @task(2)
    def get_system_stats(self):
        """Get system-wide statistics."""
        if not self.access_token:
            return
        
        headers = self.get_auth_headers()
        with self.client.get("/usage/system-stats",
                           headers=headers,
                           name="admin_system_stats",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get system stats failed: {response.status_code}")
    
    @task(1)
    def detailed_health_check(self):
        """Perform detailed health check."""
        headers = self.get_auth_headers()
        with self.client.get("/health/detailed",
                           headers=headers,
                           name="admin_health_detailed",
                           catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Detailed health check failed: {response.status_code}")


# Custom event handlers for metrics
@events.request_success.add_listener
def on_request_success(request_type, name, response_time, response_length, **kwargs):
    """Custom success handler."""
    pass


@events.request_failure.add_listener
def on_request_failure(request_type, name, response_time, response_length, exception, **kwargs):
    """Custom failure handler."""
    pass


# Test scenarios
class BrowsingUser(StudyAssistantUser):
    """User that mainly browses content."""
    
    weight = 3
    
    @task(10)
    def browse_content(self):
        """Browse various content."""
        self.list_files()
        self.list_summaries()
        self.list_quizzes()
    
    @task(1)
    def upload_occasionally(self):
        """Upload files occasionally."""
        self.upload_file()


class PowerUser(StudyAssistantUser):
    """User that actively creates content."""
    
    weight = 2
    
    @task(5)
    def create_content(self):
        """Actively create summaries and quizzes."""
        if random.choice([True, False]):
            self.generate_summary()
        else:
            self.generate_quiz()
    
    @task(3)
    def upload_frequently(self):
        """Upload files frequently."""
        self.upload_file()
    
    @task(2)
    def manage_content(self):
        """Manage existing content."""
        self.get_summary_detail()
        self.get_quiz_detail()
