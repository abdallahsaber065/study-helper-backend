"""
Database cleanup script for clearing records after experiments.
"""

import os
import shutil
import sys
from pathlib import Path
import argparse

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
from models.models import *  # Assuming User model is defined here for clear_test_users


def clear_all_tables(db: Session, confirm: bool = False):
    """Clear all data from all tables using TRUNCATE ... CASCADE."""
    if not confirm:
        response = input(
            "⚠️  This will DELETE ALL DATA from the database. Are you sure? (yes/no): "
        )
        if response.lower() != "yes":
            print("❌ Operation cancelled.")
            return False

    print("🗑️  Clearing all database tables using TRUNCATE...")

    # Complete list of all tables from models.py ordered by dependencies
    # Tables with fewer dependencies listed first, those with more dependencies later
    # TRUNCATE CASCADE should handle most dependency issues, but proper ordering is still good practice
    tables_to_clear = [
        # Link/Junction tables and dependent records (clear first)
        "user_free_api_usage",
        "gemini_file_cache",
        "user_file_access",
        "mcq_question_tag_link",
        "mcq_quiz_question_link",
        "community_member",
        "community_subject_link", 
        "community_subject_file",
        
        # Content interaction tables
        "content_rating",
        "content_comment",
        "content_version",
        "content_analytics",
        "notification",
        
        # Session and activity tables
        "quiz_session",
        "user_session",
        
        # Content tables
        "summary",
        "mcq_question",
        "mcq_quiz",
        
        # Core content tables
        "physical_file",
        "question_tag",
        
        # User-related tables
        "user_preference",
        "ai_api_key",
        
        # Community tables
        "community",
        
        # Reference/lookup tables
        "subject",
        
        # Core user table (clear last due to many foreign key references)
        '"user"',  # Quoted because USER is a reserved keyword
    ]

    try:
        # Using TRUNCATE with RESTART IDENTITY and CASCADE
        # RESTART IDENTITY resets sequences tied to the table's columns (e.g., SERIAL)
        # CASCADE removes dependent rows in other tables
        for table_name in tables_to_clear:
            try:
                db.execute(
                    text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;")
                )
                print(f"   ✅ Truncated {table_name}")
            except Exception as e:
                # This might happen if a table was already truncated via CASCADE from another table
                # or if the table doesn't exist
                print(f"   ⚠️  Warning truncating {table_name}: {str(e)}")

        # Reset sequences for all tables
        print("\n🔄 Resetting sequences (backup for any missed by TRUNCATE RESTART IDENTITY)...")
        sequences = [
            "user_id_seq",
            "user_session_id_seq", 
            "ai_api_key_id_seq",
            "subject_id_seq",
            "physical_file_id_seq",
            "gemini_file_cache_id_seq",
            "summary_id_seq",
            "mcq_question_id_seq",
            "question_tag_id_seq",
            "mcq_quiz_id_seq",
            "quiz_session_id_seq",
            "content_comment_id_seq",
            "content_version_id_seq",
            "content_rating_id_seq",
            "community_id_seq",
            "notification_id_seq",
            "user_preference_id_seq",
            "user_free_api_usage_id_seq",
            "community_subject_file_id_seq",
        ]

        for seq in sequences:
            try:
                db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                print(f"   ✅ Reset {seq}")
            except Exception as e:
                # Expected if sequence was already reset by TRUNCATE RESTART IDENTITY or doesn't exist
                print(f"   ⚠️  Note on resetting {seq}: {str(e)}")

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
        response = input(
            "⚠️  This will DELETE ALL USER DATA but keep system setup. Continue? (yes/no): "
        )
        if response.lower() != "yes":
            print("❌ Operation cancelled.")
            return False

    print("🗑️  Clearing user data only...")

    # Clear user-generated data but keep system reference data like subjects, question_tag
    tables_to_clear = [
        # User data and sessions
        "user_free_api_usage",
        "gemini_file_cache",
        "user_file_access",
        "user_session",
        "ai_api_key",
        "user_preference",
        
        # User-generated content
        "content_rating",
        "content_comment",
        "content_version",
        "content_analytics",
        "notification",
        
        # Quiz sessions and user activity
        "quiz_session",
        
        # User-created content
        "summary",
        "physical_file",  # User-uploaded files
        "mcq_question",   # User-created questions
        "mcq_quiz",       # User-created quizzes
        
        # Community data (user-created)
        "community_member",
        "community_subject_link",
        "community_subject_file", 
        "community",      # User-created communities
        
        # Link tables will be cleared when parent records are deleted
        "mcq_question_tag_link",  # Will be cleared when questions are deleted
        "mcq_quiz_question_link", # Will be cleared when quizzes are deleted
    ]

    try:
        for table in tables_to_clear:
            try:
                result = db.execute(text(f"DELETE FROM {table}"))
                print(f"   ✅ Cleared {table}: {result.rowcount} records deleted")
            except Exception as e:
                print(f"   ⚠️  Error clearing {table}: {str(e)}")

        db.commit()
        print("\n✅ User data cleared successfully!")
        print("ℹ️  System data preserved: subjects, question_tag, users (but their data is cleared)")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing user data: {str(e)}")
        return False


