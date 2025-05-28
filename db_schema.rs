// PostgreSQL database schema for ai study helper application

// --- ENUM Types (Define these in PostgreSQL first) ---
// CREATE TYPE user_role_enum AS ENUM ('user', 'admin', 'moderator');
// CREATE TYPE difficulty_level_enum AS ENUM ('Easy', 'Medium', 'Hard');
// CREATE TYPE ai_provider_enum AS ENUM ('OpenAI', 'Google');
// CREATE TYPE content_type_enum AS ENUM ('file', 'summary', 'quiz'); // Add other types as needed
// CREATE TYPE community_role_enum AS ENUM ('admin', 'member', 'moderator');
// CREATE TYPE community_file_category_enum AS ENUM ('lecture', 'section', 'exam', 'summary_material', 'general_resource', 'other');
// CREATE TYPE notification_type_enum AS ENUM ('new_content', 'comment_reply', 'quiz_result', 'community_invite', 'mention');
// CREATE TYPE rating_value_enum AS ENUM ('1', '2', '3', '4', '5'); // For star ratings

// --- Generic Trigger Function for updated_at (Define this in PostgreSQL) ---
// CREATE OR REPLACE FUNCTION trigger_set_timestamp()
// RETURNS TRIGGER AS $$
// BEGIN
//   NEW.updated_at = NOW();
//   RETURN NEW;
// END;
// $$ LANGUAGE plpgsql;

Table subject {
    id integer [pk, autoincrement]
    name varchar(100) [not null, unique]
    description text
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger: CREATE TRIGGER set_subject_updated_at BEFORE UPDATE ON subject FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();
    // quizzes list removed, relationship is via mcq_quiz.subject_id
    // Relationship to communities is via community_subject_link
}

Table user {
    id integer [pk, autoincrement]
    username varchar(50) [not null, unique]
    first_name varchar(50) [not null]
    last_name varchar(50) [not null]
    email varchar(100) [not null, unique]
    password_hash varchar(255) [not null]

    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    last_login timestamp [default: `now()`]

    profile_picture_url varchar(255) // Consider if this should be nullable
    is_active boolean [default: true]
    is_verified boolean [default: false]
    role user_role_enum [not null, default: 'user'] // Using ENUM type

    // Redundant lists removed; relationships are defined by FKs in other tables
    // Relationship to communities is via community_member
}

Table user_session {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    session_token varchar(255) [not null, unique]
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    expires_at timestamp [default: `now() + interval '2 days'`]
}

Table question_tag {
    id integer [pk, autoincrement]
    name varchar(100) [not null, unique]
    description text
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    // questions list removed, use mcq_question_tag_link join table
}

Table mcq_question {
    id integer [pk, autoincrement]
    question_text text [not null]

    option_a text [not null]
    option_b text [not null]
    option_c text
    option_d text
    correct_option char(1) [not null, check: "correct_option IN ('A', 'B', 'C', 'D')"] // Added check constraint
    
    explanation text
    hint text
    difficulty_level difficulty_level_enum [not null] // Using ENUM type

    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    
    // tag field removed, use mcq_question_tag_link join table for many-to-many
    user_id integer [ref: > user.id] // Creator of the question
}

// Join table for many-to-many relationship between mcq_question and question_tag
Table mcq_question_tag_link {
    question_id integer [ref: > mcq_question.id, not null]
    tag_id integer [ref: > question_tag.id, not null]
    created_at timestamp [default: `now()`]
    Primary Key(question_id, tag_id)
}

Table mcq_quiz {
    id integer [pk, autoincrement]
    title varchar(255) [not null]
    description text
    
    difficulty_level difficulty_level_enum [not null] // Using ENUM type
    // question_count can be derived or maintained carefully
    
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger

    // questions_json can store a snapshot of questions for this quiz instance if needed
    // questions_json jsonb 
    
    is_active boolean [default: true]
    is_public boolean [default: false] // Consider how this interacts with community visibility

    user_id integer [ref: > user.id, not null] // Creator of the quiz
    subject_id integer [ref: > subject.id] // Optional: if quiz is tied to a specific subject
    community_id integer [ref: > community.id] // Optional: if quiz is specific to a community
}

