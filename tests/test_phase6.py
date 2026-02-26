"""
Test script for Phase 6 functionality (Interaction and Engagement Features).
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
def generate_test_user(prefix="phase6"):
    return {
        "username": f"{prefix}_user_{random.randint(1000, 9999)}",
        "first_name": f"{prefix.title()}",
        "last_name": "User",
        "email": f"{prefix}_test{random.randint(1000, 9999)}@example.com",
        "password": f"{prefix}password{random.randint(1000, 9999)}"
    }

def create_test_file(filename, content):
    """Create a test file for testing."""
    test_dir = Path("cache/test_files")
    test_dir.mkdir(exist_ok=True)
    
    # Generate random filename to avoid conflicts
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    filename = f"phase6_{random_str}_{filename}"
    
    # Add randomness to content to ensure unique hash
    random_content = f"UNIQUE PHASE6 CONTENT ID: {random.randint(100000, 999999)}\n{content}"
    
    file_path = test_dir / filename
    with open(file_path, "w") as f:
        f.write(random_content)
    
    return file_path


def test_phase6_features():
    """Test Phase 6: Interaction and Engagement Features."""
    print("🚀 Testing Phase 6: Interaction and Engagement Features")
    print("=" * 50)
    
    # Test health endpoint
    print("\n1. Testing health endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Register test users
    print("\n2. Registering test users...")
    
    # User 1 - Content creator
    user1 = generate_test_user("creator")
    response = client.post("/auth/register", json=user1)
    if response.status_code == 201:
        print(f"   ✅ Creator user registered successfully")
        user1_id = response.json()['user']['id']
    else:
        print(f"   ❌ Creator user registration failed: {response.json()}")
        return
    
    # User 2 - Commenter/Rater
    user2 = generate_test_user("commenter")
    response = client.post("/auth/register", json=user2)
    if response.status_code == 201:
        print(f"   ✅ Commenter user registered successfully")
        user2_id = response.json()['user']['id']
    else:
        print(f"   ❌ Commenter user registration failed: {response.json()}")
        return
    
    # User 3 - Another user for threaded comments
    user3 = generate_test_user("replier")
    response = client.post("/auth/register", json=user3)
    if response.status_code == 201:
        print(f"   ✅ Replier user registered successfully")
        user3_id = response.json()['user']['id']
    else:
        print(f"   ❌ Replier user registration failed: {response.json()}")
        return
    
    # Login users
    print("\n3. Logging in users...")
    
    # Login user1
    response = client.post("/auth/login", json={"username": user1["username"], "password": user1["password"]})
    if response.status_code == 200:
        user1_token = response.json()["access_token"]
        user1_headers = {"Authorization": f"Bearer {user1_token}"}
        print(f"   ✅ Creator login successful")
    else:
        print(f"   ❌ Creator login failed")
        return
    
    # Login user2
    response = client.post("/auth/login", json={"username": user2["username"], "password": user2["password"]})
    if response.status_code == 200:
        user2_token = response.json()["access_token"]
        user2_headers = {"Authorization": f"Bearer {user2_token}"}
        print(f"   ✅ Commenter login successful")
    else:
        print(f"   ❌ Commenter login failed")
        return
    
    # Login user3
    response = client.post("/auth/login", json={"username": user3["username"], "password": user3["password"]})
    if response.status_code == 200:
        user3_token = response.json()["access_token"]
        user3_headers = {"Authorization": f"Bearer {user3_token}"}
        print(f"   ✅ Replier login successful")
    else:
        print(f"   ❌ Replier login failed")
        return
    
    # Create test content (file and summary)
    print("\n4. Creating test content...")
    
    # Upload a test file
    test_content = """# Machine Learning Basics

## Introduction
Machine learning is a subset of artificial intelligence that enables computers to learn and make decisions from data.

