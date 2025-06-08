"""
Router for MCQ and Quiz functionality.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import select, func, or_, and_, delete

from db_config import get_async_db
from core.security import get_current_user
from models.models import (
    User, QuestionTag, McqQuestion, McqQuestionTagLink, 
    McqQuiz, McqQuizQuestionLink, QuizSession, CommunityMember
)
from schemas.mcq import (
    _convert_question_to_read,
    # Quiz schemas
    McqQuizCreate, McqQuizRead, McqQuizUpdate, McqQuizWithQuestions,
    # Session schemas
    QuizSessionCreate, QuizSessionRead, QuizSessionSubmit,
    # AI generation schemas
    MCQGenerationRequest
)
from services.mcq_service import MCQGeneratorService
from services.community_service import CommunityService
from services.notification_service import NotificationService

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


# ============ AI MCQ Generation ============

@router.post("/generate")
async def generate_mcqs(
    request: MCQGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Generate MCQs from files using AI."""
    # Check community access if community_id is provided
    if request.community_id:
        community_service = CommunityService(db)
        try:
            await community_service._check_admin_or_moderator(current_user, request.community_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required to create community MCQs"
            )
    
    # Validate request.num_questions
    if request.num_questions <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of questions must be greater than zero"
        )
    
    if request.num_questions > 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 60 questions can be generated in a single request"
        )
    
    mcq_service = MCQGeneratorService(db)
    result = await mcq_service.generate_mcqs(request, current_user)
    return result


# ============ Quiz Endpoints ============