def clear_test_users(db: Session, confirm: bool = False):
    """Clear only test users and their associated data."""
    if not confirm:
        response = input(
            "⚠️  This will DELETE TEST USERS and their data. Continue? (yes/no): "
        )
        if response.lower() != "yes":
            print("❌ Operation cancelled.")
            return False

    print("🗑️  Clearing test users...")

    try:
        # Find test users (those with test-like usernames/emails)
        test_users = (
            db.query(User)
            .filter(
                (User.username.like("%test%"))
                | (User.username.like("%fileuser_%"))
                | (User.username.like("%shareuser_%"))
                | (User.email.like("%test%@%"))
            )
            .all()
        )

        print(f"Found {len(test_users)} test users:")
        for user_obj in test_users:
            print(f"   - {user_obj.username} ({user_obj.email})")

        if test_users:
            user_ids = [user_obj.id for user_obj in test_users]

            # Complete list of tables with user_id foreign keys or user relationships
            # Order matters: delete from child tables first to avoid foreign key constraint errors
            tables_with_user_fk = [
                # User preference and usage data
                ("user_free_api_usage", "user_id"),
                ("user_preference", "user_id"),
                
                # File and cache data
                ("gemini_file_cache", "api_key_id"),  # Indirect via ai_api_key.user_id
                ("user_file_access", "user_id"),
                ("user_file_access", "granted_by_user_id"),  # Secondary reference
                
                # Content interactions
                ("content_rating", "user_id"),
                ("content_comment", "author_id"),
                ("content_version", "user_id"),
                
                # Notifications (both as recipient and actor)
                ("notification", "user_id"),      # As recipient
                ("notification", "actor_id"),     # As actor
                
                # Quiz and session data
                ("quiz_session", "user_id"),
                
                # User-created content
                ("summary", "user_id"),
                ("mcq_question", "user_id"),      # creator
                ("mcq_quiz", "user_id"),          # creator
                
                # Community relationships
                ("community_member", "user_id"),
                ("community_subject_link", "added_by_user_id"),
                ("community_subject_file", "uploaded_by_user_id"),
                ("community", "creator_id"),      # Communities created by user
                
                # File ownership and sessions
                ("physical_file", "user_id"),     # uploader/owner
                ("ai_api_key", "user_id"),
                ("user_session", "user_id"),
            ]

            # Clear related data first
            for table, user_column in tables_with_user_fk:
                try:
                    result = db.execute(
                        text(f"DELETE FROM {table} WHERE {user_column} = ANY(:user_ids_param)"),
                        {"user_ids_param": user_ids},
                    )
                    if result.rowcount > 0:
                        print(f"   ✅ Cleared {result.rowcount} records from {table} ({user_column}) for test users")
                except Exception as e:
                    print(f"   ⚠️  Error clearing {table} ({user_column}) for test users: {str(e)}")

            # Finally delete the test users themselves
            try:
                result = db.execute(
                    text('DELETE FROM "user" WHERE id = ANY(:user_ids_param)'),
                    {"user_ids_param": user_ids},
                )
                print(f"   ✅ Deleted {result.rowcount} test users")
            except Exception as e:
                print(f'   ⚠️  Error deleting users from "user" table: {str(e)}')

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

    # Make sure these paths are relative to the project root (current working directory)
    cache_dirs = [
        "cache/file_uploads",
        "cache/test_files",  # If this exists
    ]

    total_deleted = 0
    project_root = Path(os.getcwd())

    for cache_dir_name in cache_dirs:
        cache_path = project_root / cache_dir_name
        if cache_path.exists() and cache_path.is_dir():
            try:
                deleted_in_dir = 0
                for file_path in cache_path.iterdir():
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                            deleted_in_dir += 1
                        except Exception as e_file:
                            print(f"     ⚠️ Error deleting file {file_path}: {e_file}")
                total_deleted += deleted_in_dir
                print(f"   ✅ Cleared {cache_dir_name} ({deleted_in_dir} files)")
            except Exception as e_dir:
                print(
                    f"   ⚠️  Error iterating or clearing {cache_dir_name}: {str(e_dir)}"
                )
        else:
            print(f"   ℹ️  Cache directory not found or not a directory: {cache_path}")
            
    # Clear all __pycache__ directories
    pycache_dirs = [
        "cache/__pycache__",
        "logs/__pycache__",
        "models/__pycache__",
        "scripts/__pycache__",
        "tests/__pycache__",
        "routers/__pycache__",
        "core/__pycache__",
    ]
    
    for pycache_dir in pycache_dirs:
        pycache_path = project_root / pycache_dir
        if pycache_path.exists() and pycache_path.is_dir():
            try:
                for file_path in pycache_path.iterdir():
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                            print(f"   ✅ Deleted {file_path.name}")
                        except Exception as e:
                            print(f"   ⚠️  Error deleting {file_path.name}: {str(e)}")
                    elif file_path.is_dir():
                        try:
                            shutil.rmtree(file_path)
                            print(f"   ✅ Deleted {file_path.name}")
                        except Exception as e:
                            print(f"   ⚠️  Error deleting {file_path.name}: {str(e)}")
                    else:
                        print(f"   ℹ️  {file_path.name} is not a file or directory")
            except Exception as e:
                print(f"   ⚠️  Error deleting {pycache_dir}: {str(e)}")

    print(f"   🗂️  Deleted {total_deleted} cache files in total")

