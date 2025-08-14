"""
Advanced AI-powered quiz generation service with comprehensive prompt engineering.

This module provides sophisticated quiz generation capabilities including:
- Adaptive difficulty assessment based on document complexity
- Multiple question type generation with quality scoring
- Learning objective mapping and taxonomy alignment
- Content analysis and topic extraction
- Question quality validation and improvement suggestions
"""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Type

import structlog
from pydantic import BaseModel, Field, validator

from .base import AIProvider
from .errors import AIProviderError
from .types import ErrorType, RequestValidation, ToolSpec

logger = structlog.get_logger(__name__)


class QuizGenerationError(Exception):
    """Specific error for quiz generation failures."""
    
    def __init__(self, message: str, error_type: str = "generation_error", details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}


class ContentComplexity(str, Enum):
    """Content complexity levels for adaptive difficulty."""
    ELEMENTARY = "elementary"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class QuestionQuality(BaseModel):
    """Question quality assessment."""
    
    clarity_score: float = Field(ge=0.0, le=5.0, description="How clear and well-written is the question")
    difficulty_accuracy: float = Field(ge=0.0, le=5.0, description="How well does the difficulty match the target")
    content_relevance: float = Field(ge=0.0, le=5.0, description="How relevant is the question to the source material")
    distractor_quality: float = Field(ge=0.0, le=5.0, description="Quality of incorrect answer options")
    learning_alignment: float = Field(ge=0.0, le=5.0, description="Alignment with learning objectives")
    
    @property
    def overall_score(self) -> float:
        """Calculate overall quality score."""
        return (
            self.clarity_score + 
            self.difficulty_accuracy + 
            self.content_relevance + 
            self.distractor_quality + 
            self.learning_alignment
        ) / 5


class GeneratedQuestion(BaseModel):
    """Generated question with metadata and quality assessment."""
    
    question_text: str = Field(..., description="The question text")
    question_type: str = Field(..., description="Type of question")
    difficulty_level: str = Field(..., description="Difficulty level")
    topic: str = Field(..., description="Main topic covered")
    learning_objective: Optional[str] = Field(None, description="Learning objective addressed")
    cognitive_level: Optional[str] = Field(None, description="Bloom's taxonomy level")
    
    # Answer options
    correct_answers: List[str] = Field(..., description="Correct answer(s)")
    incorrect_options: List[str] = Field(default_factory=list, description="Incorrect options for MCQ")
    explanation: Optional[str] = Field(None, description="Explanation for the correct answer")
    
    # Metadata
    context: Optional[str] = Field(None, description="Additional context for the question")
    source_reference: Optional[str] = Field(None, description="Reference to source material")
    estimated_time_seconds: int = Field(default=60, description="Estimated time to answer")
    points: float = Field(default=1.0, description="Point value")
    
    # Quality metrics
    quality: Optional[QuestionQuality] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    @validator("question_type")
    def validate_question_type(cls, v):
        allowed_types = [
            "multiple_choice", "true_false", "short_answer", 
            "long_answer", "essay", "fill_in_blank", "matching", "ordering"
        ]
        if v not in allowed_types:
            raise ValueError(f"Invalid question type. Must be one of: {', '.join(allowed_types)}")
        return v


class ContentAnalysis(BaseModel):
    """Analysis of source content for quiz generation."""
    
    complexity_level: ContentComplexity
    main_topics: List[str] = Field(description="Main topics identified in the content")
    subtopics: List[str] = Field(description="Subtopics and concepts")
    learning_objectives: List[str] = Field(description="Potential learning objectives")
    key_concepts: List[str] = Field(description="Key concepts and terms")
    content_structure: Dict[str, Any] = Field(description="Document structure analysis")
    
    # Quantitative measures
    reading_level: Optional[str] = None
    technical_depth: float = Field(ge=0.0, le=10.0, description="Technical complexity score")
    concept_density: float = Field(ge=0.0, le=10.0, description="Density of concepts per page/section")
    
    # Recommendations
    recommended_question_types: List[str] = Field(description="Recommended question types for this content")
    difficulty_distribution: Dict[str, int] = Field(description="Suggested difficulty distribution")