@router.post("", response_model=McqQuizRead, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    quiz: McqQuizCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new quiz."""
    # Check community access if community_id is provided
    if quiz.community_id:
        community_service = CommunityService(db)
        try:
            await community_service._check_admin_or_moderator(current_user, quiz.community_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required to create community quizzes"
            )
    
    # Create the quiz
    quiz_data = quiz.dict(exclude={"question_ids"})
    db_quiz = McqQuiz(**quiz_data, user_id=current_user.id)
    db.add(db_quiz)
    await db.commit()
    await db.refresh(db_quiz)
    
    # Link with questions
    if quiz.question_ids:
        for idx, question_id in enumerate(quiz.question_ids):
            question_stmt = select(McqQuestion).where(McqQuestion.id == question_id)
            question_result = await db.execute(question_stmt)
            question = question_result.scalar_one_or_none()
            if question:
                quiz_link = McqQuizQuestionLink(
                    quiz_id=db_quiz.id,
                    question_id=question_id,
                    display_order=idx + 1
                )
                db.add(quiz_link)
        await db.commit()
    
    # Add question count
    count_stmt = select(func.count(McqQuizQuestionLink.quiz_id)).where(
        McqQuizQuestionLink.quiz_id == db_quiz.id
    )
    count_result = await db.execute(count_stmt)
    question_count = count_result.scalar()
    
    result = McqQuizRead.from_orm(db_quiz)
    result.question_count = question_count
    return result


@router.get("", response_model=List[McqQuizRead])
async def list_quizzes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_public: Optional[bool] = Query(None),
    my_quizzes: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List quizzes with filtering options."""
    stmt = select(McqQuiz)
    
    if my_quizzes:
        stmt = stmt.where(McqQuiz.user_id == current_user.id)
    elif is_public is not None:
        stmt = stmt.where(McqQuiz.is_public == is_public)
    else:
        # Show public quizzes and user's own quizzes
        stmt = stmt.where(
            or_(McqQuiz.is_public == True, McqQuiz.user_id == current_user.id)
        )
    
    stmt = stmt.offset(skip).limit(limit)
    result_data = await db.execute(stmt)
    quizzes = result_data.scalars().all()
    
    # Add question counts
    result = []
    for quiz in quizzes:
        count_stmt = select(func.count(McqQuizQuestionLink.quiz_id)).where(
            McqQuizQuestionLink.quiz_id == quiz.id
        )
        count_result = await db.execute(count_stmt)
        question_count = count_result.scalar()
        
        quiz_data = McqQuizRead.from_orm(quiz)
        quiz_data.question_count = question_count
        result.append(quiz_data)
    
    return result


# ============ Quiz Session Management ============

@router.get("/sessions", response_model=List[QuizSessionRead])
async def list_my_quiz_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List user's quiz sessions."""
    # Using join to get quiz title with the session
    stmt = select(QuizSession, McqQuiz.title).join(
        McqQuiz, QuizSession.quiz_id == McqQuiz.id
    ).where(
        QuizSession.user_id == current_user.id
    ).order_by(
        QuizSession.started_at.desc()
    ).offset(skip).limit(limit)
    
    result_data = await db.execute(stmt)
    sessions = result_data.all()
    
    # Combine session with quiz title
    result = []
    for session, quiz_title in sessions:
        session_dict = {
            "id": session.id,
            "user_id": session.user_id,
            "quiz_id": session.quiz_id,
            "quiz_title": quiz_title,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "score": session.score,
            "total_questions": session.total_questions,
            "answers_json": session.answers_json,
            "time_taken_seconds": session.time_taken_seconds
        }
        result.append(QuizSessionRead(**session_dict))
    
    return result


@router.get("/sessions/{session_id}", response_model=QuizSessionRead)
async def get_quiz_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get quiz session details."""
    stmt = select(QuizSession).where(QuizSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this quiz session"
        )
    
    return session


@router.put("/sessions/{session_id}", response_model=QuizSessionRead)
async def update_quiz_session(
    session_id: int,
    submission: QuizSessionSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Edit a quiz session's answers."""
    stmt = select(QuizSession).where(QuizSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership
    if session.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this quiz session"
        )
    
    # Update session with new answers
    # Create null lists for 'correct' and 'is_correct', then map them to standardize the answers
    answer_details = {}
    for answer in submission.answers:
            answer_details[str(answer.question_id)] = {
                "selected": answer.selected_option.value,
                "correct": None,
                "is_correct": None
        }
        
    session.answers_json = answer_details
    session.time_taken_seconds = int((datetime.now(timezone.utc) - session.started_at).total_seconds())
        
    await db.commit()
    await db.refresh(session)
    
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a quiz session."""
    stmt = select(QuizSession).where(QuizSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership or admin rights
    if session.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this quiz session"
        )
    
    await db.delete(session)
    await db.commit()


@router.get("/{quiz_id}", response_model=McqQuizWithQuestions)
async def get_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific quiz with its questions."""
    stmt = select(McqQuiz).where(McqQuiz.id == quiz_id)
    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check access permissions
    if not quiz.is_public and quiz.user_id != current_user.id:
        # Check if this is a community quiz and user is a member
        if quiz.community_id:
            member_stmt = select(CommunityMember).where(
                and_(
                    CommunityMember.community_id == quiz.community_id,
                    CommunityMember.user_id == current_user.id
                )
            )
            member_result = await db.execute(member_stmt)
            member = member_result.scalar_one_or_none()
            
            if not member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this quiz"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this quiz"
            )
    
    # Get questions in order
    quiz_questions_stmt = select(McqQuizQuestionLink).where(
        McqQuizQuestionLink.quiz_id == quiz_id
    ).order_by(McqQuizQuestionLink.display_order)
    
    quiz_questions_result = await db.execute(quiz_questions_stmt)
    quiz_questions = quiz_questions_result.scalars().all()
    
    questions = []
    for quiz_question in quiz_questions:
        question_stmt = select(McqQuestion).options(
            selectinload(McqQuestion.tag_links).selectinload(McqQuestionTagLink.tag)
        ).where(McqQuestion.id == quiz_question.question_id)
        
        question_result = await db.execute(question_stmt)
        question = question_result.scalar_one_or_none()
        
        if question:
            questions.append(_convert_question_to_read(question))
    
    result = McqQuizWithQuestions.from_orm(quiz)
    result.questions = questions
    result.question_count = len(questions)
    return result