// Join table for many-to-many relationship between mcq_quiz and mcq_question
Table mcq_quiz_question_link {
    quiz_id integer [ref: > mcq_quiz.id, not null]
    question_id integer [ref: > mcq_question.id, not null]
    display_order integer // Optional: to maintain order of questions in a quiz
    created_at timestamp [default: `now()`]
    Primary Key(quiz_id, question_id)
}

Table quiz_session {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    quiz_id integer [ref: > mcq_quiz.id, not null]
    session_start timestamp [default: `now()`]
    session_end timestamp
    is_completed boolean [default: false]
    current_answers jsonb // Stores user's answers, e.g., {"question_id_1": "A", "question_id_2": "C"}
    // expiration_time timestamp [default: `now() + interval '30 min'`] // Consider if this is per session or per quiz type
    score integer
    // num_total_questions integer // Can be derived from linked questions or quiz.question_count at session start
    // num_correct_answers integer
    time_taken_seconds integer // Renamed for clarity
    
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
}

// user_quiz_session table seems redundant with quiz_session.
// If specific aggregated history per user per quiz is needed beyond individual sessions,
// it could be a view or derived data. For now, removed.

Table summary { // Renamed from Summary
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    physical_file_id integer [ref: > physical_file.id] // Optional: if summary is directly from a file
    title varchar(255) [not null]
    full_markdown text [not null]
    // section_titles jsonb // Can be derived from markdown or stored if complex
    // section_count integer // Can be derived
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    community_id integer [ref: > community.id] // Optional: if summary is specific to a community
}

Table ai_api_key {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    encrypted_api_key text [not null, unique]
    provider_name ai_provider_enum [not null] // Using ENUM type

    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    last_used_at timestamp // Renamed for consistency

    is_active boolean [default: true]
}

Table physical_file {
    id integer [pk, autoincrement]
    file_hash varchar(100) [not null, unique] // Consider SHA256, so varchar(64) hex
    file_name varchar(255) [not null]
    file_path varchar(255) [not null, unique] // Path in storage, should be unique
    file_type varchar(50) [not null] // e.g., pdf, docx, txt
    file_size_bytes integer [not null] // Renamed for clarity
    mime_type varchar(100) [not null] // Max length usually around 100

    uploaded_at timestamp [default: `now()`] // Renamed for consistency
    user_id integer [ref: > user.id, not null] // Original uploader/owner
    // Relationship to community subjects is via community_subject_file
}

Table user_file_access { // Renamed from user_file for clarity
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    physical_file_id integer [ref: > physical_file.id, not null]
    access_level varchar(50) [not null, default: 'read'] // e.g., read, write, owner
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    Unique(user_id, physical_file_id) // A user should have one defined access level per file
}

Table gemini_file_cache {
    id integer [pk, autoincrement]
    // user_id integer [ref: > user.id] // If cache is per user
    physical_file_id integer [ref: > physical_file.id, not null]
    processing_type varchar(50) [not null] // e.g., 'summary', 'mcq_generation'
    gemini_response jsonb [not null]
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    Unique(physical_file_id, processing_type) // Cache one response per file per processing type
}

Table content_comment {
    id integer [pk, autoincrement]
    author_id integer [ref: > user.id, not null]
    
    // Polymorphic association:
    content_type content_type_enum [not null] // e.g., 'file', 'summary', 'quiz'
    content_id integer [not null] // ID of the file, summary, or quiz etc.
    
    comment_text text [not null]
    parent_comment_id integer [ref: > content_comment.id] // For threaded comments
    is_deleted boolean [default: false]
    is_edited boolean [default: false]

    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    // Index on (content_type, content_id) for faster comment retrieval
}

Table content_version {
    id integer [pk, autoincrement]
    // Polymorphic association:
    content_type content_type_enum [not null]
    content_id integer [not null]

    user_id integer [ref: > user.id, not null] // User who created this version
    
    version_number integer [not null]
    version_data jsonb [not null] // Snapshot of the content (e.g., summary markdown, file metadata)
    created_at timestamp [default: `now()`]
    // updated_at not typically needed for an immutable version record

    Unique(content_type, content_id, version_number)
}