class QuizGenerationRequest(BaseModel):
    """Request model for quiz generation."""
    
    content_text: str = Field(..., description="Source content for quiz generation")
    question_count: int = Field(default=10, ge=1, le=50)
    difficulty_level: str = Field(default="adaptive")
    question_types: List[str] = Field(default_factory=lambda: ["multiple_choice", "true_false", "short_answer"])
    learning_objectives: Optional[List[str]] = None
    focus_topics: Optional[List[str]] = None
    exclude_topics: Optional[List[str]] = None
    custom_instructions: Optional[str] = None
    
    # Advanced options
    bloom_taxonomy_distribution: Optional[Dict[str, int]] = None
    adaptive_difficulty: bool = Field(default=True, description="Use adaptive difficulty based on content")
    quality_threshold: float = Field(default=3.0, ge=1.0, le=5.0, description="Minimum quality score")
    generate_distractors: bool = Field(default=True, description="Generate high-quality distractors")


class QuizGenerationResponse(BaseModel):
    """Response model for quiz generation."""
    
    questions: List[GeneratedQuestion]
    content_analysis: ContentAnalysis
    generation_metadata: Dict[str, Any]
    quality_summary: Dict[str, float]
    recommendations: List[str]


class AIQuizGenerator:
    """Advanced AI-powered quiz generation service."""
    
    def __init__(self, ai_provider: AIProvider):
        self.provider = ai_provider
        self.logger = logger.bind(component="quiz_generator")
    
    async def analyze_content(self, content_text: str) -> ContentAnalysis:
        """Analyze content to determine optimal quiz generation parameters."""
        
        analysis_prompt = self._build_content_analysis_prompt()
        
        request = RequestValidation(
            system_instruction=analysis_prompt,
            user_text=f"Please analyze the following content:\n\n{content_text[:10000]}...",  # Limit content size
            temperature=0.3,  # Lower temperature for consistent analysis
            max_tokens=2000
        )
        
        try:
            response = await self.provider.generate_with_monitoring(
                request_data=request,
                response_model=ContentAnalysis
            )
            
            if response.structured:
                return ContentAnalysis(**response.structured)
            else:
                # Fallback parsing
                return self._parse_content_analysis_fallback(response.text, content_text)
                
        except Exception as e:
            self.logger.error("Content analysis failed", error=str(e))
            raise QuizGenerationError(
                f"Failed to analyze content: {str(e)}",
                error_type="analysis_error"
            )
    
    async def generate_quiz(self, request: QuizGenerationRequest) -> QuizGenerationResponse:
        """Generate a comprehensive quiz from the provided content."""
        
        try:
            # Step 1: Analyze content if adaptive difficulty is enabled
            content_analysis = None
            if request.adaptive_difficulty:
                self.logger.info("Analyzing content for adaptive difficulty")
                content_analysis = await self.analyze_content(request.content_text)
            else:
                content_analysis = self._create_default_content_analysis(request)
            
            # Step 2: Generate questions in batches for better quality
            questions = []
            batch_size = min(5, request.question_count)  # Generate in small batches
            
            for i in range(0, request.question_count, batch_size):
                remaining_questions = min(batch_size, request.question_count - i)
                
                self.logger.info(
                    "Generating question batch",
                    batch=i//batch_size + 1,
                    questions_in_batch=remaining_questions
                )
                
                batch_questions = await self._generate_question_batch(
                    request, content_analysis, remaining_questions, i
                )
                questions.extend(batch_questions)
            
            # Step 3: Quality assessment and improvement
            questions = await self._assess_and_improve_questions(questions, request)
            
            # Step 4: Generate final recommendations
            recommendations = self._generate_recommendations(questions, content_analysis, request)
            
            # Step 5: Compile response
            quality_summary = self._calculate_quality_summary(questions)
            generation_metadata = {
                "generated_at": datetime.utcnow().isoformat(),
                "total_questions": len(questions),
                "avg_quality_score": quality_summary.get("average_quality", 0.0),
                "generation_approach": "adaptive" if request.adaptive_difficulty else "standard",
                "content_complexity": content_analysis.complexity_level.value if content_analysis else "unknown"
            }
            
            return QuizGenerationResponse(
                questions=questions,
                content_analysis=content_analysis,
                generation_metadata=generation_metadata,
                quality_summary=quality_summary,
                recommendations=recommendations
            )
            
        except Exception as e:
            self.logger.error("Quiz generation failed", error=str(e))
            if isinstance(e, QuizGenerationError):
                raise e
            raise QuizGenerationError(
                f"Failed to generate quiz: {str(e)}",
                error_type="generation_error",
                details={"original_error": str(e)}
            )
    
    async def _generate_question_batch(
        self, 
        request: QuizGenerationRequest, 
        content_analysis: ContentAnalysis, 
        question_count: int,
        start_index: int = 0
    ) -> List[GeneratedQuestion]:
        """Generate a batch of questions with high quality."""
        
        # Build context-aware prompt
        generation_prompt = self._build_question_generation_prompt(
            request, content_analysis, question_count, start_index
        )
        
        # Prepare content excerpt for this batch
        content_excerpt = self._extract_relevant_content_excerpt(
            request.content_text, start_index, question_count
        )
        
        request_validation = RequestValidation(
            system_instruction=generation_prompt,
            user_text=f"Generate {question_count} high-quality questions from this content:\n\n{content_excerpt}",
            temperature=0.7,  # Balanced creativity for question generation
            max_tokens=4000
        )
        
        try:
            response = await self.provider.generate_with_monitoring(
                request_data=request_validation
            )
            
            # Parse questions from response
            questions = self._parse_questions_from_response(response.text, question_count)
            
            # Validate and clean questions
            valid_questions = []
            for question in questions:
                if self._validate_generated_question(question, request):
                    valid_questions.append(question)
            
            self.logger.info(
                "Question batch generated",
                requested=question_count,
                generated=len(questions),
                valid=len(valid_questions)
            )
            
            return valid_questions
            
        except Exception as e:
            self.logger.error("Question batch generation failed", error=str(e))
            raise QuizGenerationError(
                f"Failed to generate question batch: {str(e)}",
                error_type="batch_generation_error"
            )
    
    async def _assess_and_improve_questions(
        self, 
        questions: List[GeneratedQuestion], 
        request: QuizGenerationRequest
    ) -> List[GeneratedQuestion]:
        """Assess question quality and improve low-quality questions."""
        
        improved_questions = []
        
        for question in questions:
            # Assess quality
            quality = await self._assess_question_quality(question)
            question.quality = quality
            
            # Improve if below threshold
            if quality.overall_score < request.quality_threshold:
                self.logger.info(
                    "Improving low-quality question",
                    current_score=quality.overall_score,
                    threshold=request.quality_threshold
                )
                
                improved_question = await self._improve_question(question, request)
                improved_questions.append(improved_question)
            else:
                improved_questions.append(question)
        
        return improved_questions
    
    async def _assess_question_quality(self, question: GeneratedQuestion) -> QuestionQuality:
        """Assess the quality of a generated question."""
        
        assessment_prompt = self._build_quality_assessment_prompt()
        
        question_json = question.model_dump_json(indent=2)
        
        request = RequestValidation(
            system_instruction=assessment_prompt,
            user_text=f"Please assess the quality of this question:\n\n{question_json}",
            temperature=0.2,  # Low temperature for consistent assessment
            max_tokens=1000
        )
        
        try:
            response = await self.provider.generate_with_monitoring(
                request_data=request,
                response_model=QuestionQuality
            )
            
            if response.structured:
                return QuestionQuality(**response.structured)
            else:
                # Fallback assessment
                return self._fallback_quality_assessment(question)
                
        except Exception as e:
            self.logger.warning("Quality assessment failed, using fallback", error=str(e))
            return self._fallback_quality_assessment(question)
    
    async def _improve_question(
        self, 
        question: GeneratedQuestion, 
        request: QuizGenerationRequest
    ) -> GeneratedQuestion:
        """Improve a low-quality question."""
        
        improvement_prompt = self._build_question_improvement_prompt()
        
        current_quality = question.quality
        quality_issues = []
        
        if current_quality.clarity_score < 3.0:
            quality_issues.append("clarity")
        if current_quality.difficulty_accuracy < 3.0:
            quality_issues.append("difficulty_matching")
        if current_quality.content_relevance < 3.0:
            quality_issues.append("content_relevance")
        if current_quality.distractor_quality < 3.0:
            quality_issues.append("distractor_quality")
        
        question_json = question.model_dump_json(indent=2)
        
        request_validation = RequestValidation(
            system_instruction=improvement_prompt,
            user_text=f"""Please improve this question. Focus on these quality issues: {', '.join(quality_issues)}

Current question:
{question_json}

Target quality threshold: {request.quality_threshold}/5.0""",
            temperature=0.6,
            max_tokens=2000
        )
        
        try:
            response = await self.provider.generate_with_monitoring(
                request_data=request_validation,
                response_model=GeneratedQuestion
            )
            
            if response.structured:
                improved = GeneratedQuestion(**response.structured)
                # Preserve original metadata
                improved.source_reference = question.source_reference
                return improved
            else:
                # Return original if improvement fails
                return question
                
        except Exception as e:
            self.logger.warning("Question improvement failed", error=str(e))
            return question
    
    def _build_content_analysis_prompt(self) -> str:
        """Build comprehensive content analysis prompt."""
        return """You are an expert educational content analyzer. Your task is to analyze the provided content and determine optimal parameters for quiz generation.

Please analyze the content and provide a detailed assessment including:

1. **Complexity Level**: Determine if the content is elementary, intermediate, advanced, or expert level
2. **Topic Structure**: Identify main topics, subtopics, and key concepts
3. **Learning Objectives**: Suggest appropriate learning objectives that could be assessed
4. **Technical Depth**: Rate the technical complexity and concept density
5. **Question Type Recommendations**: Suggest the most appropriate question types for this content
6. **Difficulty Distribution**: Recommend how questions should be distributed across difficulty levels

Return your analysis in the following JSON structure:
{
    "complexity_level": "intermediate",
    "main_topics": ["topic1", "topic2"],
    "subtopics": ["subtopic1", "subtopic2"],
    "learning_objectives": ["objective1", "objective2"],
    "key_concepts": ["concept1", "concept2"],
    "content_structure": {
        "sections": 5,
        "estimated_pages": 10,
        "concept_density": "high"
    },
    "reading_level": "college",
    "technical_depth": 7.5,
    "concept_density": 6.2,
    "recommended_question_types": ["multiple_choice", "short_answer", "essay"],
    "difficulty_distribution": {
        "beginner": 2,
        "intermediate": 6,
        "advanced": 2
    }
}

Focus on accuracy and educational value in your assessment."""
    
    def _build_question_generation_prompt(
        self, 
        request: QuizGenerationRequest, 
        content_analysis: ContentAnalysis, 
        question_count: int,
        start_index: int
    ) -> str:
        """Build context-aware question generation prompt."""
        
        difficulty_guidance = self._get_difficulty_guidance(request.difficulty_level, content_analysis)
        question_type_guidance = self._get_question_type_guidance(request.question_types)
        
        return f"""You are an expert educational assessment designer. Generate {question_count} high-quality quiz questions from the provided content.

**Generation Requirements:**
- Question count: {question_count}
- Difficulty level: {request.difficulty_level}
- Question types: {', '.join(request.question_types)}
- Content complexity: {content_analysis.complexity_level.value if content_analysis else 'unknown'}

**Quality Standards:**
- Questions must be clear, unambiguous, and well-written
- Correct answers must be definitively correct based on the content
- Incorrect options (distractors) must be plausible but clearly wrong
- Each question should test understanding, not just memorization
- Questions should align with appropriate learning objectives

{difficulty_guidance}

{question_type_guidance}

**Response Format:**
Return each question as a JSON object with this structure:
{{
    "question_text": "Clear, well-written question",
    "question_type": "multiple_choice|true_false|short_answer|long_answer|essay",
    "difficulty_level": "beginner|intermediate|advanced|expert",
    "topic": "main topic covered",
    "learning_objective": "what this question assesses",
    "cognitive_level": "remember|understand|apply|analyze|evaluate|create",
    "correct_answers": ["correct answer 1", "correct answer 2"],
    "incorrect_options": ["distractor 1", "distractor 2", "distractor 3"],
    "explanation": "why the correct answer is right",
    "context": "additional context if needed",
    "estimated_time_seconds": 60,
    "points": 1.0,
    "confidence_score": 0.9
}}

Wrap all questions in a JSON array: [question1, question2, ...]

Focus on educational value and assessment quality."""
    
    def _build_quality_assessment_prompt(self) -> str:
        """Build question quality assessment prompt."""
        return """You are an expert in educational assessment quality. Evaluate the provided question across multiple dimensions.

Rate each aspect from 0.0 to 5.0:

1. **Clarity Score (0.0-5.0)**: How clear and well-written is the question?
   - 5.0: Crystal clear, no ambiguity
   - 3.0: Generally clear with minor issues
   - 1.0: Confusing or poorly written

2. **Difficulty Accuracy (0.0-5.0)**: How well does the actual difficulty match the stated level?
   - 5.0: Perfect match between stated and actual difficulty
   - 3.0: Close match with minor discrepancies
   - 1.0: Major mismatch in difficulty level

3. **Content Relevance (0.0-5.0)**: How relevant is the question to the source material?
   - 5.0: Directly tests key concepts from the content
   - 3.0: Tests relevant but secondary concepts
   - 1.0: Barely related to the source material

4. **Distractor Quality (0.0-5.0)**: Quality of incorrect answer options (for MCQ)?
   - 5.0: Excellent distractors that are plausible but clearly wrong
   - 3.0: Good distractors with some issues
   - 1.0: Poor distractors that are obviously wrong or irrelevant

5. **Learning Alignment (0.0-5.0)**: How well does the question align with stated learning objectives?
   - 5.0: Perfectly aligned with learning objectives
   - 3.0: Generally aligned but could be stronger
   - 1.0: Poor alignment with learning objectives

Return your assessment in this JSON format:
{
    "clarity_score": 4.5,
    "difficulty_accuracy": 4.0,
    "content_relevance": 4.2,
    "distractor_quality": 3.8,
    "learning_alignment": 4.1
}"""
    
    def _build_question_improvement_prompt(self) -> str:
        """Build question improvement prompt."""
        return """You are an expert educational assessment designer. Improve the provided question to meet higher quality standards.

**Improvement Guidelines:**
1. **Enhance Clarity**: Make the question clearer and more precise
2. **Improve Distractors**: Create more plausible but definitively incorrect options
3. **Strengthen Content Alignment**: Ensure the question tests important concepts
4. **Adjust Difficulty**: Match the difficulty to the stated level
5. **Educational Value**: Focus on understanding and application, not just recall

**Quality Standards:**
- Target score: 4.0+ on all quality dimensions
- Clear, unambiguous language
- Educationally valuable content
- Appropriate cognitive level
- High-quality distractors (for MCQ)

Return the improved question in the same JSON format as the original, with all fields properly filled."""
    
    def _get_difficulty_guidance(self, difficulty_level: str, content_analysis: Optional[ContentAnalysis]) -> str:
        """Get difficulty-specific generation guidance."""
        
        if difficulty_level == "adaptive" and content_analysis:
            return f"""**Adaptive Difficulty Guidance:**
Based on the content analysis (complexity: {content_analysis.complexity_level.value}), adjust question difficulty appropriately:
- Focus on {content_analysis.complexity_level.value}-level concepts
- Use the recommended difficulty distribution: {content_analysis.difficulty_distribution}
- Align with the technical depth score of {content_analysis.technical_depth}/10"""
        
        difficulty_guides = {
            "beginner": "Focus on basic recall and simple understanding. Use straightforward language and test fundamental concepts.",
            "intermediate": "Test understanding and basic application. Questions should require some analysis but not expert-level insight.",
            "advanced": "Challenge learners with analysis, synthesis, and application. Test deeper understanding and complex concepts.",
            "expert": "Create sophisticated questions requiring expert-level analysis, evaluation, and synthesis of complex ideas."
        }
        
        return f"**Difficulty Guidance:** {difficulty_guides.get(difficulty_level, difficulty_guides['intermediate'])}"
    
    def _get_question_type_guidance(self, question_types: List[str]) -> str:
        """Get question type-specific guidance."""
        
        type_guides = {
            "multiple_choice": "Create 4 options with 1 correct answer. Distractors should be plausible but clearly incorrect.",
            "true_false": "Create statements that are definitively true or false based on the content. Avoid ambiguous statements.",
            "short_answer": "Ask for specific, concise answers that can be objectively evaluated (1-3 sentences).",
            "long_answer": "Request detailed explanations or analysis (paragraph-length responses).",
            "essay": "Ask for comprehensive analysis, argument, or synthesis requiring multiple paragraphs.",
            "fill_in_blank": "Create sentences with key terms removed. Blanks should test important concepts.",
            "matching": "Create pairs of related items (terms-definitions, concepts-examples, etc.).",
            "ordering": "Ask learners to sequence items chronologically, by importance, or by process steps."
        }
        
        guidance_parts = []
        for q_type in question_types:
            if q_type in type_guides:
                guidance_parts.append(f"- **{q_type.title()}**: {type_guides[q_type]}")
        
        return "**Question Type Guidance:**\n" + "\n".join(guidance_parts)
    
    def _extract_relevant_content_excerpt(self, content: str, start_index: int, question_count: int) -> str:
        """Extract relevant content excerpt for question generation."""
        
        # For now, return a manageable excerpt
        # In a more sophisticated implementation, this could use content analysis
        # to identify the most relevant sections
        
        content_length = len(content)
        excerpt_size = min(8000, content_length)  # Limit to 8000 characters
        
        # Try to get a balanced excerpt
        if content_length <= excerpt_size:
            return content
        
        # Get excerpt from middle sections to avoid just introduction/conclusion
        start_pos = (content_length // 4) + (start_index * (content_length // 10))
        end_pos = min(start_pos + excerpt_size, content_length)
        
        return content[start_pos:end_pos]
    
    def _parse_questions_from_response(self, response_text: str, expected_count: int) -> List[GeneratedQuestion]:
        """Parse questions from AI response with robust error handling."""
        
        questions = []
        
        try:
            # Try to parse as JSON array first
            parsed = json.loads(response_text)
            
            if isinstance(parsed, list):
                for item in parsed:
                    try:
                        question = GeneratedQuestion(**item)
                        questions.append(question)
                    except Exception as e:
                        self.logger.warning("Failed to parse question", error=str(e), item=item)
            
        except json.JSONDecodeError:
            # Try to extract JSON objects from text
            self.logger.info("Attempting to extract questions from non-JSON response")
            questions = self._extract_questions_from_text(response_text)
        
        # Validate count
        if len(questions) < expected_count:
            self.logger.warning(
                "Generated fewer questions than expected",
                expected=expected_count,
                generated=len(questions)
            )
        
        return questions[:expected_count]  # Return only what was requested
    
    def _extract_questions_from_text(self, text: str) -> List[GeneratedQuestion]:
        """Extract questions from unstructured text response."""
        
        # This is a fallback method for parsing questions from text
        # In a production system, this would be more sophisticated
        
        questions = []
        # Placeholder implementation - would need more robust parsing
        
        return questions
    
    def _validate_generated_question(self, question: GeneratedQuestion, request: QuizGenerationRequest) -> bool:
        """Validate that a generated question meets basic requirements."""
        
        try:
            # Basic validation
            if not question.question_text or len(question.question_text.strip()) < 10:
                return False
            
            if not question.correct_answers:
                return False
            
            # Type-specific validation
            if question.question_type == "multiple_choice":
                if len(question.incorrect_options) < 2:
                    return False
            
            if question.question_type == "true_false":
                if not any(ans.lower() in ["true", "false", "yes", "no"] for ans in question.correct_answers):
                    return False
            
            # Content validation
            if request.focus_topics:
                if not any(topic.lower() in question.question_text.lower() for topic in request.focus_topics):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.warning("Question validation failed", error=str(e))
            return False
    
    def _parse_content_analysis_fallback(self, response_text: str, content_text: str) -> ContentAnalysis:
        """Fallback content analysis when structured parsing fails."""
        
        # Create a basic analysis based on content characteristics
        word_count = len(content_text.split())
        char_count = len(content_text)
        
        # Simple heuristics for complexity
        if word_count > 5000 or char_count > 25000:
            complexity = ContentComplexity.ADVANCED
        elif word_count > 2000 or char_count > 10000:
            complexity = ContentComplexity.INTERMEDIATE
        else:
            complexity = ContentComplexity.ELEMENTARY
        
        return ContentAnalysis(
            complexity_level=complexity,
            main_topics=["General Content"],
            subtopics=["Various Concepts"],
            learning_objectives=["Understanding Key Concepts"],
            key_concepts=["Primary Content"],
            content_structure={"estimated_words": word_count},
            technical_depth=5.0,
            concept_density=5.0,
            recommended_question_types=["multiple_choice", "short_answer"],
            difficulty_distribution={"intermediate": 10}
        )
    
    def _create_default_content_analysis(self, request: QuizGenerationRequest) -> ContentAnalysis:
        """Create default content analysis when adaptive difficulty is disabled."""
        
        return ContentAnalysis(
            complexity_level=ContentComplexity.INTERMEDIATE,
            main_topics=request.focus_topics or ["General Content"],
            subtopics=[],
            learning_objectives=request.learning_objectives or ["Understanding Key Concepts"],
            key_concepts=[],
            content_structure={"type": "standard"},
            technical_depth=5.0,
            concept_density=5.0,
            recommended_question_types=request.question_types,
            difficulty_distribution={request.difficulty_level: request.question_count}
        )
    
    def _fallback_quality_assessment(self, question: GeneratedQuestion) -> QuestionQuality:
        """Fallback quality assessment when AI assessment fails."""
        
        # Simple heuristic-based quality assessment
        clarity_score = 3.5 if len(question.question_text) > 20 else 2.0
        difficulty_accuracy = 3.0  # Default middle score
        content_relevance = 3.5 if question.topic else 2.5
        distractor_quality = 3.0 if len(question.incorrect_options) >= 3 else 2.0
        learning_alignment = 3.0 if question.learning_objective else 2.5
        
        return QuestionQuality(
            clarity_score=clarity_score,
            difficulty_accuracy=difficulty_accuracy,
            content_relevance=content_relevance,
            distractor_quality=distractor_quality,
            learning_alignment=learning_alignment
        )
    
    def _calculate_quality_summary(self, questions: List[GeneratedQuestion]) -> Dict[str, float]:
        """Calculate overall quality summary for the generated quiz."""
        
        if not questions:
            return {"average_quality": 0.0, "total_questions": 0}
        
        quality_scores = []
        for question in questions:
            if question.quality:
                quality_scores.append(question.quality.overall_score)
        
        if not quality_scores:
            return {"average_quality": 0.0, "total_questions": len(questions)}
        
        return {
            "average_quality": sum(quality_scores) / len(quality_scores),
            "min_quality": min(quality_scores),
            "max_quality": max(quality_scores),
            "quality_std_dev": self._calculate_std_dev(quality_scores),
            "total_questions": len(questions),
            "high_quality_count": len([score for score in quality_scores if score >= 4.0])
        }
    
    def _calculate_std_dev(self, scores: List[float]) -> float:
        """Calculate standard deviation of quality scores."""
        if len(scores) < 2:
            return 0.0
        
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        return variance ** 0.5
    
    def _generate_recommendations(
        self, 
        questions: List[GeneratedQuestion], 
        content_analysis: ContentAnalysis,
        request: QuizGenerationRequest
    ) -> List[str]:
        """Generate recommendations for quiz improvement and usage."""
        
        recommendations = []
        
        # Quality-based recommendations
        quality_scores = [q.quality.overall_score for q in questions if q.quality]
        if quality_scores:
            avg_quality = sum(quality_scores) / len(quality_scores)
            
            if avg_quality < 3.5:
                recommendations.append(
                    "Consider regenerating some questions to improve overall quality. "
                    f"Current average quality: {avg_quality:.1f}/5.0"
                )
            
            if len([score for score in quality_scores if score < 3.0]) > 0:
                recommendations.append(
                    "Some questions scored below 3.0 in quality assessment. "
                    "Review and potentially replace these questions."
                )
        
        # Content coverage recommendations
        topics_covered = set(q.topic for q in questions if q.topic)
        if len(topics_covered) < len(content_analysis.main_topics) // 2:
            recommendations.append(
                "Quiz covers fewer topics than available in the source content. "
                "Consider generating more questions to improve coverage."
            )
        
        # Question type distribution
        type_distribution = {}
        for question in questions:
            type_distribution[question.question_type] = type_distribution.get(question.question_type, 0) + 1
        
        if len(type_distribution) == 1:
            recommendations.append(
                "Quiz uses only one question type. Consider adding variety with different question types."
            )
        
        # Difficulty recommendations
        difficulty_distribution = {}
        for question in questions:
            difficulty_distribution[question.difficulty_level] = difficulty_distribution.get(question.difficulty_level, 0) + 1
        
        if len(difficulty_distribution) == 1 and "adaptive" not in request.difficulty_level:
            recommendations.append(
                "All questions are at the same difficulty level. Consider adding variety in difficulty."
            )
        
        # Time estimation
        total_time = sum(q.estimated_time_seconds for q in questions)
        if total_time > 3600:  # More than 1 hour
            recommendations.append(
                f"Estimated completion time is {total_time//60} minutes. "
                "Consider reducing question count or complexity for better user experience."
            )
        
        return recommendations[:5]  # Limit to 5 recommendations