@router.put("/{quiz_id}", response_model=McqQuizRead)
async def update_quiz(
    quiz_id: int,
    quiz_update: McqQuizUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update a quiz."""
    stmt = select(McqQuiz).where(McqQuiz.id == quiz_id)
    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check ownership or admin rights
    if quiz.user_id != current_user.id and current_user.role.value != "admin":
        # If it's a community quiz, check if user is admin/moderator
        if quiz.community_id:
            community_service = CommunityService(db)
            try:
                await community_service._check_admin_or_moderator(current_user, quiz.community_id)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to update this quiz"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this quiz"
            )
    
    # Update basic fields
    update_data = quiz_update.dict(exclude_unset=True, exclude={"question_ids"})
    for field, value in update_data.items():
        setattr(quiz, field, value)
    
    # Update question links if provided
    if quiz_update.question_ids is not None:
        # Remove existing question links
        delete_stmt = delete(McqQuizQuestionLink).where(
            McqQuizQuestionLink.quiz_id == quiz_id
        )
        await db.execute(delete_stmt)
        
        # Add new question links
        for idx, question_id in enumerate(quiz_update.question_ids):
            question_stmt = select(McqQuestion).where(McqQuestion.id == question_id)
            question_result = await db.execute(question_stmt)
            question = question_result.scalar_one_or_none()
            
            if question:
                quiz_link = McqQuizQuestionLink(
                    quiz_id=quiz_id,
                    question_id=question_id,
                    display_order=idx + 1
                )
                db.add(quiz_link)
    
    await db.commit()
    await db.refresh(quiz)
    
    # Get updated question count
    count_stmt = select(func.count(McqQuizQuestionLink.quiz_id)).where(
        McqQuizQuestionLink.quiz_id == quiz_id
    )
    count_result = await db.execute(count_stmt)
    question_count = count_result.scalar()
    
    result = McqQuizRead.from_orm(quiz)
    result.question_count = question_count
    return result


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a quiz."""
    stmt = select(McqQuiz).where(McqQuiz.id == quiz_id)
    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check ownership or admin rights
    if quiz.user_id != current_user.id and current_user.role.value != "admin":
        # If it's a community quiz, check if user is admin/moderator
        if quiz.community_id:
            community_service = CommunityService(db)
            try:
                await community_service._check_admin_or_moderator(current_user, quiz.community_id)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to delete this quiz"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this quiz"
            )
    
    # Delete question links first
    delete_links_stmt = delete(McqQuizQuestionLink).where(
        McqQuizQuestionLink.quiz_id == quiz_id
    )
    await db.execute(delete_links_stmt)
    
    # Delete active sessions for this quiz
    delete_sessions_stmt = delete(QuizSession).where(
        and_(
            QuizSession.quiz_id == quiz_id,
            QuizSession.completed_at.is_(None)
        )
    )
    await db.execute(delete_sessions_stmt)
    
    await db.delete(quiz)
    await db.commit()


@router.post("/{quiz_id}/sessions", response_model=QuizSessionRead, status_code=status.HTTP_201_CREATED)
async def start_quiz_session(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Start a new quiz session."""
    stmt = select(McqQuiz).where(McqQuiz.id == quiz_id)
    result = await db.execute(stmt)
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check access permissions
    if not quiz.is_public and quiz.user_id != current_user.id:
        # Check if this is a community quiz and user is a member
        if quiz.community_id:
            member_stmt = select(CommunityMember).where(
                and_(
                    CommunityMember.community_id == quiz.community_id,
                    CommunityMember.user_id == current_user.id
                )
            )
            member_result = await db.execute(member_stmt)
            member = member_result.scalar_one_or_none()
            
            if not member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this quiz"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this quiz"
            )
    
    # Get question count for this quiz
    count_stmt = select(func.count(McqQuizQuestionLink.quiz_id)).where(
        McqQuizQuestionLink.quiz_id == quiz_id
    )
    count_result = await db.execute(count_stmt)
    question_count = count_result.scalar()
    
    # Create new session
    session = QuizSession(
        user_id=current_user.id,
        quiz_id=quiz_id,
        total_questions=question_count,
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    # Add quiz title for response
    session_dict = {
        "id": session.id,
        "user_id": session.user_id,
        "quiz_id": session.quiz_id,
        "quiz_title": quiz.title,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "score": session.score,
        "total_questions": session.total_questions,
        "answers_json": session.answers_json,
        "time_taken_seconds": session.time_taken_seconds
    }
    
    return QuizSessionRead(**session_dict)


@router.post("/sessions/{session_id}/submit", response_model=QuizSessionRead)
async def submit_quiz_session(
    session_id: int,
    submission: QuizSessionSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Submit answers for a quiz session."""
    stmt = select(QuizSession).where(QuizSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this quiz session"
        )
    
    # Check if already completed
    if session.completed_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz session already completed"
        )
    
    # Calculate score
    score = 0
    answer_details = {}
    
    for answer in submission.answers:
        question_stmt = select(McqQuestion).where(McqQuestion.id == answer.question_id)
        question_result = await db.execute(question_stmt)
        question = question_result.scalar_one_or_none()
        
        if question:
            is_correct = question.correct_option == answer.selected_option.value
            if is_correct:
                score += 1
            
            answer_details[str(answer.question_id)] = {
                "selected": answer.selected_option.value,
                "correct": question.correct_option,
                "is_correct": is_correct
            }
    
    # Update session
    session.score = score
    session.completed_at = datetime.now(timezone.utc)
    session.answers_json = answer_details
    session.time_taken_seconds = int((session.completed_at - session.started_at).total_seconds())
    
    await db.commit()
    await db.refresh(session)
    
    return session 