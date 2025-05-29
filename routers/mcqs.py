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
    McqQuiz, McqQuizQuestionLink, QuizSession
)
from schemas.mcq import (
    # Tag schemas
    QuestionTagCreate, QuestionTagRead, QuestionTagUpdate,
    # Question schemas  
    McqQuestionCreate, McqQuestionRead, McqQuestionUpdate,
    # Quiz schemas
    McqQuizCreate, McqQuizRead, McqQuizUpdate, McqQuizWithQuestions,
    # Session schemas
    QuizSessionCreate, QuizSessionRead, QuizSessionSubmit,
    # AI generation schemas
    MCQGenerationRequest
)
from services.mcq_service import MCQGeneratorService

router = APIRouter(prefix="/mcqs", tags=["MCQs and Quizzes"])


def _convert_question_to_read(question: McqQuestion) -> McqQuestionRead:
    """Convert a question with its tag links to McqQuestionRead format."""
    question_dict = {
        "id": question.id,
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_option": question.correct_option,
        "explanation": question.explanation,
        "hint": question.hint,
        "difficulty_level": question.difficulty_level,
        "user_id": question.user_id,
        "created_at": question.created_at,
        "updated_at": question.updated_at,
        "tags": [QuestionTagRead.from_orm(link.tag) for link in question.tag_links] if hasattr(question, 'tag_links') else []
    }
    return McqQuestionRead(**question_dict)


# ============ Question Tag Endpoints ============

@router.post("/tags", response_model=QuestionTagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag: QuestionTagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new question tag."""
    # Check if tag already exists
    existing_tag = db.query(QuestionTag).filter(QuestionTag.name == tag.name).first()
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag with this name already exists"
        )
    
    db_tag = QuestionTag(**tag.dict())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag


@router.get("/tags", response_model=List[QuestionTagRead])
async def list_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all question tags."""
    query = db.query(QuestionTag)
    
    if search:
        query = query.filter(QuestionTag.name.ilike(f"%{search}%"))
    
    tags = query.offset(skip).limit(limit).all()
    return tags


@router.get("/tags/{tag_id}", response_model=QuestionTagRead)
async def get_tag(tag_id: int, db: Session = Depends(get_db)):
    """Get a specific question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.put("/tags/{tag_id}", response_model=QuestionTagRead)
async def update_tag(
    tag_id: int,
    tag_update: QuestionTagUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    
    # Check if new name conflicts with existing tag
    if tag_update.name and tag_update.name != tag.name:
        existing_tag = db.query(QuestionTag).filter(QuestionTag.name == tag_update.name).first()
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tag with this name already exists"
            )
    
    update_data = tag_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    
    tag.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    
    db.delete(tag)
    db.commit()


# ============ MCQ Question Endpoints ============

@router.post("/questions", response_model=McqQuestionRead, status_code=status.HTTP_201_CREATED)
async def create_question(
    question: McqQuestionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new MCQ question."""
    # Create the question
    question_data = question.dict(exclude={"tag_ids"})
    db_question = McqQuestion(**question_data, user_id=current_user.id)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    # Link with tags
    if question.tag_ids:
        for tag_id in question.tag_ids:
            tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
            if tag:
                tag_link = McqQuestionTagLink(question_id=db_question.id, tag_id=tag_id)
                db.add(tag_link)
        db.commit()
    
    # Reload with tags
    db_question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == db_question.id).first()
    
    return _convert_question_to_read(db_question)


@router.get("/questions", response_model=List[McqQuestionRead])
async def list_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag_id: Optional[int] = Query(None),
    difficulty: Optional[str] = Query(None),
    my_questions: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List MCQ questions with filtering options."""
    query = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    )
    
    if my_questions:
        query = query.filter(McqQuestion.user_id == current_user.id)
    
    if tag_id:
        query = query.join(McqQuestionTagLink).filter(McqQuestionTagLink.tag_id == tag_id)
    
    if difficulty:
        query = query.filter(McqQuestion.difficulty_level == difficulty)
    
    questions = query.offset(skip).limit(limit).all()
    return [_convert_question_to_read(q) for q in questions]


@router.get("/questions/{question_id}", response_model=McqQuestionRead)
async def get_question(
    question_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific MCQ question."""
    question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == question_id).first()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    return _convert_question_to_read(question)


@router.put("/questions/{question_id}", response_model=McqQuestionRead)
async def update_question(
    question_id: int,
    question_update: McqQuestionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an MCQ question."""
    question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this question"
        )
    
    # Update question fields
    update_data = question_update.dict(exclude_unset=True, exclude={"tag_ids"})
    for field, value in update_data.items():
        setattr(question, field, value)
    
    question.updated_at = datetime.now(timezone.utc)
    
    # Update tag associations if provided
    if question_update.tag_ids is not None:
        # Remove existing tag links
        db.query(McqQuestionTagLink).filter(McqQuestionTagLink.question_id == question_id).delete()
        
        # Add new tag links
        for tag_id in question_update.tag_ids:
            tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
            if tag:
                tag_link = McqQuestionTagLink(question_id=question_id, tag_id=tag_id)
                db.add(tag_link)
    
    db.commit()
    db.refresh(question)
    
    # Reload with tags
    question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == question_id).first()
    
    return _convert_question_to_read(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an MCQ question."""
    question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this question"
        )
    
    db.delete(question)
    db.commit()


# ============ AI MCQ Generation ============

@router.post("/generate")
async def generate_mcqs_from_files(
    request: MCQGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate MCQs from files using AI."""
    mcq_service = MCQGeneratorService(db)
    result = await mcq_service.generate_mcqs_from_files(request, current_user)
    return result


# ============ Quiz Endpoints ============

@router.post("/quizzes", response_model=McqQuizRead, status_code=status.HTTP_201_CREATED)
async def create_quiz(
    quiz: McqQuizCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new quiz."""
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


@router.get("/quizzes", response_model=List[McqQuizRead])
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


@router.get("/quizzes/{quiz_id}", response_model=McqQuizWithQuestions)
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


# ============ Quiz Session Management ============

@router.post("/quizzes/{quiz_id}/sessions", response_model=QuizSessionRead, status_code=status.HTTP_201_CREATED)
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
    
    return session


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