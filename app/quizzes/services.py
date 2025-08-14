"""
Service layer for quiz operations, analytics, and business logic.

This module provides comprehensive services for:
- Quiz creation, management, and lifecycle operations
- Question and answer management with quality scoring
- Quiz attempt tracking and performance analytics
- Advanced filtering, searching, and reporting capabilities
- Export functionality and data analysis
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_, text
from sqlalchemy.orm import Session, selectinload

from .models import Quiz, Question, Answer, QuizAttempt, QuestionResponse
from .schemas import (
    QuizFilters, QuizListResponse, QuizResponse, QuizAnalytics,
    QuizAttemptResponse, QuizAttemptListResponse, QuestionResponse as QuestionResponseSchema,
    AnswerResponse, QuizMetrics
)
from ..files.models import FileMetadata
from ..users.models import User

logger = logging.getLogger(__name__)


class QuizService:
    """Service class for quiz operations and management."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_quiz(
        self,
        user_id: int,
        file_id: str,
        title: str,
        description: Optional[str] = None,
        difficulty_level: str = "intermediate",
        question_count: int = 10,
        **kwargs
    ) -> Quiz:
        """Create a new quiz record."""
        
        # Verify file exists and belongs to user
        file_metadata = self.db.query(FileMetadata).filter(
            and_(
                FileMetadata.id == file_id,
                FileMetadata.user_id == user_id
            )
        ).first()
        
        if not file_metadata:
            raise ValueError("File not found or access denied")
        
        quiz = Quiz(
            user_id=user_id,
            file_id=file_id,
            title=title,
            description=description,
            difficulty_level=difficulty_level,
            question_count=question_count,
            **kwargs
        )
        
        self.db.add(quiz)
        self.db.commit()
        self.db.refresh(quiz)
        
        logger.info(f"Created quiz {quiz.id} for user {user_id}")
        return quiz
    
    def get_quiz(self, quiz_id: str, user_id: int, include_questions: bool = False) -> Optional[Quiz]:
        """Get a quiz by ID, ensuring user owns it."""
        
        query = self.db.query(Quiz).filter(
            and_(
                Quiz.id == quiz_id,
                Quiz.user_id == user_id,
                Quiz.deleted_at.is_(None)
            )
        )
        
        if include_questions:
            query = query.options(
                selectinload(Quiz.questions).selectinload(Question.answers)
            )
        
        return query.first()
    
    def get_quizzes(
        self,
        user_id: int,
        filters: QuizFilters
    ) -> QuizListResponse:
        """Get paginated list of user's quizzes with filters."""
        
        query = self.db.query(Quiz).filter(
            and_(
                Quiz.user_id == user_id,
                Quiz.deleted_at.is_(None)
            )
        )
        
        # Apply filters
        if filters.status:
            query = query.filter(Quiz.status.in_([s.value for s in filters.status]))
        
        if filters.difficulty_level:
            query = query.filter(Quiz.difficulty_level.in_([d.value for d in filters.difficulty_level]))
        
        if filters.ai_provider:
            query = query.filter(Quiz.ai_provider.in_([p.value for p in filters.ai_provider]))
        
        if filters.created_after:
            query = query.filter(Quiz.created_at >= filters.created_after)
        
        if filters.created_before:
            query = query.filter(Quiz.created_at <= filters.created_before)
        
        if filters.min_quality_score is not None:
            query = query.filter(Quiz.quality_score >= filters.min_quality_score)
        
        if filters.has_user_rating is not None:
            if filters.has_user_rating:
                query = query.filter(Quiz.user_rating.is_not(None))
            else:
                query = query.filter(Quiz.user_rating.is_(None))
        
        if filters.topic:
            query = query.filter(Quiz.topics_covered.contains(filters.topic))
        
        if filters.learning_objective:
            query = query.filter(Quiz.learning_objectives.contains(filters.learning_objective))
        
        if filters.question_count_min:
            query = query.filter(Quiz.question_count >= filters.question_count_min)
        
        if filters.question_count_max:
            query = query.filter(Quiz.question_count <= filters.question_count_max)
        
        # Search functionality
        if filters.search_query:
            search_term = f"%{filters.search_query}%"
            query = query.filter(
                or_(
                    Quiz.title.ilike(search_term),
                    Quiz.description.ilike(search_term),
                    Quiz.topics_covered.ilike(search_term)
                )
            )
        
        # Count total results before pagination
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(Quiz, filters.sort_by, Quiz.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)
        
        # Apply pagination
        offset = (filters.page - 1) * filters.page_size
        quizzes = query.offset(offset).limit(filters.page_size).all()
        
        # Convert to response schema
        quiz_responses = []
        for quiz in quizzes:
            metrics = self._calculate_quiz_metrics(quiz)
            quiz_response = QuizResponse(
                id=quiz.id,
                user_id=quiz.user_id,
                file_id=quiz.file_id,
                title=quiz.title,
                description=quiz.description,
                difficulty_level=quiz.difficulty_level,
                question_count=quiz.question_count,
                estimated_time_minutes=quiz.estimated_time_minutes,
                time_limit_minutes=quiz.time_limit_minutes,
                topics_covered=json.loads(quiz.topics_covered) if quiz.topics_covered else [],
                learning_objectives=json.loads(quiz.learning_objectives) if quiz.learning_objectives else [],
                ai_provider=quiz.ai_provider,
                ai_model_used=quiz.ai_model_used,
                prompt_template=quiz.prompt_template,
                status=quiz.status,
                progress_percentage=quiz.progress_percentage,
                error_message=quiz.error_message,
                quality_score=quiz.quality_score,
                user_rating=quiz.user_rating,
                user_feedback=quiz.user_feedback,
                shuffle_questions=quiz.shuffle_questions,
                shuffle_answers=quiz.shuffle_answers,
                show_correct_answers=quiz.show_correct_answers,
                allow_retries=quiz.allow_retries,
                max_attempts=quiz.max_attempts,
                passing_score=quiz.passing_score,
                metrics=metrics,
                created_at=quiz.created_at,
                updated_at=quiz.updated_at,
                completed_at=quiz.completed_at,
            )
            quiz_responses.append(quiz_response)
        
        # Calculate pagination metadata
        total_pages = (total + filters.page_size - 1) // filters.page_size
        
        # Generate summary statistics
        summary_stats = self._calculate_summary_stats(user_id, filters)
        
        return QuizListResponse(
            quizzes=quiz_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
            summary_stats=summary_stats
        )
    
    def update_quiz(
        self,
        quiz_id: str,
        user_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[Quiz]:
        """Update quiz metadata and settings."""
        
        quiz = self.get_quiz(quiz_id, user_id)
        if not quiz:
            return None
        
        # Update allowed fields
        allowed_fields = {
            'title', 'description', 'difficulty_level', 'time_limit_minutes',
            'shuffle_questions', 'shuffle_answers', 'show_correct_answers',
            'allow_retries', 'max_attempts', 'passing_score', 'user_rating',
            'user_feedback', 'difficulty_rating'
        }
        
        for field, value in update_data.items():
            if field in allowed_fields and hasattr(quiz, field):
                setattr(quiz, field, value)
        
        self.db.commit()
        self.db.refresh(quiz)
        
        logger.info(f"Updated quiz {quiz_id} for user {user_id}")
        return quiz
    
    def delete_quiz(self, quiz_id: str, user_id: int, soft_delete: bool = True) -> bool:
        """Delete a quiz (soft delete by default)."""
        
        quiz = self.get_quiz(quiz_id, user_id)
        if not quiz:
            return False
        
        if soft_delete:
            quiz.soft_delete()
            logger.info(f"Soft deleted quiz {quiz_id} for user {user_id}")
        else:
            self.db.delete(quiz)
            logger.info(f"Hard deleted quiz {quiz_id} for user {user_id}")
        
        self.db.commit()
        return True
    
    def archive_quiz(self, quiz_id: str, user_id: int) -> bool:
        """Archive a quiz."""
        
        quiz = self.get_quiz(quiz_id, user_id)
        if not quiz:
            return False
        
        quiz.archive()
        self.db.commit()
        
        logger.info(f"Archived quiz {quiz_id} for user {user_id}")
        return True
    
    def get_quiz_with_questions(
        self,
        quiz_id: str,
        user_id: int,
        shuffle_questions: Optional[bool] = None,
        shuffle_answers: Optional[bool] = None
    ) -> Optional[QuizResponse]:
        """Get quiz with all questions and answers, optionally shuffled."""
        
        quiz = self.get_quiz(quiz_id, user_id, include_questions=True)
        if not quiz:
            return None
        
        # Determine shuffling settings
        should_shuffle_questions = shuffle_questions if shuffle_questions is not None else quiz.shuffle_questions
        should_shuffle_answers = shuffle_answers if shuffle_answers is not None else quiz.shuffle_answers
        
        # Convert questions to response schema
        questions = []
        question_list = list(quiz.questions)
        
        if should_shuffle_questions:
            import random
            random.shuffle(question_list)
        else:
            question_list.sort(key=lambda q: q.order_index)
        
        for question in question_list:
            answers = []
            answer_list = list(question.answers)
            
            if should_shuffle_answers and question.question_type == "multiple_choice":
                import random
                random.shuffle(answer_list)
            else:
                answer_list.sort(key=lambda a: a.order_index)
            
            for answer in answer_list:
                answer_response = AnswerResponse(
                    id=answer.id,
                    answer_text=answer.answer_text,
                    order_index=answer.order_index,
                    is_correct=answer.is_correct if quiz.show_correct_answers else None,
                    explanation=answer.explanation if quiz.show_correct_answers else None,
                    points=answer.points,
                )
                answers.append(answer_response)
            
            question_response = QuestionResponseSchema(
                id=question.id,
                question_text=question.question_text,
                question_type=question.question_type,
                order_index=question.order_index,
                difficulty_level=question.difficulty_level,
                points=question.points,
                time_limit_seconds=question.time_limit_seconds,
                topic=question.topic,
                learning_objective=question.learning_objective,
                cognitive_level=question.cognitive_level,
                context=question.context,
                quality_score=question.quality_score,
                success_rate=question.success_rate,
                average_response_time=question.average_response_time,
                answers=answers,
            )
            questions.append(question_response)
        
        # Build complete quiz response
        metrics = self._calculate_quiz_metrics(quiz)
        
        return QuizResponse(
            id=quiz.id,
            user_id=quiz.user_id,
            file_id=quiz.file_id,
            title=quiz.title,
            description=quiz.description,
            difficulty_level=quiz.difficulty_level,
            question_count=quiz.question_count,
            estimated_time_minutes=quiz.estimated_time_minutes,
            time_limit_minutes=quiz.time_limit_minutes,
            topics_covered=json.loads(quiz.topics_covered) if quiz.topics_covered else [],
            learning_objectives=json.loads(quiz.learning_objectives) if quiz.learning_objectives else [],
            ai_provider=quiz.ai_provider,
            ai_model_used=quiz.ai_model_used,
            prompt_template=quiz.prompt_template,
            status=quiz.status,
            progress_percentage=quiz.progress_percentage,
            error_message=quiz.error_message,
            quality_score=quiz.quality_score,
            user_rating=quiz.user_rating,
            user_feedback=quiz.user_feedback,
            shuffle_questions=quiz.shuffle_questions,
            shuffle_answers=quiz.shuffle_answers,
            show_correct_answers=quiz.show_correct_answers,
            allow_retries=quiz.allow_retries,
            max_attempts=quiz.max_attempts,
            passing_score=quiz.passing_score,
            metrics=metrics,
            created_at=quiz.created_at,
            updated_at=quiz.updated_at,
            completed_at=quiz.completed_at,
            questions=questions,
        )
    
    def get_quiz_analytics(self, quiz_id: str, user_id: int) -> Optional[QuizAnalytics]:
        """Get comprehensive analytics for a quiz."""
        
        quiz = self.get_quiz(quiz_id, user_id)
        if not quiz:
            return None
        
        # Get all attempts for this quiz
        attempts = self.db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id
        ).all()
        
        if not attempts:
            return QuizAnalytics(
                quiz_id=quiz_id,
                total_attempts=0,
                unique_users=0,
                completion_rate=0.0,
                average_score=Decimal("0.0"),
                pass_rate=0.0,
                average_completion_time=0,
                time_distribution={},
                question_analytics=[],
                difficult_questions=[],
                easy_questions=[],
                performance_vs_difficulty={},
                suggested_improvements=[]
            )
        
        # Calculate basic statistics
        total_attempts = len(attempts)
        completed_attempts = len([a for a in attempts if a.status == "completed"])
        unique_users = len(set(a.user_id for a in attempts))
        completion_rate = (completed_attempts / total_attempts) * 100 if total_attempts > 0 else 0.0
        
        # Score statistics
        completed_scores = [a.percentage_score for a in attempts if a.percentage_score is not None]
        average_score = sum(completed_scores) / len(completed_scores) if completed_scores else Decimal("0.0")
        
        # Pass rate calculation
        passed_attempts = 0
        if quiz.passing_score:
            passed_attempts = len([score for score in completed_scores if score >= quiz.passing_score])
        pass_rate = (passed_attempts / len(completed_scores)) * 100 if completed_scores else 0.0
        
        # Time statistics
        completion_times = [a.time_spent_seconds for a in attempts if a.time_spent_seconds is not None]
        average_completion_time = int(sum(completion_times) / len(completion_times)) if completion_times else 0
        
        # Time distribution
        time_distribution = self._calculate_time_distribution(completion_times)
        
        # Question-level analytics
        question_analytics = self._calculate_question_analytics(quiz_id)
        
        # Identify difficult and easy questions
        difficult_questions = [qa["question_id"] for qa in question_analytics if qa.get("success_rate", 1.0) < 0.5]
        easy_questions = [qa["question_id"] for qa in question_analytics if qa.get("success_rate", 0.0) > 0.9]
        
        # Performance vs difficulty analysis
        performance_vs_difficulty = self._analyze_performance_vs_difficulty(quiz, attempts)
        
        # Generate improvement suggestions
        suggested_improvements = self._generate_improvement_suggestions(
            quiz, attempts, question_analytics, completion_rate, average_score
        )
        
        return QuizAnalytics(
            quiz_id=quiz_id,
            total_attempts=total_attempts,
            unique_users=unique_users,
            completion_rate=completion_rate,
            average_score=average_score,
            pass_rate=pass_rate if quiz.passing_score else None,
            average_completion_time=average_completion_time,
            time_distribution=time_distribution,
            question_analytics=question_analytics,
            difficult_questions=difficult_questions,
            easy_questions=easy_questions,
            learning_objectives_mastery=self._calculate_learning_objectives_mastery(quiz_id),
            topic_mastery=self._calculate_topic_mastery(quiz_id),
            common_misconceptions=self._identify_common_misconceptions(quiz_id),
            suggested_improvements=suggested_improvements,
            performance_vs_difficulty=performance_vs_difficulty,
            user_progression_patterns=self._analyze_user_progression(quiz_id)
        )
    
    def _calculate_quiz_metrics(self, quiz: Quiz) -> QuizMetrics:
        """Calculate comprehensive metrics for a quiz."""
        
        # Question type distribution
        question_type_counts = self.db.query(
            Question.question_type,
            func.count(Question.id)
        ).filter(Question.quiz_id == quiz.id).group_by(Question.question_type).all()
        
        question_type_distribution = {qtype: count for qtype, count in question_type_counts}
        
        # Difficulty distribution
        difficulty_counts = self.db.query(
            Question.difficulty_level,
            func.count(Question.id)
        ).filter(Question.quiz_id == quiz.id).group_by(Question.difficulty_level).all()
        
        difficulty_distribution = {diff: count for diff, count in difficulty_counts}
        
        # Topic coverage
        topic_counts = self.db.query(
            Question.topic,
            func.count(Question.id)
        ).filter(
            and_(Question.quiz_id == quiz.id, Question.topic.is_not(None))
        ).group_by(Question.topic).all()
        
        topic_coverage = {topic: count for topic, count in topic_counts if topic}
        
        # Success rate calculation
        success_rate = None
        if quiz.completed_attempts > 0:
            success_rate = float(quiz.average_score) / 100.0 if quiz.average_score else None
        
        return QuizMetrics(
            input_tokens=quiz.input_tokens,
            output_tokens=quiz.output_tokens,
            total_tokens=quiz.total_tokens,
            generation_cost=quiz.generation_cost,
            processing_time_ms=quiz.processing_time_ms,
            content_complexity_score=quiz.content_complexity_score,
            question_quality_avg=quiz.question_quality_avg,
            ai_confidence_score=quiz.ai_confidence_score,
            total_attempts=quiz.total_attempts,
            completed_attempts=quiz.completed_attempts,
            average_score=quiz.average_score,
            average_completion_time=quiz.average_completion_time,
            success_rate=success_rate,
            question_difficulty_distribution=difficulty_distribution,
            question_type_distribution=question_type_distribution,
            topic_coverage=topic_coverage
        )
    
    def _calculate_summary_stats(self, user_id: int, filters: QuizFilters) -> Dict[str, Any]:
        """Calculate summary statistics for quiz list."""
        
        base_query = self.db.query(Quiz).filter(
            and_(Quiz.user_id == user_id, Quiz.deleted_at.is_(None))
        )
        
        # Apply same filters as main query
        if filters.status:
            base_query = base_query.filter(Quiz.status.in_([s.value for s in filters.status]))
        
        stats = {
            "total_quizzes": base_query.count(),
            "completed_quizzes": base_query.filter(Quiz.status == "completed").count(),
            "average_quality": 0.0,
            "total_attempts": 0,
            "average_questions_per_quiz": 0.0
        }
        
        # Calculate averages
        quality_avg = base_query.filter(Quiz.quality_score.is_not(None)).with_entities(
            func.avg(Quiz.quality_score)
        ).scalar()
        
        if quality_avg:
            stats["average_quality"] = float(quality_avg)
        
        attempts_sum = base_query.with_entities(func.sum(Quiz.total_attempts)).scalar()
        if attempts_sum:
            stats["total_attempts"] = attempts_sum
        
        questions_avg = base_query.with_entities(func.avg(Quiz.question_count)).scalar()
        if questions_avg:
            stats["average_questions_per_quiz"] = float(questions_avg)
        
        return stats
    
    def _calculate_time_distribution(self, completion_times: List[int]) -> Dict[str, int]:
        """Calculate distribution of completion times."""
        
        if not completion_times:
            return {}
        
        distribution = {
            "0-5min": 0,
            "5-10min": 0,
            "10-20min": 0,
            "20-30min": 0,
            "30-60min": 0,
            "60min+": 0
        }
        
        for time_seconds in completion_times:
            time_minutes = time_seconds / 60
            
            if time_minutes <= 5:
                distribution["0-5min"] += 1
            elif time_minutes <= 10:
                distribution["5-10min"] += 1
            elif time_minutes <= 20:
                distribution["10-20min"] += 1
            elif time_minutes <= 30:
                distribution["20-30min"] += 1
            elif time_minutes <= 60:
                distribution["30-60min"] += 1
            else:
                distribution["60min+"] += 1
        
        return distribution
    
    def _calculate_question_analytics(self, quiz_id: str) -> List[Dict[str, Any]]:
        """Calculate detailed analytics for each question."""
        
        questions = self.db.query(Question).filter(Question.quiz_id == quiz_id).all()
        analytics = []
        
        for question in questions:
            # Get response statistics
            responses = self.db.query(QuestionResponse).filter(
                QuestionResponse.question_id == question.id
            ).all()
            
            if not responses:
                analytics.append({
                    "question_id": question.id,
                    "question_text": question.question_text[:100] + "..." if len(question.question_text) > 100 else question.question_text,
                    "question_type": question.question_type,
                    "difficulty_level": question.difficulty_level,
                    "total_responses": 0,
                    "correct_responses": 0,
                    "success_rate": 0.0,
                    "average_response_time": 0,
                    "discrimination_index": None,
                })
                continue
            
            correct_responses = len([r for r in responses if r.is_correct])
            total_responses = len(responses)
            success_rate = correct_responses / total_responses if total_responses > 0 else 0.0
            
            avg_response_time = int(sum(r.response_time_seconds for r in responses) / len(responses))
            
            # Calculate discrimination index (correlation between question success and overall quiz performance)
            discrimination_index = self._calculate_discrimination_index(question.id, responses)
            
            analytics.append({
                "question_id": question.id,
                "question_text": question.question_text[:100] + "..." if len(question.question_text) > 100 else question.question_text,
                "question_type": question.question_type,
                "difficulty_level": question.difficulty_level,
                "topic": question.topic,
                "total_responses": total_responses,
                "correct_responses": correct_responses,
                "success_rate": success_rate,
                "average_response_time": avg_response_time,
                "discrimination_index": discrimination_index,
                "quality_score": float(question.quality_score) if question.quality_score else None,
            })
        
        return analytics
    
    def _calculate_discrimination_index(self, question_id: str, responses: List[QuestionResponse]) -> Optional[float]:
        """Calculate discrimination index for a question."""
        
        if len(responses) < 10:  # Need sufficient data
            return None
        
        # Get overall quiz scores for each response
        attempt_scores = {}
        for response in responses:
            attempt = self.db.query(QuizAttempt).filter(QuizAttempt.id == response.attempt_id).first()
            if attempt and attempt.percentage_score is not None:
                attempt_scores[response.id] = float(attempt.percentage_score)
        
        if len(attempt_scores) < 10:
            return None
        
        # Split into high and low performers (top and bottom 27%)
        sorted_scores = sorted(attempt_scores.items(), key=lambda x: x[1], reverse=True)
        n = len(sorted_scores)
        high_n = max(1, int(n * 0.27))
        low_n = max(1, int(n * 0.27))
        
        high_performers = [response_id for response_id, _ in sorted_scores[:high_n]]
        low_performers = [response_id for response_id, _ in sorted_scores[-low_n:]]
        
        # Calculate success rates for high and low performers
        high_correct = len([r for r in responses if r.id in high_performers and r.is_correct])
        low_correct = len([r for r in responses if r.id in low_performers and r.is_correct])
        
        high_success_rate = high_correct / high_n if high_n > 0 else 0.0
        low_success_rate = low_correct / low_n if low_n > 0 else 0.0
        
        return high_success_rate - low_success_rate
    
    def _analyze_performance_vs_difficulty(self, quiz: Quiz, attempts: List[QuizAttempt]) -> Dict[str, float]:
        """Analyze how performance varies by question difficulty."""
        
        performance = {}
        difficulty_levels = ["beginner", "intermediate", "advanced", "expert"]
        
        for difficulty in difficulty_levels:
            questions = self.db.query(Question).filter(
                and_(Question.quiz_id == quiz.id, Question.difficulty_level == difficulty)
            ).all()
            
            if not questions:
                continue
            
            question_ids = [q.id for q in questions]
            responses = self.db.query(QuestionResponse).filter(
                QuestionResponse.question_id.in_(question_ids)
            ).all()
            
            if responses:
                correct_count = len([r for r in responses if r.is_correct])
                total_count = len(responses)
                success_rate = (correct_count / total_count) * 100 if total_count > 0 else 0.0
                performance[difficulty] = success_rate
        
        return performance
    
    def _calculate_learning_objectives_mastery(self, quiz_id: str) -> Optional[Dict[str, float]]:
        """Calculate mastery levels for different learning objectives."""
        
        questions = self.db.query(Question).filter(
            and_(Question.quiz_id == quiz_id, Question.learning_objective.is_not(None))
        ).all()
        
        if not questions:
            return None
        
        mastery = {}
        
        for question in questions:
            if not question.learning_objective:
                continue
            
            responses = self.db.query(QuestionResponse).filter(
                QuestionResponse.question_id == question.id
            ).all()
            
            if responses:
                correct_count = len([r for r in responses if r.is_correct])
                total_count = len(responses)
                success_rate = (correct_count / total_count) * 100 if total_count > 0 else 0.0
                
                if question.learning_objective in mastery:
                    mastery[question.learning_objective] = (mastery[question.learning_objective] + success_rate) / 2
                else:
                    mastery[question.learning_objective] = success_rate
        
        return mastery
    
    def _calculate_topic_mastery(self, quiz_id: str) -> Optional[Dict[str, float]]:
        """Calculate mastery levels for different topics."""
        
        questions = self.db.query(Question).filter(
            and_(Question.quiz_id == quiz_id, Question.topic.is_not(None))
        ).all()
        
        if not questions:
            return None
        
        mastery = {}
        
        for question in questions:
            if not question.topic:
                continue
            
            responses = self.db.query(QuestionResponse).filter(
                QuestionResponse.question_id == question.id
            ).all()
            
            if responses:
                correct_count = len([r for r in responses if r.is_correct])
                total_count = len(responses)
                success_rate = (correct_count / total_count) * 100 if total_count > 0 else 0.0
                
                if question.topic in mastery:
                    # Average with existing score
                    mastery[question.topic] = (mastery[question.topic] + success_rate) / 2
                else:
                    mastery[question.topic] = success_rate
        
        return mastery
    
    def _identify_common_misconceptions(self, quiz_id: str) -> Optional[List[str]]:
        """Identify common misconceptions based on incorrect answers."""
        
        # This is a simplified implementation
        # In a production system, this would be more sophisticated
        misconceptions = []
        
        questions = self.db.query(Question).filter(Question.quiz_id == quiz_id).all()
        
        for question in questions:
            if question.question_type != "multiple_choice":
                continue
            
            responses = self.db.query(QuestionResponse).filter(
                QuestionResponse.question_id == question.id
            ).all()
            
            if not responses:
                continue
            
            # Analyze incorrect answer patterns
            incorrect_responses = [r for r in responses if not r.is_correct]
            
            if len(incorrect_responses) > len(responses) * 0.5:  # More than 50% incorrect
                misconceptions.append(f"Common difficulty with: {question.topic or 'unknown topic'}")
        
        return misconceptions[:5]  # Limit to top 5
    
    def _generate_improvement_suggestions(
        self,
        quiz: Quiz,
        attempts: List[QuizAttempt],
        question_analytics: List[Dict[str, Any]],
        completion_rate: float,
        average_score: Decimal
    ) -> List[str]:
        """Generate improvement suggestions based on quiz analytics."""
        
        suggestions = []
        
        # Completion rate suggestions
        if completion_rate < 50:
            suggestions.append("Low completion rate detected. Consider reducing quiz length or difficulty.")
        
        # Average score suggestions
        if average_score < 60:
            suggestions.append("Low average scores suggest the quiz may be too difficult. Review question difficulty levels.")
        elif average_score > 90:
            suggestions.append("High average scores suggest the quiz may be too easy. Consider adding more challenging questions.")
        
        # Question-specific suggestions
        difficult_questions = [qa for qa in question_analytics if qa.get("success_rate", 1.0) < 0.3]
        if len(difficult_questions) > len(question_analytics) * 0.3:
            suggestions.append("Multiple questions have very low success rates. Review question clarity and difficulty.")
        
        easy_questions = [qa for qa in question_analytics if qa.get("success_rate", 0.0) > 0.95]
        if len(easy_questions) > len(question_analytics) * 0.3:
            suggestions.append("Many questions have very high success rates. Consider adding more challenging alternatives.")
        
        # Time-based suggestions
        if attempts:
            avg_time = sum(a.time_spent_seconds for a in attempts if a.time_spent_seconds) / len([a for a in attempts if a.time_spent_seconds])
            if avg_time > quiz.estimated_time_minutes * 60 * 1.5:  # 50% over estimate
                suggestions.append("Actual completion time significantly exceeds estimate. Consider adjusting time estimate or reducing question count.")
        
        # Quality suggestions
        low_quality_questions = [qa for qa in question_analytics if qa.get("quality_score", 5.0) < 3.0]
        if len(low_quality_questions) > 0:
            suggestions.append(f"{len(low_quality_questions)} questions have low quality scores. Consider regenerating these questions.")
        
        return suggestions[:5]  # Limit to top 5 suggestions
    
    def _analyze_user_progression(self, quiz_id: str) -> Optional[List[Dict[str, Any]]]:
        """Analyze user progression patterns across multiple attempts."""
        
        # Get users with multiple attempts
        user_attempts = self.db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id
        ).order_by(QuizAttempt.user_id, QuizAttempt.attempt_number).all()
        
        user_progression = {}
        
        for attempt in user_attempts:
            if attempt.user_id not in user_progression:
                user_progression[attempt.user_id] = []
            
            user_progression[attempt.user_id].append({
                "attempt_number": attempt.attempt_number,
                "score": float(attempt.percentage_score) if attempt.percentage_score else 0.0,
                "completion_time": attempt.time_spent_seconds,
                "completed": attempt.status == "completed"
            })
        
        # Analyze progression patterns
        progression_patterns = []
        
        for user_id, attempts in user_progression.items():
            if len(attempts) > 1:
                scores = [a["score"] for a in attempts if a["completed"]]
                if len(scores) > 1:
                    improvement = scores[-1] - scores[0]  # Last score - first score
                    progression_patterns.append({
                        "user_id": user_id,
                        "attempts": len(attempts),
                        "improvement": improvement,
                        "final_score": scores[-1] if scores else 0.0
                    })
        
        return progression_patterns[:10]  # Limit to first 10 users


