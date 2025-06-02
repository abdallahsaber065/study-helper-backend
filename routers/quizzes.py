"""
Router for MCQ and Quiz functionality.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from db_config import get_db
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
    db: Session = Depends(get_db)
):
    """Generate MCQs from files using AI."""
    # Check community access if community_id is provided
    if request.community_id:
        community_service = CommunityService(db)
        try:
            community_service._check_admin_or_moderator(current_user, request.community_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required to create community MCQs"
            )
    
    mcq_service = MCQGeneratorService(db)
    result = await mcq_service.generate_mcqs(request, current_user)
    return result


# ============ Quiz Endpoints ============

@router.post("", response_model=McqQuizRead, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    quiz: McqQuizCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new quiz."""
    # Check community access if community_id is provided
    if quiz.community_id:
        community_service = CommunityService(db)
        try:
            community_service._check_admin_or_moderator(current_user, quiz.community_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required to create community quizzes"
            )
    
    # Create the quiz
    quiz_data = quiz.dict(exclude={"question_ids"})
    db_quiz = McqQuiz(**quiz_data, user_id=current_user.id)
    db.add(db_quiz)
    db.commit()
    db.refresh(db_quiz)
    
    # Link with questions
    if quiz.question_ids:
        for idx, question_id in enumerate(quiz.question_ids):
            question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
            if question:
                quiz_link = McqQuizQuestionLink(
                    quiz_id=db_quiz.id,
                    question_id=question_id,
                    display_order=idx + 1
                )
                db.add(quiz_link)
        db.commit()
    
    # Add question count
    question_count = db.query(McqQuizQuestionLink).filter(
        McqQuizQuestionLink.quiz_id == db_quiz.id
    ).count()
    
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
    db: Session = Depends(get_db)
):
    """List quizzes with filtering options."""
    query = db.query(McqQuiz).filter(McqQuiz.is_active == True)
    
    if my_quizzes:
        query = query.filter(McqQuiz.user_id == current_user.id)
    elif is_public is not None:
        query = query.filter(McqQuiz.is_public == is_public)
    else:
        # Show public quizzes and user's own quizzes
        query = query.filter(
            (McqQuiz.is_public == True) | (McqQuiz.user_id == current_user.id)
        )
    
    quizzes = query.offset(skip).limit(limit).all()
    
    # Add question counts
    result = []
    for quiz in quizzes:
        question_count = db.query(McqQuizQuestionLink).filter(
            McqQuizQuestionLink.quiz_id == quiz.id
        ).count()
        
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
    db: Session = Depends(get_db)
):
    """List user's quiz sessions."""
    sessions = db.query(QuizSession).filter(
        QuizSession.user_id == current_user.id
    ).order_by(QuizSession.started_at.desc()).offset(skip).limit(limit).all()
    
    return sessions


