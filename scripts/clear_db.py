"""
Database cleanup script for clearing records after experiments.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# set working directory to the project root (parent directory of this script directory)
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# print the working directory for debugging
print(f"Working directory: {os.getcwd()}")

from sqlalchemy.orm import Session
from sqlalchemy import text
from db_config import get_db, engine
from models.models import *
import argparse

def clear_all_tables(db: Session, confirm: bool = False):
    """Clear all data from all tables."""
    if not confirm:
        response = input("⚠️  This will DELETE ALL DATA from the database. Are you sure? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return False
    
    print("🗑️  Clearing all database tables...")
    
    # List of tables to clear in dependency order (child tables first)
    tables_to_clear = [
        # File and content related
        "user_free_api_usage",
        "gemini_file_cache", 
        "user_file_access",
        "community_subject_file",
        
        # Content interactions
        "content_rating",
        "content_comment",
        "content_version",
        "content_analytics",
        
        # Quiz related
        "quiz_session",
        "mcq_quiz_question_link",
        "mcq_question_tag_link",
        "mcq_question",
        "mcq_quiz",
        "question_tag",
        
        # Community related
        "community_member",
        "community_subject_link",
        "notification",
        "community",
        
        # Summary and file management
        "summary",
        "physical_file",
        
        # User related
        "user_preference",
        "ai_api_key",
        "user_session",
        
        # Core tables
        "subject",
        "user"
    ]
    
    try:
        # Disable foreign key constraints temporarily
        # db.execute(text("SET session_replication_role = replica;"))
        
        for table in tables_to_clear:
            try:
                # Quote table name if it's a reserved keyword
                table_name = f'"{table}"' if table == "user" else table
                result = db.execute(text(f"DELETE FROM {table_name}"))
                if result.rowcount > 0:
                    print(f"   ✅ Cleared {table}: {result.rowcount} records")
            except Exception as e:
                print(f"   ⚠️  Error clearing {table}: {str(e)}")
        
        # Re-enable foreign key constraints
        # db.execute(text("SET session_replication_role = DEFAULT;"))
        
        # Reset sequences to start from 1
        print("\n🔄 Resetting sequences...")
        sequences = [
            "user_id_seq",
            "ai_api_key_id_seq",
            "subject_id_seq", 
            "physical_file_id_seq",
            "summary_id_seq",
            "mcq_question_id_seq",
            "question_tag_id_seq",
            "mcq_quiz_id_seq",
            "quiz_session_id_seq",
            "community_id_seq",
            "notification_id_seq",
            "content_comment_id_seq",
            "content_version_id_seq",
            "content_rating_id_seq",
            "user_preference_id_seq",
            "gemini_file_cache_id_seq",
            "user_free_api_usage_id_seq",
            "community_subject_file_id_seq"
        ]
        
        for seq in sequences:
            try:
                db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                print(f"   ✅ Reset {seq}")
            except Exception as e:
                print(f"   ⚠️  Error resetting {seq}: {str(e)}")
        
        db.commit()
        print("\n✅ Database cleared successfully!")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing database: {str(e)}")
        return False

def clear_user_data_only(db: Session, confirm: bool = False):
    """Clear only user-generated data, keep system data."""
    if not confirm:
        response = input("⚠️  This will DELETE ALL USER DATA but keep system setup. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return False
    
    print("🗑️  Clearing user data only...")
    
    tables_to_clear = [
        "user_free_api_usage",
        "gemini_file_cache",
        "user_file_access", 
        "quiz_session",
        "mcq_quiz_question_link",
        "mcq_question_tag_link",
        "summary",
        "physical_file",
        "mcq_question",
        "mcq_quiz",
        "content_comment",
        "content_rating",
        "content_version",
        "community_member",
        "community_subject_link",
        "community_subject_file",
        "notification",
        "ai_api_key",
        "user_session"
    ]
    
    try:
        for table in tables_to_clear:
            try:
                # Quote table name if it's a reserved keyword
                table_name = f'"{table}"' if table == "user" else table
                result = db.execute(text(f"DELETE FROM {table_name}"))
                print(f"   ✅ Cleared {table}: {result.rowcount} records deleted")
            except Exception as e:
                print(f"   ⚠️  Error clearing {table}: {str(e)}")
        
        db.commit()
        print("\n✅ User data cleared successfully!")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing user data: {str(e)}")
        return False

def clear_test_users(db: Session, confirm: bool = False):
    """Clear only test users and their associated data."""
    if not confirm:
        response = input("⚠️  This will DELETE TEST USERS and their data. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return False
    
    print("🗑️  Clearing test users...")
    
    try:
        # Find test users (those with test-like usernames/emails)
        test_users = db.query(User).filter(
            (User.username.like('%test%')) |
            (User.username.like('%fileuser_%')) |
            (User.username.like('%shareuser_%')) |
            (User.email.like('%test%@%'))
        ).all()
        
        print(f"Found {len(test_users)} test users:")
        for user in test_users:
            print(f"   - {user.username} ({user.email})")
        
        if test_users:
            user_ids = [user.id for user in test_users]
            
            # Clear related data first
            tables_with_user_id = [
                "user_free_api_usage",
                "user_file_access",
                "quiz_session", 
                "summary",
                "mcq_question",
                "mcq_quiz",
                "content_comment",
                "content_rating",
                "community_member",
                "notification",
                "ai_api_key",
                "user_session"
            ]
            
            for table in tables_with_user_id:
                try:
                    result = db.execute(text(f"DELETE FROM {table} WHERE user_id = ANY(:user_ids)"), 
                                      {"user_ids": user_ids})
                    if result.rowcount > 0:
                        print(f"   ✅ Cleared {table}: {result.rowcount} records")
                except Exception as e:
                    print(f"   ⚠️  Error clearing {table}: {str(e)}")
            
            # Clear physical files uploaded by test users
            try:
                result = db.execute(text("DELETE FROM physical_file WHERE user_id = ANY(:user_ids)"), 
                                  {"user_ids": user_ids})
                if result.rowcount > 0:
                    print(f"   ✅ Cleared physical_file: {result.rowcount} records")
            except Exception as e:
                print(f"   ⚠️  Error clearing physical_file: {str(e)}")
            
            # Finally delete the users
            try:
                result = db.execute(text("DELETE FROM \"user\" WHERE id = ANY(:user_ids)"), 
                                  {"user_ids": user_ids})
                print(f"   ✅ Deleted {result.rowcount} test users")
            except Exception as e:
                print(f"   ⚠️  Error deleting users: {str(e)}")
        
        db.commit()
        print("\n✅ Test users cleared successfully!")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing test users: {str(e)}")
        return False

def clear_cache_files():
    """Clear uploaded files from cache directory."""
    print("🗑️  Clearing cache files...")
    
    cache_dirs = [
        "cache/file_uploads",
        "cache/test_files",
        "file_uploads"
    ]
    
    total_deleted = 0
    
    for cache_dir in cache_dirs:
        cache_path = Path(cache_dir)
        if cache_path.exists():
            try:
                for file_path in cache_path.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                        total_deleted += 1
                print(f"   ✅ Cleared {cache_dir}")
            except Exception as e:
                print(f"   ⚠️  Error clearing {cache_dir}: {str(e)}")
    
    print(f"   🗂️  Deleted {total_deleted} cache files")

def main():
    parser = argparse.ArgumentParser(description="Database cleanup utility")
    parser.add_argument("--all", action="store_true", help="Clear all data")
    parser.add_argument("--user-data", action="store_true", help="Clear user data only")
    parser.add_argument("--test-users", action="store_true", help="Clear test users only")
    parser.add_argument("--cache", action="store_true", help="Clear cache files only")
    parser.add_argument("--yes", action="store_true", help="Auto-confirm (use with caution!)")
    
    args = parser.parse_args()
    
    if not any([args.all, args.user_data, args.test_users, args.cache]):
        print("🧹 Database Cleanup Utility")
        print("=" * 30)
        print("Please choose an option:")
        print("  --all         Clear ALL data (complete reset)")
        print("  --user-data   Clear user data only (keep system setup)")  
        print("  --test-users  Clear test users and their data only")
        print("  --cache       Clear cache files only")
        print("  --yes         Auto-confirm (combine with other options)")
        print("\nExample: python scripts/clear_db.py --test-users --cache")
        return
    
    try:
        db = next(get_db())
        
        if args.cache:
            clear_cache_files()
        
        if args.all:
            clear_all_tables(db, args.yes)
        elif args.user_data:
            clear_user_data_only(db, args.yes)
        elif args.test_users:
            clear_test_users(db, args.yes)
        
        print("\n🎉 Cleanup completed!")
        
    except Exception as e:
        print(f"\n❌ Database connection error: {str(e)}")

if __name__ == "__main__":
    main() 
