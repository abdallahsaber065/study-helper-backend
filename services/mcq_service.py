"""
MCQ Generation Service using AI integration.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
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


class MCQGeneratorService:
    """Service for generating MCQs using AI."""

    def __init__(self, db: Session):
        self.db = db
        self.ai_manager = AIManager(db)
        
    def _get_generation_prompt(
        self, 
        num_questions: int, 
        difficulty_level: Optional[str] = None,
        custom_instructions: Optional[str] = None
    ) -> str:
        """Generate the prompt for MCQ creation."""

        base_prompt = f"""Generate a set of {num_questions} multiple choice questions (MCQs) based on the provided document(s). 

**Requirements:**
- Create exactly {num_questions} questions
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
        # Validate files exist and user has access
        for file_id in request.physical_file_ids:
            file_record = self.db.query(PhysicalFile).filter(PhysicalFile.id == file_id).first()
            if not file_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File with ID {file_id} not found"
                )

        # Generate system instruction and prompt
        with open("prompts/mcq/system_instruction.md", "r", encoding="utf-8") as file:
            system_instruction = file.read()
            
        prompt = self._get_generation_prompt(
            request.num_questions,
            request.difficulty_level.value if request.difficulty_level else None,
            request.custom_instructions
        )

        try:
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

            # If response is text (parsing failed), try to handle it
            if not isinstance(response, MCQGenerationResponse):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AI response could not be parsed. Please try again."
                )

            # Extract the MCQ set
            mcq_set = response.mcq_set

            # Create or get tags
            tag_objects = []
            for tag_name in mcq_set.tags:
                tag = self.db.query(QuestionTag).filter(QuestionTag.name == tag_name).first()
                if not tag:
                    tag = QuestionTag(name=tag_name, description=f"Auto-generated tag: {tag_name}")
                    self.db.add(tag)
                    self.db.commit()
                    self.db.refresh(tag)
                tag_objects.append(tag)

            # Create MCQ questions in database
            created_questions = []
            for mcq_question in mcq_set.questions:
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
                self.db.commit()
                self.db.refresh(question)

                # Link with tags
                for tag in tag_objects:
                    tag_link = McqQuestionTagLink(
                        question_id=question.id,
                        tag_id=tag.id
                    )
                    self.db.add(tag_link)

                created_questions.append(question)

            self.db.commit()

            result = {
                "message": "MCQs generated successfully",
                "questions_created": len(created_questions),
                "question_ids": [q.id for q in created_questions],
                "generated_mcq_set": mcq_set,
                "quiz": None
            }

            # Create quiz if requested
            if request.create_quiz:
                quiz_title = request.quiz_title or mcq_set.title
                quiz_description = request.quiz_description or mcq_set.description

                quiz = McqQuiz(
                    title=quiz_title,
                    description=quiz_description,
                    difficulty_level=mcq_set.difficulty_level,
                    user_id=user.id,
                    is_active=True,
                    is_public=False
                )
                self.db.add(quiz)
                self.db.commit()
                self.db.refresh(quiz)

                # Link questions to quiz
                for idx, question in enumerate(created_questions):
                    quiz_link = McqQuizQuestionLink(
                        quiz_id=quiz.id,
                        question_id=question.id,
                        display_order=idx + 1
                    )
                    self.db.add(quiz_link)

                self.db.commit()

                result["quiz"] = {
                    "id": quiz.id,
                    "title": quiz.title,
                    "description": quiz.description,
                    "question_count": len(created_questions)
                }

            return result

        except Exception as e:
            self.db.rollback()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate MCQs: {str(e)}"
            ) 