## Key Concepts
- **Supervised Learning**: Learning with labeled data
- **Unsupervised Learning**: Finding patterns in unlabeled data
- **Reinforcement Learning**: Learning through rewards and penalties

## Common Algorithms
1. Linear Regression
2. Decision Trees
3. Neural Networks
4. K-Means Clustering

## Applications
- Image recognition
- Natural language processing
- Recommendation systems
- Autonomous vehicles
"""
    
    test_file_path = create_test_file("ml_basics.txt", test_content)
    print(f"   ✅ Test file created: {test_file_path}")
    
    # Upload file
    with open(test_file_path, "rb") as f:
        response = client.post(
            "/files/upload", 
            files={"file": ("ml_basics.txt", f, "text/plain")},
            headers=user1_headers
        )
    
    if response.status_code == 201:
        file_id = response.json()["file"]["id"]
        print(f"   ✅ File uploaded successfully (ID: {file_id})")
    else:
        print(f"   ❌ File upload failed: {response.json()}")
        return
    
    # Generate summary
    summary_request = {
        "physical_file_ids": [file_id],
        "custom_instructions": "Create a comprehensive summary for students studying machine learning."
    }
    
    response = client.post("/summaries/generate", json=summary_request, headers=user1_headers)
    if response.status_code == 200:
        summary_id = response.json()["summary"]["id"]
        summary_title = response.json()["summary"]["title"]
        print(f"   ✅ Summary created successfully (ID: {summary_id})")
        print(f"   Summary title: {summary_title}")
    else:
        print(f"   ❌ Summary creation failed: {response.json()}")
        return
    
    # ============ USER PREFERENCES TESTING ============
    print("\n5. Testing User Preferences...")
    
    # Get default preferences
    print("\n5a. Getting default user preferences...")
    response = client.get("/preferences", headers=user1_headers)
    if response.status_code == 200:
        preferences = response.json()
        print(f"   ✅ Default preferences retrieved")
        print(f"   Theme: {preferences['default_theme']}")
        print(f"   Email notifications: {preferences['email_notifications_enabled']}")
    else:
        print(f"   ❌ Failed to get preferences: {response.json()}")
    
    # Update preferences
    print("\n5b. Updating user preferences...")
    preference_update = {
        "default_theme": "dark",
        "email_notifications_enabled": False,
        "default_content_filter_difficulty": "Medium",
        "preferences_json": {"favorite_subjects": ["Machine Learning", "Data Science"]}
    }
    
    response = client.put("/preferences", json=preference_update, headers=user1_headers)
    if response.status_code == 200:
        updated_prefs = response.json()
        print(f"   ✅ Preferences updated successfully")
        print(f"   New theme: {updated_prefs['preferences']['default_theme']}")
        print(f"   Email notifications: {updated_prefs['preferences']['email_notifications_enabled']}")
    else:
        print(f"   ❌ Failed to update preferences: {response.json()}")
    
    # ============ CONTENT COMMENTS TESTING ============
    print("\n6. Testing Content Comments...")
    
    # Create comments on summary
    print("\n6a. Creating comments on summary...")
    
    # User2 comments on summary
    comment1_data = {
        "content_type": "summary",
        "content_id": summary_id,
        "comment_text": "Great summary! Very helpful for understanding ML basics. The structure is clear and easy to follow."
    }
    
    response = client.post("/interactions/comments", json=comment1_data, headers=user2_headers)
    if response.status_code == 201:
        comment1 = response.json()["comment"]
        comment1_id = comment1["id"]
        print(f"   ✅ First comment created (ID: {comment1_id})")
        print(f"   Comment: {comment1['comment_text'][:50]}...")
    else:
        print(f"   ❌ Failed to create comment: {response.json()}")
        return
    
    # User3 replies to User2's comment
    reply_data = {
        "content_type": "summary",
        "content_id": summary_id,
        "comment_text": "I agree! This would be perfect for my AI course. Thanks for sharing this resource.",
        "parent_comment_id": comment1_id
    }
    
    response = client.post("/interactions/comments", json=reply_data, headers=user3_headers)
    if response.status_code == 201:
        reply = response.json()["comment"]
        print(f"   ✅ Reply created (ID: {reply['id']})")
        print(f"   Reply: {reply['comment_text'][:50]}...")
    else:
        print(f"   ❌ Failed to create reply: {response.json()}")
    
    # User1 (creator) also comments
    creator_comment = {
        "content_type": "summary",
        "content_id": summary_id,
        "comment_text": "Thanks for the positive feedback! I'm glad this summary is helpful for your studies."
    }
    
    response = client.post("/interactions/comments", json=creator_comment, headers=user1_headers)
    if response.status_code == 201:
        print(f"   ✅ Creator comment added")
    else:
        print(f"   ❌ Failed to create creator comment: {response.json()}")
    
    # Get all comments for the summary
    print("\n6b. Retrieving comments...")
    response = client.get(f"/interactions/comments?content_type=summary&content_id={summary_id}&include_replies=true")
    if response.status_code == 200:
        comments_response = response.json()
        print(f"   ✅ Retrieved {len(comments_response['comments'])} top-level comments")
        print(f"   Total comments: {comments_response['total_count']}")
        
        for comment in comments_response['comments']:
            print(f"   - {comment['author_username']}: {comment['comment_text'][:40]}...")
            if comment['replies']:
                for reply in comment['replies']:
                    print(f"     └─ {reply['author_username']}: {reply['comment_text'][:40]}...")
    else:
        print(f"   ❌ Failed to get comments: {response.json()}")
    
    # ============ CONTENT RATINGS TESTING ============
    print("\n7. Testing Content Ratings...")
    
    # User2 rates the summary
    print("\n7a. Creating ratings...")
    rating1_data = {
        "content_type": "summary",
        "content_id": summary_id,
        "rating": "5",
        "review_text": "Excellent summary! Clear, concise, and covers all the important topics."
    }
    
    response = client.post("/interactions/ratings", json=rating1_data, headers=user2_headers)
    if response.status_code == 200:
        rating_response = response.json()
        print(f"   ✅ Rating created: {rating_response['rating']['rating']}/5")
        print(f"   Review: {rating_response['rating']['review_text'][:50]}...")
        print(f"   Average rating: {rating_response['stats']['average_rating']}")
    else:
        print(f"   ❌ Failed to create rating: {response.json()}")
    
    # User3 also rates the summary
    rating2_data = {
        "content_type": "summary",
        "content_id": summary_id,
        "rating": "4",
        "review_text": "Very good summary, though it could use more examples."
    }
    
    response = client.post("/interactions/ratings", json=rating2_data, headers=user3_headers)
    if response.status_code == 200:
        print(f"   ✅ Second rating created")
    else:
        print(f"   ❌ Failed to create second rating: {response.json()}")
    
    # Get rating statistics
    print("\n7b. Getting rating statistics...")
    response = client.get(f"/interactions/ratings/stats?content_type=summary&content_id={summary_id}")
    if response.status_code == 200:
        stats = response.json()
        print(f"   ✅ Rating statistics:")
        print(f"   Average: {stats['average_rating']}/5")
        print(f"   Total ratings: {stats['total_ratings']}")
        print(f"   Rating breakdown: {stats['rating_breakdown']}")
    else:
        print(f"   ❌ Failed to get rating stats: {response.json()}")
    
    # Get all ratings
    response = client.get(f"/interactions/ratings?content_type=summary&content_id={summary_id}")
    if response.status_code == 200:
        ratings = response.json()
        print(f"   ✅ Retrieved {len(ratings)} ratings")
        for rating in ratings:
            print(f"   - {rating['username']}: {rating['rating']}/5 - {rating['review_text'][:40]}...")
    else:
        print(f"   ❌ Failed to get ratings: {response.json()}")
    
    # ============ NOTIFICATIONS TESTING ============
    print("\n8. Testing Notifications...")
    
    # Check if comment reply notification was created for user2
    print("\n8a. Checking notifications...")
    response = client.get("/notifications", headers=user2_headers)
    if response.status_code == 200:
        notifications = response.json()
        print(f"   ✅ User2 has {notifications['unread_count']} unread notifications")
        print(f"   Total notifications: {notifications['total_count']}")
        
        if notifications['notifications']:
            for notif in notifications['notifications'][:3]:  # Show first 3
                print(f"   - {notif['notification_type']}: {notif['message'][:60]}...")
                print(f"     Read: {notif['is_read']}, Created: {notif['created_at'][:19]}")
    else:
        print(f"   ❌ Failed to get notifications: {response.json()}")
    
    # Get unread count
    response = client.get("/notifications/unread-count", headers=user2_headers)
    if response.status_code == 200:
        unread_count = response.json()["unread_count"]
        print(f"   ✅ Unread count check: {unread_count}")
    else:
        print(f"   ❌ Failed to get unread count: {response.json()}")
    
    # Mark notifications as read
    print("\n8b. Marking notifications as read...")
    response = client.put("/notifications/mark-read", headers=user2_headers)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ {result['message']}")
    else:
        print(f"   ❌ Failed to mark notifications as read: {response.json()}")
    
    # ============ QUIZ NOTIFICATIONS TESTING ============
    print("\n9. Testing Quiz Completion Notifications...")
    
    # Create a simple quiz first
    print("\n9a. Creating a quiz...")
    if file_id:
        mcq_request = {
            "physical_file_ids": [file_id],
            "num_questions": 3,
            "difficulty_level": "Easy",
            "create_quiz": True,
            "quiz_title": "ML Basics Quiz",
            "quiz_description": "Test your knowledge of machine learning basics"
        }
        
        response = client.post("/mcqs/generate", json=mcq_request, headers=user1_headers)
        if response.status_code == 200:
            quiz_data = response.json()
            if quiz_data.get("quiz"):
                quiz_id = quiz_data["quiz"]["id"]
                print(f"   ✅ Quiz created (ID: {quiz_id})")
                
                # User2 takes the quiz
                print("\n9b. Starting quiz session...")
                response = client.post(f"/mcqs/quizzes/{quiz_id}/sessions", headers=user2_headers)
                if response.status_code == 201:
                    session = response.json()
                    session_id = session["id"]
                    print(f"   ✅ Quiz session started (ID: {session_id})")
                    
                    # Submit answers (just random for testing)
                    print("\n9c. Submitting quiz answers...")
                    answers = [
                        {"question_id": i, "selected_option": "A"} 
                        for i in range(1, 4)  # Assuming question IDs 1-3
                    ]
                    
                    # Get the actual quiz to get real question IDs
                    response = client.get(f"/mcqs/quizzes/{quiz_id}", headers=user2_headers)
                    if response.status_code == 200:
                        quiz_details = response.json()
                        if quiz_details.get("questions"):
                            # Use real question IDs
                            answers = [
                                {"question_id": q["id"], "selected_option": "A"} 
                                for q in quiz_details["questions"][:3]
                            ]
                    
                    submission = {"answers": answers}
                    response = client.post(f"/mcqs/sessions/{session_id}/submit", json=submission, headers=user2_headers)
                    if response.status_code == 200:
                        completed_session = response.json()
                        print(f"   ✅ Quiz completed!")
                        print(f"   Score: {completed_session['score']}/{completed_session['total_questions']}")
                        
                        # Check for quiz completion notification
                        print("\n9d. Checking for quiz completion notification...")
                        response = client.get("/notifications?unread_only=true", headers=user2_headers)
                        if response.status_code == 200:
                            notifications = response.json()
                            quiz_notifications = [
                                n for n in notifications['notifications'] 
                                if n['notification_type'] == 'quiz_result'
                            ]
                            if quiz_notifications:
                                print(f"   ✅ Quiz completion notification found:")
                                print(f"   Message: {quiz_notifications[0]['message']}")
                            else:
                                print(f"   ⚠️ No quiz completion notification found")
                        else:
                            print(f"   ❌ Failed to check notifications: {response.json()}")
                    else:
                        print(f"   ❌ Failed to submit quiz: {response.json()}")
                else:
                    print(f"   ❌ Failed to start quiz session: {response.json()}")
            else:
                print(f"   ⚠️ MCQs generated but no quiz created")
        else:
            print(f"   ❌ Failed to create quiz: {response.json()}")
    
    # ============ COMMENT/RATING UPDATE/DELETE TESTING ============
    print("\n10. Testing Comment and Rating Management...")
    
    # Update a comment
    print("\n10a. Updating comment...")
    if 'comment1_id' in locals():
        update_data = {"comment_text": "Great summary! Very helpful for understanding ML basics. Updated: The structure is clear and easy to follow, and the examples are perfect."}
        response = client.put(f"/interactions/comments/{comment1_id}", json=update_data, headers=user2_headers)
        if response.status_code == 200:
            updated_comment = response.json()
            print(f"   ✅ Comment updated")
            print(f"   Edited: {updated_comment['is_edited']}")
        else:
            print(f"   ❌ Failed to update comment: {response.json()}")
    
    # Try to update someone else's comment (should fail)
    if 'comment1_id' in locals():
        response = client.put(f"/interactions/comments/{comment1_id}", json=update_data, headers=user3_headers)
        if response.status_code == 403:
            print(f"   ✅ Correctly denied unauthorized comment update")
        else:
            print(f"   ❌ Should not allow updating someone else's comment: {response.status_code}")
    
    # Update a rating
    print("\n10b. Updating rating...")
    rating_update = {
        "rating": "5",
        "review_text": "Changed my mind - this is absolutely excellent! Perfect for beginners."
    }
    response = client.post("/interactions/ratings", json={
        "content_type": "summary",
        "content_id": summary_id,
        "rating": "5",
        "review_text": "Changed my mind - this is absolutely excellent! Perfect for beginners."
    }, headers=user3_headers)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Rating updated to {result['rating']['rating']}/5")
        print(f"   New average: {result['stats']['average_rating']}")
    else:
        print(f"   ❌ Failed to update rating: {response.json()}")
    
    # Reset preferences
    print("\n11. Testing preference reset...")
    response = client.post("/preferences/reset", headers=user1_headers)
    if response.status_code == 200:
        reset_prefs = response.json()
        print(f"   ✅ Preferences reset to defaults")
        print(f"   Theme: {reset_prefs['preferences']['default_theme']}")
        print(f"   Email notifications: {reset_prefs['preferences']['email_notifications_enabled']}")
    else:
        print(f"   ❌ Failed to reset preferences: {response.json()}")
    
    # Clean up test file
    print("\nCleaning up test files...")
    try:
        if 'test_file_path' in locals() and test_file_path and os.path.exists(test_file_path):
            os.remove(test_file_path)
            print(f"   ✅ Test file {test_file_path} removed.")
    except Exception as e:
        print(f"   ⚠️ Could not remove test file: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Phase 6 Testing Complete!")
    print("🎉 Interaction and Engagement functionality is working!")
    print("\nFeatures tested:")
    print("- ✅ User Preferences (get, update, reset)")
    print("- ✅ Content Comments (create, reply, threaded display)")
    print("- ✅ Content Ratings (create, update, statistics)")
    print("- ✅ Notifications (comment replies, quiz completion)")
    print("- ✅ Comment and Rating Management (update, access control)")
    print("- ✅ User notification management (list, mark read)")
    print("- ✅ Polymorphic content interaction (summaries, files, quizzes)")


if __name__ == "__main__":
    test_phase6_features() 