def clear_all_logs():
    """Clear all logs from the logs directory."""
    print("🗑️  Clearing all logs...")
    logs_dir = Path("logs")
    if logs_dir.exists() and logs_dir.is_dir():
        for file in logs_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                    print(f"   ✅ Deleted {file.name}")
                except Exception as e:
                    print(f"   ⚠️  Error deleting {file.name}: {str(e)}")
    else:
        print(f"   ℹ️  Logs directory not found or not a directory: {logs_dir}")

def main():
    parser = argparse.ArgumentParser(description="Database and cache cleanup utility")
    parser.add_argument(
        "--all", action="store_true", help="Clear all data from database using TRUNCATE"
    )
    parser.add_argument(
        "--user-data",
        action="store_true",
        help="Clear user-generated data only (keeps users, subjects, etc.)",
    )
    parser.add_argument(
        "--test-users",
        action="store_true",
        help="Clear test users and their associated data",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Clear cache files from configured directories",
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Clear all logs from the logs directory",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirm dangerous operations (use with caution!)",
    )

    args = parser.parse_args()

    if not any([args.all, args.user_data, args.test_users, args.cache]):
        print("🧹 Database & Cache Cleanup Utility")
        print("=" * 35)
        parser.print_help()
        
        print("\n📋 Tables in Database (from models.py):")
        all_tables = [
            "user", "user_session", "ai_api_key", "subject", "physical_file",
            "gemini_file_cache", "user_file_access", "summary", "mcq_question_tag_link",
            "mcq_question", "question_tag", "mcq_quiz_question_link", "mcq_quiz",
            "quiz_session", "content_comment", "content_version", "content_analytics",
            "community", "community_member", "community_subject_link", 
            "community_subject_file", "notification", "content_rating",
            "user_preference", "user_free_api_usage"
        ]
        
        for i, table in enumerate(all_tables, 1):
            print(f"   {i:2d}. {table}")
        
        print(f"\nTotal: {len(all_tables)} tables")
        print("\nExample: python scripts/clear_db.py --test-users --cache --yes")
        return

    db_session = None  # Initialize to None
    try:
        # Only connect to DB if a DB operation is requested
        if args.all or args.user_data or args.test_users:
            db_session = next(get_db())

        if args.cache:
            clear_cache_files()

        if args.all and db_session:
            clear_all_tables(db_session, args.yes)
        elif args.user_data and db_session:
            clear_user_data_only(db_session, args.yes)
        elif args.test_users and db_session:
            # This function requires the User model to be defined and imported
            # from models.models. Ensure User is available.
            if "User" not in globals() or not hasattr(globals()["User"], "username"):
                print(
                    "❌ Error: User model not found or not correctly imported for --test-users. Skipping."
                )
            else:
                clear_test_users(db_session, args.yes)

        if args.logs:
            clear_all_logs()

        print("\n🎉 Cleanup completed!")

    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {str(e)}")
        if hasattr(e, "pgcode") and hasattr(
            e, "pgerror"
        ):  # Check for psycopg2 error attributes
            print(f"   PostgreSQL Error Code: {e.pgcode}")
            print(f"   PostgreSQL Error: {e.pgerror}")
        if db_session:  # ensure rollback if db_session was initialized
            db_session.rollback()
    finally:
        if db_session:
            db_session.close()


if __name__ == "__main__":
    main()
