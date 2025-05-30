"""
Database cleanup script for clearing records after experiments.
"""

import os
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

    # List of tables to clear. Order matters less with TRUNCATE CASCADE.
    # "user" table is quoted because USER is an SQL reserved keyword.
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
        '"user"',  # Quoted because USER is a reserved keyword
    ]

    try:
        # Using TRUNCATE with RESTART IDENTITY and CASCADE
        # RESTART IDENTITY resets sequences tied to the table's columns (e.g., SERIAL)
        # CASCADE removes dependent rows in other tables
        # The order of tables in tables_to_clear matters less because of CASCADE,
        # but it's good practice to list them.
        # Some tables might be truncated by CASCADE when a parent is truncated.

        # It's often better to truncate in an order that respects dependencies if not using CASCADE,
        # or to truncate parent tables and let CASCADE handle children.
        # For robustness, we can iterate through the list. If a table is already
        # emptied by a previous CASCADE, the command will do nothing or raise a notice.

        # To avoid issues with TRUNCATE order and CASCADE, one common strategy is to
        # TRUNCATE a specific set of "parent" tables and let CASCADE handle the rest,
        # or simply TRUNCATE all tables if privileges allow and the database handles
        # the CASCADE order correctly. PostgreSQL is generally good at this.

        for table_name in tables_to_clear:
            try:
                db.execute(
                    text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;")
                )
                print(f"   ✅ Truncated {table_name}")
            except Exception as e:
                # This might happen if a table was already truncated via CASCADE from another table.
                # Or if the table doesn't exist, or permission issues persist for specific tables.
                print(f"   ⚠️  Warning truncating {table_name}: {str(e)}")

        # The explicit sequence reset block below is largely redundant if
        # TRUNCATE ... RESTART IDENTITY CASCADE handles all relevant sequences tied to table columns.
        # However, it can be a safeguard for sequences not directly owned by table columns
        # or if any TRUNCATE command failed to include RESTART IDENTITY for some reason.
        # You might see "sequence does not exist" or similar warnings if they were handled by TRUNCATE.
        print(
            "\n🔄 Resetting sequences (many should have been reset by TRUNCATE RESTART IDENTITY)..."
        )
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
            "community_subject_file_id_seq",
            # Add other sequences if they are not associated with table identity columns
        ]

        for seq in sequences:
            try:
                # Check if sequence exists before attempting to alter it, to avoid errors for sequences
                # already handled or non-existent. This requires a query.
                # For simplicity, we'll let it try and catch the error.
                db.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                print(f"   ✅ Reset {seq}")
            except Exception as e:
                # This error is expected if the sequence is tied to a column and
                # TRUNCATE ... RESTART IDENTITY already reset it, or if sequence doesn't exist.
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

    # For user data, simple DELETE is usually fine, foreign keys should handle cascades
    # or you delete in dependency order. `session_replication_role` is less likely needed here.
    # If there are complex dependencies or performance issues, TRUNCATE could be used for these too.
    tables_to_clear = [
        "user_free_api_usage",
        "gemini_file_cache",
        "user_file_access",
        "quiz_session",
        # "mcq_quiz_question_link", # Link tables usually cleared by parent cascades
        # "mcq_question_tag_link",  # Link tables usually cleared by parent cascades
        "summary",
        "physical_file",  # Assuming these are user-uploaded and not system files
        "mcq_question",  # Assuming these are user-created questions
        "mcq_quiz",  # Assuming these are user-created quizzes
        "content_comment",
        "content_rating",
        "content_version",
        # "community_member", # Deleting users below might handle this, or clear explicitly
        # "community_subject_link",
        # "community_subject_file",
        "notification",
        "ai_api_key",
        "user_session",
        # Decide if you want to delete 'users' themselves, or just their data.
        # The current list does not delete users, communities, or subjects.
    ]

    try:
        # Disable foreign key constraints temporarily if using DELETE on many interconnected tables
        # db.execute(text("SET session_replication_role = replica;"))

        for table in tables_to_clear:
            try:
                # Consider if DELETE or TRUNCATE is more appropriate here.
                # If TRUNCATE, and these tables have sequences, add RESTART IDENTITY.
                result = db.execute(text(f"DELETE FROM {table}"))
                print(f"   ✅ Cleared {table}: {result.rowcount} records deleted")
            except Exception as e:
                print(f"   ⚠️  Error clearing {table}: {str(e)}")

        # Re-enable foreign key constraints if disabled
        # db.execute(text("SET session_replication_role = DEFAULT;"))

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
        response = input(
            "⚠️  This will DELETE TEST USERS and their data. Continue? (yes/no): "
        )
        if response.lower() != "yes":
            print("❌ Operation cancelled.")
            return False

    print("🗑️  Clearing test users...")

    try:
        # Find test users (those with test-like usernames/emails)
        # Ensure the User model is imported and mapped correctly.
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
        for user_obj in test_users:  # Renamed to avoid conflict with "user" table name
            print(f"   - {user_obj.username} ({user_obj.email})")

        if test_users:
            user_ids = [user_obj.id for user_obj in test_users]

            # Clear related data first. Order from child to parent if not using ON DELETE CASCADE.
            # This assumes ON DELETE CASCADE is set up for user_id foreign keys.
            # If not, you'd need to delete from child tables explicitly first.

            # The current script deletes from related tables first, which is safer if CASCADE isn't guaranteed.
            tables_with_user_id_fk = [  # Tables directly referencing user_id
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
                "user_session",
                "user_preference",
                "physical_file",
            ]

            for table in tables_with_user_id_fk:
                # Ensure table names are correct, especially if they contain "user"
                # e.g., user_preference, user_session.
                # The column name is assumed to be 'user_id'.
                # If the column name varies, this logic needs adjustment.
                user_id_column = "user_id"  # Default assumption
                if (
                    table == "physical_file"
                ):  # Example: if physical_file uses uploader_id
                    pass  # keep user_id or change if different column name for owner

                try:
                    # Using sqlalchemy.dialects.postgresql.array for ANY is good practice
                    # For simplicity with `text()`, ensure user_ids is properly formatted if needed
                    # or pass as parameter.
                    result = db.execute(
                        text(
                            f"DELETE FROM {table} WHERE {user_id_column} = ANY(:user_ids_param)"
                        ),
                        {"user_ids_param": user_ids},
                    )
                    if result.rowcount > 0:
                        print(
                            f"   ✅ Cleared {result.rowcount} records from {table} for test users"
                        )
                except Exception as e:
                    print(f"   ⚠️  Error clearing {table} for test users: {str(e)}")

            # Finally delete the users from the "user" table (quoted)
            try:
                # Ensure your User model maps to "user" table correctly.
                # The table name must be quoted if it's 'user'.
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

    print(f"   🗂️  Deleted {total_deleted} cache files in total")


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
