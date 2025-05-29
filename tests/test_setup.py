"""
Test script to validate Phase 1 setup.
"""
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported successfully."""
    try:
        # Test core imports
        from core.config import settings
        from core.security import get_password_hash, verify_password
        
        # Test database imports
        from db_config import Base, get_db
        
        # Test model imports
        from models.models import User, Subject, UserRoleEnum
        
        # Test schema imports
        from schemas.user import UserCreate, UserRead
        from schemas.subject import SubjectCreate, SubjectRead
        
        # Test FastAPI app
        from main import app
        
        print("✅ All imports successful!")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_password_hashing():
    """Test password hashing functionality."""
    try:
        from core.security import get_password_hash, verify_password
        
        password = "test_password_123"
        hashed = get_password_hash(password)
        
        # Verify correct password
        if not verify_password(password, hashed):
            print("❌ Password verification failed for correct password")
            return False
            
        # Verify incorrect password fails
        if verify_password("wrong_password", hashed):
            print("❌ Password verification succeeded for wrong password")
            return False
            
        print("✅ Password hashing works correctly!")
        return True
    except Exception as e:
        print(f"❌ Password hashing error: {e}")
        return False

def test_configuration():
    """Test configuration loading."""
    try:
        from core.config import settings
        
        # Check some basic settings
        print(f"✅ Database URL configured: {settings.database_url.split('@')[0]}@***")
        print(f"✅ JWT secret configured: {'*' * len(settings.jwt_secret_key)}")
        print(f"✅ App name: {settings.app_name}")
        
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_models():
    """Test that models are properly defined."""
    try:
        from db_config import Base
        from models.models import User, Subject
        
        # Check that tables are registered
        tables = list(Base.metadata.tables.keys())
        print(f"✅ {len(tables)} tables defined in metadata")
        
        # Check essential tables exist
        essential_tables = ['user', 'subject']
        for table in essential_tables:
            if table in tables:
                print(f"✅ Table '{table}' found")
            else:
                print(f"❌ Table '{table}' missing")
                return False
                
        return True
    except Exception as e:
        print(f"❌ Models error: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Running Phase 1 validation tests...\n")
    
    tests = [
        ("Imports", test_imports),
        ("Password Hashing", test_password_hashing),
        ("Configuration", test_configuration),
        ("Models", test_models),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n--- Testing {test_name} ---")
        if test_func():
            passed += 1
        
    print(f"\n🎯 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("\n🎉 Phase 1 setup is working correctly!")
        print("\n📋 Next steps for Phase 2:")
        print("  - Apply database migrations")
        print("  - Implement user authentication endpoints")
        print("  - Add JWT token handling")
        print("  - Create user registration and login")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