class QuizAttemptService:
    """Service class for quiz attempt operations and tracking."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def start_attempt(
        self,
        quiz_id: str,
        user_id: int,
        session_id: Optional[str] = None,
        **kwargs
    ) -> QuizAttempt:
        """Start a new quiz attempt."""
        
        # Verify quiz exists and is accessible
        quiz = self.db.query(Quiz).filter(
            and_(Quiz.id == quiz_id, Quiz.status == "completed")
        ).first()
        
        if not quiz:
            raise ValueError("Quiz not found or not available")
        
        # Check attempt limits
        if quiz.max_attempts:
            existing_attempts = self.db.query(QuizAttempt).filter(
                and_(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
            ).count()
            
            if existing_attempts >= quiz.max_attempts:
                raise ValueError("Maximum attempts exceeded")
        
        # Get next attempt number
        last_attempt = self.db.query(QuizAttempt).filter(
            and_(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
        ).order_by(desc(QuizAttempt.attempt_number)).first()
        
        attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
        
        # Calculate max possible score
        total_points = self.db.query(func.sum(Question.points)).filter(
            Question.quiz_id == quiz_id
        ).scalar() or Decimal("0.0")
        
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            user_id=user_id,
            attempt_number=attempt_number,
            max_possible_score=total_points,
            session_id=session_id or str(uuid.uuid4()),
            time_limit_seconds=quiz.time_limit_minutes * 60 if quiz.time_limit_minutes else None,
            **kwargs
        )
        
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        
        logger.info(f"Started quiz attempt {attempt.id} for user {user_id}")
        return attempt
    
    def get_attempt(self, attempt_id: str, user_id: int) -> Optional[QuizAttempt]:
        """Get a quiz attempt by ID."""
        
        return self.db.query(QuizAttempt).filter(
            and_(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user_id)
        ).first()
    
    def submit_answer(
        self,
        attempt_id: str,
        question_id: str,
        user_answer: Optional[str] = None,
        selected_answer_ids: Optional[List[str]] = None,
        response_time_seconds: int = 0,
        confidence_level: Optional[int] = None
    ) -> QuestionResponse:
        """Submit an answer for a question in an attempt."""
        
        attempt = self.db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
        if not attempt or attempt.status != "in_progress":
            raise ValueError("Invalid attempt or attempt not in progress")
        
        question = self.db.query(Question).filter(Question.id == question_id).first()
        if not question or question.quiz_id != attempt.quiz_id:
            raise ValueError("Invalid question for this quiz")
        
        # Check if already answered
        existing_response = self.db.query(QuestionResponse).filter(
            and_(QuestionResponse.attempt_id == attempt_id, QuestionResponse.question_id == question_id)
        ).first()
        
        if existing_response:
            raise ValueError("Question already answered")
        
        # Evaluate answer
        is_correct, points_earned = self._evaluate_answer(
            question, user_answer, selected_answer_ids
        )
        
        # Create response record
        response = QuestionResponse(
            attempt_id=attempt_id,
            question_id=question_id,
            user_answer=user_answer,
            selected_answer_ids=json.dumps(selected_answer_ids) if selected_answer_ids else None,
            is_correct=is_correct,
            points_earned=points_earned,
            max_points=question.points,
            response_time_seconds=response_time_seconds,
            confidence_level=confidence_level
        )
        
        self.db.add(response)
        
        # Update attempt progress
        attempt.questions_answered += 1
        if is_correct:
            attempt.questions_correct += 1
        attempt.total_score += points_earned
        attempt.current_question_index += 1
        
        # Update question analytics
        question.update_analytics(is_correct, response_time_seconds)
        
        self.db.commit()
        
        logger.info(f"Answer submitted for attempt {attempt_id}, question {question_id}")
        return response
    
    def complete_attempt(
        self,
        attempt_id: str,
        user_id: int,
        user_feedback: Optional[str] = None,
        difficulty_rating: Optional[int] = None
    ) -> QuizAttempt:
        """Complete a quiz attempt."""
        
        attempt = self.get_attempt(attempt_id, user_id)
        if not attempt:
            raise ValueError("Attempt not found")
        
        if attempt.status != "in_progress":
            raise ValueError("Attempt is not in progress")
        
        # Mark as completed
        attempt.mark_completed()
        attempt.user_feedback = user_feedback
        attempt.difficulty_rating = difficulty_rating
        
        # Update quiz analytics
        quiz = self.db.query(Quiz).filter(Quiz.id == attempt.quiz_id).first()
        if quiz and attempt.percentage_score is not None:
            quiz.update_analytics(attempt.percentage_score, attempt.time_spent_seconds or 0)
        
        self.db.commit()
        
        logger.info(f"Completed quiz attempt {attempt_id} for user {user_id}")
        return attempt
    
    def abandon_attempt(self, attempt_id: str, user_id: int) -> QuizAttempt:
        """Abandon a quiz attempt."""
        
        attempt = self.get_attempt(attempt_id, user_id)
        if not attempt:
            raise ValueError("Attempt not found")
        
        attempt.abandon()
        self.db.commit()
        
        logger.info(f"Abandoned quiz attempt {attempt_id} for user {user_id}")
        return attempt
    
    def get_user_attempts(
        self,
        user_id: int,
        quiz_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> QuizAttemptListResponse:
        """Get paginated list of user's quiz attempts."""
        
        query = self.db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id)
        
        if quiz_id:
            query = query.filter(QuizAttempt.quiz_id == quiz_id)
        
        total = query.count()
        
        query = query.order_by(desc(QuizAttempt.started_at))
        offset = (page - 1) * page_size
        attempts = query.offset(offset).limit(page_size).all()
        
        # Convert to response schema
        attempt_responses = []
        for attempt in attempts:
            attempt_response = QuizAttemptResponse(
                id=attempt.id,
                quiz_id=attempt.quiz_id,
                user_id=attempt.user_id,
                attempt_number=attempt.attempt_number,
                status=attempt.status,
                total_score=attempt.total_score,
                max_possible_score=attempt.max_possible_score,
                percentage_score=attempt.percentage_score,
                passed=attempt.passed,
                questions_answered=attempt.questions_answered,
                questions_correct=attempt.questions_correct,
                current_question_index=attempt.current_question_index,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
                time_spent_seconds=attempt.time_spent_seconds,
                time_limit_seconds=attempt.time_limit_seconds,
                topic_scores=json.loads(attempt.topic_scores) if attempt.topic_scores else None,
                difficulty_progression=json.loads(attempt.difficulty_progression) if attempt.difficulty_progression else None,
                user_feedback=attempt.user_feedback,
                difficulty_rating=attempt.difficulty_rating,
            )
            attempt_responses.append(attempt_response)
        
        total_pages = (total + page_size - 1) // page_size
        
        return QuizAttemptListResponse(
            attempts=attempt_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    def _evaluate_answer(
        self,
        question: Question,
        user_answer: Optional[str],
        selected_answer_ids: Optional[List[str]]
    ) -> Tuple[bool, Decimal]:
        """Evaluate a user's answer and return correctness and points earned."""
        
        if question.question_type == "multiple_choice":
            if not selected_answer_ids:
                return False, Decimal("0.0")
            
            # Get correct answers
            correct_answers = self.db.query(Answer).filter(
                and_(Answer.question_id == question.id, Answer.is_correct == True)
            ).all()
            
            correct_answer_ids = set(a.id for a in correct_answers)
            selected_ids = set(selected_answer_ids)
            
            if correct_answer_ids == selected_ids:
                return True, question.points
            else:
                # Check for partial credit
                if question.allow_partial_credit and correct_answer_ids.intersection(selected_ids):
                    partial_credit = (len(correct_answer_ids.intersection(selected_ids)) / 
                                    len(correct_answer_ids)) * question.points
                    return False, partial_credit
                return False, Decimal("0.0")
        
        elif question.question_type == "true_false":
            if not user_answer:
                return False, Decimal("0.0")
            
            correct_answer = self.db.query(Answer).filter(
                and_(Answer.question_id == question.id, Answer.is_correct == True)
            ).first()
            
            if correct_answer and user_answer.lower().strip() == correct_answer.answer_text.lower().strip():
                return True, question.points
            return False, Decimal("0.0")
        
        elif question.question_type in ["short_answer", "long_answer", "essay"]:
            if not user_answer:
                return False, Decimal("0.0")
            
            # For text answers, we'd typically need AI evaluation or manual grading
            # For now, return partial credit and mark for manual review
            return False, question.points * Decimal("0.5")  # 50% pending review
        
        elif question.question_type == "fill_in_blank":
            if not user_answer:
                return False, Decimal("0.0")
            
            correct_answers = self.db.query(Answer).filter(
                and_(Answer.question_id == question.id, Answer.is_correct == True)
            ).all()
            
            user_text = user_answer.lower().strip()
            if not question.case_sensitive:
                for correct_answer in correct_answers:
                    if user_text == correct_answer.answer_text.lower().strip():
                        return True, question.points
            else:
                for correct_answer in correct_answers:
                    if user_answer.strip() == correct_answer.answer_text.strip():
                        return True, question.points
            
            return False, Decimal("0.0")
        
        # Default case
        return False, Decimal("0.0")
