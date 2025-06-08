"""
MCQ Generation Service with AI integration.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from pydantic import BaseModel

from core.logging import get_logger
from models.models import (
    PhysicalFile, McqQuestion, QuestionTag, McqQuestionTagLink, 
    McqQuiz, McqQuizQuestionLink, User
)
from schemas.mcq import (
    MCQGenerationRequest, MCQGenerationResponse, MCQGenerationQuestion,
    McqQuestionCreate, McqQuizCreate, McqQuizRead
)
from services.ai_manager import AIManager
from models.models import AiProviderEnum
from core.exceptions import AIServiceException

# Initialize logger
logger = get_logger("mcq_service")

class MCQGeneratorService:
    """Service for generating MCQs using AI."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_manager = AIManager(db)
        
    def _get_generation_prompt(
        self, 
        num_questions: int, 
        difficulty_level: Optional[str] = None,
        custom_instructions: Optional[str] = None
    ) -> str:
        """Generate the prompt for MCQ creation."""

        base_prompt = f"""Generate a set of EXACTLY num_questions={num_questions} multiple choice questions (MCQs) based on the provided document(s). 

**IMPORTANT: You MUST generate EXACTLY num_questions={num_questions} questions. This requirement overrides any conflicting instructions.**

**Requirements:**
- Create EXACTLY num_questions={num_questions} questions - no more, no less
- Ensure questions test different concepts from the material"""

        if difficulty_level:
            base_prompt += f"\n- Target difficulty level: {difficulty_level}"

        if custom_instructions:
            base_prompt += f"\n\n**Additional Instructions:**\n{custom_instructions}"

        return base_prompt

    async def generate_mcqs(
        self, 
        request: MCQGenerationRequest, 
        user: User
    ) -> dict:
        """
        Generate MCQs from files using AI.
        
        Args:
            request: The MCQ generation request
            user: The authenticated user
            
        Returns:
            dict: Contains generated questions and optionally created quiz
        """
        logger.info("MCQ generation started", 
                   user_id=user.id, 
                   username=user.username,
                   num_questions=request.num_questions,
                   file_count=len(request.physical_file_ids),
                   difficulty=request.difficulty_level.value if request.difficulty_level else None,
                   create_quiz=request.create_quiz)
        
        # Validate files exist and user has access
        for file_id in request.physical_file_ids:
            file_stmt = select(PhysicalFile).where(PhysicalFile.id == file_id)
            file_result = await self.db.execute(file_stmt)
            file_record = file_result.scalar_one_or_none()
            
            if not file_record:
                logger.warning("File not found for MCQ generation", 
                              user_id=user.id, 
                              file_id=file_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File with ID {file_id} not found"
                )

        logger.debug("File validation completed", 
                    user_id=user.id, 
                    validated_files=request.physical_file_ids)

        # Generate system instruction and prompt
        try:
            with open("prompts/mcq/system_instruction.md", "r", encoding="utf-8") as file:
                system_instruction = file.read()
                
            prompt = self._get_generation_prompt(
                request.num_questions,
                request.difficulty_level.value if request.difficulty_level else None,
                request.custom_instructions
            )
            
            logger.debug("Prompt and system instruction prepared", 
                        user_id=user.id, 
                        prompt_length=len(prompt),
                        system_instruction_length=len(system_instruction))
        except FileNotFoundError as e:
            logger.error("MCQ prompt template not found", 
                        user_id=user.id, 
                        error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MCQ generation template not found"
            )

        try:
            logger.info("Sending request to AI manager", 
                       user_id=user.id, 
                       file_ids=request.physical_file_ids)
            
            # Generate MCQs using AI
            response = (
                await self.ai_manager.generate_content_with_gemini(
                    user_id=user.id,
                    prompt=prompt,
                    physical_file_ids=request.physical_file_ids,
                    response_schema=MCQGenerationResponse,
                    system_instruction=system_instruction,
                )
            )   

            logger.info("AI response received", 
                       user_id=user.id, 
                       response_type=type(response).__name__)

            # If response is text (parsing failed), try to handle it
            if not isinstance(response, MCQGenerationResponse):
                logger.error("AI response parsing failed", 
                            user_id=user.id, 
                            response_type=type(response).__name__)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI response could not be parsed. Please try again."
                )

            # Extract the MCQ set
            mcq_set = response.mcq_set
            logger.info("MCQ set extracted from AI response", 
                       user_id=user.id, 
                       questions_count=len(mcq_set.questions),
                       mcq_title=mcq_set.title)

            # Create or get tags
            tag_objects = []
            for tag_name in mcq_set.tags:
                tag_stmt = select(QuestionTag).where(QuestionTag.name == tag_name)
                tag_result = await self.db.execute(tag_stmt)
                tag = tag_result.scalar_one_or_none()
                
                if not tag:
                    tag = QuestionTag(name=tag_name, description=f"Auto-generated tag: {tag_name}")
                    self.db.add(tag)
                    await self.db.commit()
                    await self.db.refresh(tag)
                    logger.debug("Created new question tag", 
                                user_id=user.id, 
                                tag_name=tag_name, 
                                tag_id=tag.id)
                else:
                    logger.debug("Using existing question tag", 
                                user_id=user.id, 
                                tag_name=tag_name, 
                                tag_id=tag.id)
                tag_objects.append(tag)

            logger.info("Question tags processed", 
                       user_id=user.id, 
                       total_tags=len(tag_objects),
                       tag_names=[tag.name for tag in tag_objects])

            # Create MCQ questions in database
            created_questions = []
            for idx, mcq_question in enumerate(mcq_set.questions):
                try:
                    # Create the question
                    question = McqQuestion(
                        question_text=mcq_question.question,
                        option_a=mcq_question.options.A,
                        option_b=mcq_question.options.B,
                        option_c=mcq_question.options.C,
                        option_d=mcq_question.options.D,
                        correct_option=mcq_question.correct_answer.value,
                        explanation=mcq_question.explanation,
                        hint=mcq_question.hint,
                        difficulty_level=mcq_question.difficulty,
                        user_id=user.id
                    )
                    self.db.add(question)
                    await self.db.commit()
                    await self.db.refresh(question)

                    # Link with tags
                    for tag in tag_objects:
                        tag_link = McqQuestionTagLink(
                            question_id=question.id,
                            tag_id=tag.id
                        )
                        self.db.add(tag_link)

                    created_questions.append(question)
                    logger.debug("MCQ question created", 
                                user_id=user.id, 
                                question_id=question.id,
                                question_number=idx + 1,
                                difficulty=mcq_question.difficulty)
                    
                except SQLAlchemyError as e:
                    logger.error("Failed to create MCQ question", 
                                user_id=user.id, 
                                question_number=idx + 1,
                                error=str(e))
                    await self.db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to create question {idx + 1}"
                    )

            await self.db.commit()
            logger.info("All MCQ questions created successfully", 
                       user_id=user.id, 
                       questions_created=len(created_questions))

            result = {
                "message": "MCQs generated successfully",
                "questions_created": len(created_questions),
                "question_ids": [q.id for q in created_questions],
                "generated_mcq_set": mcq_set,
                "quiz": None
            }

            # Create quiz if requested
            if request.create_quiz:
                logger.info("Creating quiz from generated MCQs", 
                           user_id=user.id, 
                           questions_count=len(created_questions))
                
                quiz_title = request.quiz_title or mcq_set.title
                quiz_description = request.quiz_description or mcq_set.description

                try:
                    quiz = McqQuiz(
                        title=quiz_title,
                        description=quiz_description,
                        difficulty_level=mcq_set.difficulty_level,
                        user_id=user.id,
                        is_active=True,
                        is_public=request.community_id is None,
                        community_id=request.community_id
                    )
                    self.db.add(quiz)
                    await self.db.commit()
                    await self.db.refresh(quiz)

                    # Link questions to quiz
                    for idx, question in enumerate(created_questions):
                        quiz_link = McqQuizQuestionLink(
                            quiz_id=quiz.id,
                            question_id=question.id,
                            display_order=idx + 1
                        )
                        self.db.add(quiz_link)

                    await self.db.commit()
                    
                    logger.info("Quiz created successfully", 
                               user_id=user.id, 
                               quiz_id=quiz.id,
                               quiz_title=quiz.title,
                               community_id=request.community_id)

                    # Send notifications for community content
                    if request.community_id:
                        logger.info("Sending community notifications for new quiz", 
                                   user_id=user.id, 
                                   quiz_id=quiz.id,
                                   community_id=request.community_id)
                        
                        from services.notification_service import NotificationService
                        from models.models import ContentTypeEnum
                        
                        notification_service = NotificationService(self.db)
                        await notification_service.notify_new_community_content(
                            content_type=ContentTypeEnum.quiz,
                            content_id=quiz.id,
                            community_id=request.community_id,
                            actor_id=user.id,
                            content_title=quiz.title
                        )

                    result["quiz"] = {
                        "id": quiz.id,
                        "title": quiz.title,
                        "description": quiz.description,
                        "question_count": len(created_questions)
                    }
                    
                except SQLAlchemyError as e:
                    logger.error("Failed to create quiz", 
                                user_id=user.id, 
                                error=str(e))
                    await self.db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create quiz from generated questions"
                    )

            logger.info("MCQ generation completed successfully", 
                       user_id=user.id, 
                       questions_created=len(created_questions),
                       quiz_created=bool(request.create_quiz),
                       total_time="calculated_elsewhere")
            
            return result

        except AIServiceException as e:
            logger.error("AI service error during MCQ generation", 
                        user_id=user.id, 
                        error=str(e),
                        provider=e.provider if hasattr(e, 'provider') else 'unknown')
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {str(e)}"
            )
        except Exception as e:
            logger.error("Unexpected error during MCQ generation", 
                        user_id=user.id, 
                        error=str(e), 
                        error_type=type(e).__name__,
                        exc_info=True)
            await self.db.rollback()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during MCQ generation"
            ) 
