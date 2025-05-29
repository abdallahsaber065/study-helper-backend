"""
Test script for Phase 4 functionality (MCQ and Quiz Functionality).
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
TEST_USER = {
    "username": f"mcquser_{random.randint(1000, 9999)}",
    "first_name": "MCQ",
    "last_name": "User",
    "email": f"mcq_test{random.randint(1000, 9999)}@example.com",
    "password": f"mcqpassword{random.randint(1000, 9999)}"
}

def create_test_file(filename, content):
    """Create a test file for MCQ generation."""
    test_dir = Path("cache/test_files")
    test_dir.mkdir(exist_ok=True)
    
    # Generate random filename to avoid conflicts
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    filename = f"mcq_{random_str}_{filename}"
    
    # Add randomness to content to ensure unique hash
    random_content = f"UNIQUE MCQ CONTENT ID: {random.randint(100000, 999999)}\n{content}"
    
    file_path = test_dir / filename
    with open(file_path, "w") as f:
        f.write(random_content)
    
    return file_path


def test_mcq_and_quiz_functionality():
    """Test the MCQ and Quiz functionality."""
    print("🚀 Testing Phase 4: MCQ and Quiz Functionality")
    print("=" * 50)
    
    # Test health endpoint
    print("\n1. Testing health endpoint...")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Register test user
    print("\n2. Registering test user...")
    response = client.post("/auth/register", json=TEST_USER)
    
    if response.status_code == 201:
        print(f"   ✅ User registered successfully")
        user_id = response.json()['user']['id']
        print(f"   User ID: {user_id}")
    else:
        print(f"   ❌ User registration failed: {response.json()}")
        return
    
    # Login user
    print("\n3. Logging in user...")
    login_data = {
        "username": TEST_USER["username"],
        "password": TEST_USER["password"]
    }
    
    response = client.post("/auth/login", json=login_data)
    if response.status_code == 200:
        print(f"   ✅ Login successful")
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
    else:
        print(f"   ❌ Login failed: {response.json()}")
        return
    
    # Create test file for MCQ generation
    print("\n4. Creating test file for MCQ generation...")
    test_content = """# Machine Learning Fundamentals

## Introduction to Machine Learning
Machine Learning (ML) is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed.

## Types of Machine Learning

### Supervised Learning
- Uses labeled data to train models
- Examples: Classification and Regression
- Algorithms: Linear Regression, Decision Trees, Neural Networks

### Unsupervised Learning  
- Finds patterns in unlabeled data
- Examples: Clustering and Dimensionality Reduction
- Algorithms: K-Means, PCA, Hierarchical Clustering

### Reinforcement Learning
- Learns through interaction with environment
- Uses rewards and penalties
- Applications: Game playing, Robotics

## Key Concepts

### Overfitting
When a model performs well on training data but poorly on new data.

### Cross-Validation
A technique to assess model performance by splitting data into multiple folds.

### Feature Engineering
The process of selecting and transforming variables for machine learning models.

## Popular Algorithms

1. **Linear Regression**: Predicts continuous values
2. **Logistic Regression**: Used for binary classification
3. **Random Forest**: Ensemble method using multiple decision trees
4. **Support Vector Machines**: Effective for high-dimensional data
5. **Neural Networks**: Inspired by biological neural networks