@router.get("/sessions/{session_id}", response_model=QuizSessionRead)
async def get_quiz_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get quiz session details."""
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
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
    db: Session = Depends(get_db)
):
    """Edit a quiz session's answers."""
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership
    if session.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this quiz session"
        )
    
    # Calculate new score
    correct_answers = 0
    answer_details = {}
    
    for answer in submission.answers:
        question = db.query(McqQuestion).filter(McqQuestion.id == answer.question_id).first()
        if question:
            is_correct = question.correct_option == answer.selected_option.value
            if is_correct:
                correct_answers += 1
            
            answer_details[str(answer.question_id)] = {
                "selected": answer.selected_option.value,
                "correct": question.correct_option,
                "is_correct": is_correct
            }
    
    # Update session
    session.score = correct_answers
    session.answers_json = answer_details
    
    # If session wasn't completed yet, mark it as completed now
    if not session.completed_at:
        session.completed_at = datetime.now(timezone.utc)
        session.time_taken_seconds = int((session.completed_at - session.started_at).total_seconds())
    
    db.commit()
    db.refresh(session)
    
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a quiz session."""
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    
    # Check ownership or admin rights
    if session.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this quiz session"
        )
    
    db.delete(session)
    db.commit()


@router.get("/{quiz_id}", response_model=McqQuizWithQuestions)
async def get_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific quiz with its questions."""
    quiz = db.query(McqQuiz).filter(McqQuiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check access permissions
    if not quiz.is_public and quiz.user_id != current_user.id:
        # Check if this is a community quiz and user is a member
        if quiz.community_id:
            member = db.query(CommunityMember).filter(
                CommunityMember.community_id == quiz.community_id,
                CommunityMember.user_id == current_user.id
            ).first()
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
    quiz_questions = db.query(McqQuizQuestionLink).filter(
        McqQuizQuestionLink.quiz_id == quiz_id
    ).order_by(McqQuizQuestionLink.display_order).all()
    
    questions = []
    for quiz_question in quiz_questions:
        question = db.query(McqQuestion).options(
            joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
        ).filter(McqQuestion.id == quiz_question.question_id).first()
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
    db: Session = Depends(get_db)
):
    """Update a quiz."""
    quiz = db.query(McqQuiz).filter(McqQuiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check ownership or admin rights
    if quiz.user_id != current_user.id and current_user.role.value != "admin":
        # If it's a community quiz, check if user is admin/moderator
        if quiz.community_id:
            community_service = CommunityService(db)
            try:
                community_service._check_admin_or_moderator(quiz.community_id, current_user.id)
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
    
    quiz.updated_at = datetime.now(timezone.utc)
    
    # Update quiz questions if provided
    if quiz_update.question_ids is not None:
        # Delete existing question links
        db.query(McqQuizQuestionLink).filter(McqQuizQuestionLink.quiz_id == quiz_id).delete()
        
        # Add new question links
        for i, question_id in enumerate(quiz_update.question_ids):
            # Verify question exists
            question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
            if not question:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Question with ID {question_id} not found"
                )
            
            # Add question link with order
            link = McqQuizQuestionLink(
                quiz_id=quiz_id,
                question_id=question_id,
                display_order=i
            )
            db.add(link)
    
    db.commit()
    db.refresh(quiz)
    
    # Update quiz question count
    question_count = db.query(McqQuizQuestionLink).filter(McqQuizQuestionLink.quiz_id == quiz_id).count()
    quiz.question_count = question_count
    db.commit()
    
    return quiz


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a quiz."""
    quiz = db.query(McqQuiz).filter(McqQuiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check ownership or admin rights
    if quiz.user_id != current_user.id and current_user.role.value != "admin":
        # If it's a community quiz, check if user is admin/moderator
        if quiz.community_id:
            community_service = CommunityService(db)
            try:
                community_service._check_admin_or_moderator(quiz.community_id, current_user.id)
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
    
    # First delete all quiz-question links
    db.query(McqQuizQuestionLink).filter(McqQuizQuestionLink.quiz_id == quiz_id).delete()
    
    # Check if there are any active sessions for this quiz
    active_sessions = db.query(QuizSession).filter(
        QuizSession.quiz_id == quiz_id,
        QuizSession.completed_at == None
    ).all()
    
    # Delete sessions if any exist
    if active_sessions:
        for session in active_sessions:
            db.delete(session)
    
    # Finally delete the quiz
    db.delete(quiz)
    db.commit()


@router.post("/{quiz_id}/sessions", response_model=QuizSessionRead, status_code=status.HTTP_201_CREATED)
async def start_quiz_session(
    quiz_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new quiz session."""
    quiz = db.query(McqQuiz).filter(McqQuiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    
    # Check access permissions
    if not quiz.is_public and quiz.user_id != current_user.id:
        # Check if this is a community quiz and user is a member
        if quiz.community_id:
            member = db.query(CommunityMember).filter(
                CommunityMember.community_id == quiz.community_id,
                CommunityMember.user_id == current_user.id
            ).first()
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
    
    # Get question count
    question_count = db.query(McqQuizQuestionLink).filter(
        McqQuizQuestionLink.quiz_id == quiz_id
    ).count()
    
    if question_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz has no questions"
        )
    
    # Create quiz session
    session = QuizSession(
        user_id=current_user.id,
        quiz_id=quiz_id,
        total_questions=question_count,
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return session


@router.post("/sessions/{session_id}/submit", response_model=QuizSessionRead)
async def submit_quiz_session(
    session_id: int,
    submission: QuizSessionSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit answers for a quiz session."""
    session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
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
    correct_answers = 0
    answer_details = {}
    
    for answer in submission.answers:
        question = db.query(McqQuestion).filter(McqQuestion.id == answer.question_id).first()
        if question:
            is_correct = question.correct_option == answer.selected_option.value
            if is_correct:
                correct_answers += 1
            
            answer_details[str(answer.question_id)] = {
                "selected": answer.selected_option.value,
                "correct": question.correct_option,
                "is_correct": is_correct
            }
    
    # Update session
    session.completed_at = datetime.now(timezone.utc)
    session.score = correct_answers
    session.answers_json = answer_details
    session.time_taken_seconds = int((session.completed_at - session.started_at).total_seconds())
    
    db.commit()
    db.refresh(session)
    
    # Send notification about quiz completion
    notification_service = NotificationService(db)
    notification_service.notify_quiz_result(
        user_id=current_user.id,
        quiz_id=session.quiz_id,
        score=correct_answers,
        total_questions=session.total_questions
    )
    
    return session 