Table content_analytics {
    // Polymorphic association:
    content_type content_type_enum [not null]
    content_id integer [not null]

    view_count integer [default: 0]
    like_count integer [default: 0]
    share_count integer [default: 0]
    comment_count integer [default: 0] // Can be derived or maintained by triggers/app logic

    // last_viewed_at timestamp // Optional
    created_at timestamp [default: `now()`] // When analytics entry was first created
    updated_at timestamp [default: `now()`] // When counts were last updated (Apply trigger)

    Primary Key(content_type, content_id) // Each content item has one analytics row
}

// --- Community Feature Tables ---

Table community {
    id integer [pk, autoincrement]
    name varchar(150) [not null, unique]
    description text
    creator_id integer [ref: > user.id, not null] // User who created the community
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    is_private boolean [default: false] // Indicates if community is invite-only or public
}

Table community_member {
    community_id integer [ref: > community.id, not null]
    user_id integer [ref: > user.id, not null]
    role community_role_enum [not null, default: 'member'] // Role within this specific community
    joined_at timestamp [default: `now()`]
    Primary Key(community_id, user_id)
    // Add trigger for updated_at if member status/role can be updated
}

Table community_subject_link {
    community_id integer [ref: > community.id, not null]
    subject_id integer [ref: > subject.id, not null]
    added_by_user_id integer [ref: > user.id, not null] // User who linked this subject to the community
    created_at timestamp [default: `now()`]
    Primary Key(community_id, subject_id)
}

Table community_subject_file {
    id integer [pk, autoincrement]
    community_id integer [ref: > community.id, not null]
    subject_id integer [ref: > subject.id, not null] // Ensures file is linked via a subject in the community
    physical_file_id integer [ref: > physical_file.id, not null]
    file_category community_file_category_enum [not null]
    uploaded_by_user_id integer [ref: > user.id, not null] // User who uploaded/linked this file in community context
    description text // Optional description for the file in this context
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
    Unique(community_id, subject_id, physical_file_id) // Prevent duplicate file linking per community-subject
    // Foreign key to community_subject_link can also be considered:
    // community_subject_link_id integer [ref: > community_subject_link.id] - but composite FKs might be better
    // Ensure (community_id, subject_id) exists in community_subject_link
}

// --- Enhanced Features Tables ---

Table notification {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null] // Recipient of the notification
    notification_type notification_type_enum [not null]
    
    // Polymorphic association for related content (optional but useful)
    related_content_type content_type_enum // e.g., 'quiz', 'summary', 'comment' (extend content_type_enum if needed)
    related_content_id integer 
    related_community_id integer [ref: > community.id] // If notification is community-specific
    actor_id integer [ref: > user.id] // User who triggered the notification (e.g. who commented)

    message text [not null]
    is_read boolean [default: false]
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger (e.g., when marked as read)
    // Index on (user_id, is_read, created_at) for efficient retrieval of unread notifications
}

Table content_rating {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null]
    
    // Polymorphic association for the content being rated
    content_type content_type_enum [not null] // e.g., 'summary', 'quiz', 'file'
    content_id integer [not null]
    
    rating rating_value_enum [not null] // Using ENUM for 1-5 star rating
    review_text text // Optional textual review
    
    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger (if reviews can be edited)
    Unique(user_id, content_type, content_id) // User can rate a piece of content once
    // Index on (content_type, content_id) for aggregating ratings
}

Table user_preference {
    id integer [pk, autoincrement]
    user_id integer [ref: > user.id, not null, unique] // Each user has one row of preferences
    
    // Example preference fields (can be expanded or stored as JSONB if highly dynamic)
    email_notifications_enabled boolean [default: true]
    default_theme varchar(50) [default: 'light'] // e.g., 'light', 'dark'
    default_content_filter_difficulty difficulty_level_enum // User's preferred default difficulty
    // Add more specific notification preferences as needed, e.g.:
    // notification_on_comment_reply boolean [default: true]
    // notification_on_new_community_content boolean [default: true]

    preferences_json jsonb // For more dynamic or less common preferences

    created_at timestamp [default: `now()`]
    updated_at timestamp [default: `now()`] // Apply trigger
}