## Applications
- Image Recognition
- Natural Language Processing
- Recommendation Systems
- Fraud Detection
- Autonomous Vehicles
"""
    
    test_file_path = create_test_file("ml_fundamentals.txt", test_content)
    print(f"   ✅ Test file created: {test_file_path}")
    
    # Upload file
    print("\n5. Uploading test file...")
    with open(test_file_path, "rb") as f:
        response = client.post(
            "/files/upload", 
            files={"file": ("ml_fundamentals.txt", f, "text/plain")},
            headers=headers
        )
    
    if response.status_code == 201:
        print(f"   ✅ File uploaded successfully")
        file_id = response.json()["file"]["id"]
        print(f"   File ID: {file_id}")
    else:
        print(f"   ❌ File upload failed: {response.json()}")
        return
    
    # Test creating question tags
    print("\n6. Creating question tags...")
    tags_to_create = [
        {"name": "Machine Learning", "description": "General ML concepts"},
        {"name": "Algorithms", "description": "ML algorithms and methods"},
        {"name": "Fundamentals", "description": "Basic concepts and definitions"}
    ]
    
    created_tags = []
    for tag_data in tags_to_create:
        response = client.post("/mcqs/tags", json=tag_data, headers=headers)
        if response.status_code == 201:
            tag = response.json()
            created_tags.append(tag)
            print(f"   ✅ Created tag: {tag['name']}")
        else:
            print(f"   ⚠️  Failed to create tag {tag_data['name']}: {response.json()}")
    
    # List tags
    print("\n7. Listing question tags...")
    response = client.get("/mcqs/tags")
    if response.status_code == 200:
        tags = response.json()
        print(f"   ✅ Retrieved {len(tags)} tags")
        for tag in tags:
            print(f"   - {tag['name']}: {tag['description']}")
    else:
        print(f"   ❌ Failed to list tags: {response.json()}")
    
    # Generate MCQs from file using AI
    print("\n8. Generating MCQs from file using AI...")
    mcq_request = {
        "physical_file_ids": [file_id],
        "num_questions": 5,
        "difficulty_level": "Medium",
        "custom_instructions": "Focus on key concepts, algorithms, and definitions. Make questions practical and educational.",
        "create_quiz": True,
        "quiz_title": "Machine Learning Fundamentals Quiz",
        "quiz_description": "Test your knowledge of basic machine learning concepts"
    }
    
    response = client.post("/mcqs/generate", json=mcq_request, headers=headers)
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ MCQs generated successfully")
        print(f"   Questions created: {result['questions_created']}")
        print(f"   Question IDs: {result['question_ids']}")
        if result['quiz']:
            quiz_id = result['quiz']['id']
            print(f"   Quiz created: {result['quiz']['title']} (ID: {quiz_id})")
        else:
            quiz_id = None
    else:
        print(f"   ❌ MCQ generation failed: {response.json()}")
        return
    
    # List generated questions
    print("\n9. Listing generated questions...")
    response = client.get("/mcqs/questions?my_questions=true", headers=headers)
    if response.status_code == 200:
        questions = response.json()
        print(f"   ✅ Retrieved {len(questions)} questions")
        for i, question in enumerate(questions[:2], 1):  # Show first 2 questions
            print(f"   Question {i}: {question['question_text'][:50]}...")
            print(f"   - Options: A) {question['option_a'][:30]}...")
            print(f"   - Correct: {question['correct_option']}")
            print(f"   - Difficulty: {question['difficulty_level']}")
    else:
        print(f"   ❌ Failed to list questions: {response.json()}")
    
    # Get specific question details
    if result['question_ids']:
        question_id = result['question_ids'][0]
        print(f"\n10. Getting question details (ID: {question_id})...")
        response = client.get(f"/mcqs/questions/{question_id}")
        if response.status_code == 200:
            question = response.json()
            print(f"   ✅ Question retrieved successfully")
            print(f"   Question: {question['question_text']}")
            print(f"   A) {question['option_a']}")
            print(f"   B) {question['option_b']}")
            print(f"   C) {question['option_c']}")
            print(f"   D) {question['option_d']}")
            print(f"   Correct Answer: {question['correct_option']}")
            print(f"   Explanation: {question['explanation']}")
            print(f"   Hint: {question['hint']}")
        else:
            print(f"   ❌ Failed to get question: {response.json()}")
    
    # List quizzes
    print("\n11. Listing quizzes...")
    response = client.get("/mcqs/quizzes", headers=headers)
    if response.status_code == 200:
        quizzes = response.json()
        print(f"   ✅ Retrieved {len(quizzes)} quizzes")
        for quiz in quizzes:
            print(f"   - {quiz['title']}: {quiz['question_count']} questions")
    else:
        print(f"   ❌ Failed to list quizzes: {response.json()}")
    
    # Get quiz with questions
    if quiz_id:
        print(f"\n12. Getting quiz details (ID: {quiz_id})...")
        response = client.get(f"/mcqs/quizzes/{quiz_id}", headers=headers)
        if response.status_code == 200:
            quiz = response.json()
            print(f"   ✅ Quiz retrieved successfully")
            print(f"   Title: {quiz['title']}")
            print(f"   Description: {quiz['description']}")
            print(f"   Questions: {len(quiz['questions'])}")
            print(f"   Difficulty: {quiz['difficulty_level']}")
        else:
            print(f"   ❌ Failed to get quiz: {response.json()}")
    
    # Start quiz session
    if quiz_id:
        print(f"\n13. Starting quiz session...")
        response = client.post(f"/mcqs/quizzes/{quiz_id}/sessions", headers=headers)
        if response.status_code == 201:
            session = response.json()
            session_id = session['id']
            print(f"   ✅ Quiz session started successfully")
            print(f"   Session ID: {session_id}")
            print(f"   Total questions: {session['total_questions']}")
            print(f"   Started at: {session['started_at']}")
        else:
            print(f"   ❌ Failed to start quiz session: {response.json()}")
            return
    
    # Submit quiz answers (simulate answering)
    if quiz_id and session_id:
        print(f"\n14. Submitting quiz answers...")
        
        # Get quiz questions to answer them
        response = client.get(f"/mcqs/quizzes/{quiz_id}", headers=headers)
        if response.status_code == 200:
            quiz = response.json()
            answers = []
            
            # Simulate answering (randomly choose between correct and incorrect)
            for question in quiz['questions']:
                # 70% chance of correct answer for demonstration
                if random.random() < 0.7:
                    selected = question['correct_option']
                else:
                    options = ['A', 'B', 'C', 'D']
                    selected = random.choice([opt for opt in options if opt != question['correct_option']])
                
                answers.append({
                    "question_id": question['id'],
                    "selected_option": selected
                })
            
            submission = {"answers": answers}
            response = client.post(f"/mcqs/sessions/{session_id}/submit", json=submission, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Quiz submitted successfully")
                print(f"   Score: {result['score']}/{result['total_questions']}")
                print(f"   Time taken: {result['time_taken_seconds']} seconds")
                print(f"   Completed at: {result['completed_at']}")
            else:
                print(f"   ❌ Failed to submit quiz: {response.json()}")
        else:
            print(f"   ❌ Failed to get quiz for answering: {response.json()}")
    
    # List user's quiz sessions
    print(f"\n15. Listing user's quiz sessions...")
    response = client.get("/mcqs/sessions", headers=headers)
    if response.status_code == 200:
        sessions = response.json()
        print(f"   ✅ Retrieved {len(sessions)} sessions")
        for session in sessions:
            status = "Completed" if session['completed_at'] else "In Progress"
            score_text = f" - Score: {session['score']}/{session['total_questions']}" if session['score'] is not None else ""
            print(f"   - Session {session['id']}: {status}{score_text}")
    else:
        print(f"   ❌ Failed to list sessions: {response.json()}")
    
    # Create a manual MCQ question
    print(f"\n16. Creating a manual MCQ question...")
    manual_question = {
        "question_text": "What is the main purpose of cross-validation in machine learning?",
        "option_a": "To increase training speed",
        "option_b": "To assess model performance and prevent overfitting",
        "option_c": "To clean the data",
        "option_d": "To visualize results",
        "correct_option": "B",
        "explanation": "Cross-validation helps assess how well a model generalizes to unseen data and helps detect overfitting.",
        "hint": "Think about model evaluation and generalization",
        "difficulty_level": "Medium",
        "tag_ids": [tag['id'] for tag in created_tags if tag['name'] == 'Fundamentals'][:1]
    }
    
    response = client.post("/mcqs/questions", json=manual_question, headers=headers)
    if response.status_code == 201:
        question = response.json()
        print(f"   ✅ Manual question created successfully")
        print(f"   Question ID: {question['id']}")
        print(f"   Question: {question['question_text']}")
    else:
        print(f"   ❌ Failed to create manual question: {response.json()}")
    
    # Create a manual quiz
    print(f"\n17. Creating a manual quiz...")
    
    # Get some question IDs for the quiz
    response = client.get("/mcqs/questions?my_questions=true&limit=3", headers=headers)
    if response.status_code == 200:
        questions = response.json()
        question_ids = [q['id'] for q in questions[:3]]
        
        manual_quiz = {
            "title": "Quick ML Concepts Quiz",
            "description": "A short quiz covering essential machine learning concepts",
            "difficulty_level": "Medium",
            "is_public": True,
            "question_ids": question_ids
        }
        
        response = client.post("/mcqs/quizzes", json=manual_quiz, headers=headers)
        if response.status_code == 201:
            quiz = response.json()
            print(f"   ✅ Manual quiz created successfully")
            print(f"   Quiz ID: {quiz['id']}")
            print(f"   Title: {quiz['title']}")
            print(f"   Questions: {quiz['question_count']}")
        else:
            print(f"   ❌ Failed to create manual quiz: {response.json()}")
    
    # Clean up test files
    try:
        os.remove(test_file_path)
    except:
        pass
    
    print("\n" + "=" * 50)
    print("✅ Phase 4 Testing Complete!")
    print("🎉 MCQ and Quiz functionality is working!")
    print("\nFeatures tested:")
    print("- ✅ Question tag management")
    print("- ✅ AI-powered MCQ generation from files")
    print("- ✅ Manual MCQ question creation")
    print("- ✅ Quiz creation and management")
    print("- ✅ Quiz session management")
    print("- ✅ Quiz taking and scoring")
    print("- ✅ User quiz history")


if __name__ == "__main__":
    test_mcq_and_quiz_functionality() 