"""
Service layer for summary operations and prompt template management.
"""

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from .models import Summary, SummaryVersion
from .schemas import SummaryFilters, SummaryListResponse, SummaryResponse
from ..files.models import FileMetadata

logger = logging.getLogger(__name__)


class SummaryService:
    """Service class for summary operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_summary(
        self,
        user_id: int,
        file_id: str,
        title: str,
        summary_type: str = "general",
        **kwargs
    ) -> Summary:
        """Create a new summary record."""
        
        # Verify file exists and belongs to user
        file_metadata = self.db.query(FileMetadata).filter(
            and_(
                FileMetadata.id == file_id,
                FileMetadata.user_id == user_id
            )
        ).first()
        
        if not file_metadata:
            raise ValueError("File not found or access denied")
        
        summary = Summary(
            user_id=user_id,
            file_id=file_id,
            title=title,
            summary_type=summary_type,
            content="",  # Will be filled by background task
            **kwargs
        )
        
        self.db.add(summary)
        self.db.commit()
        self.db.refresh(summary)
        
        logger.info(f"Created summary {summary.id} for user {user_id}")
        return summary
    
    def get_summary(self, summary_id: str, user_id: int) -> Optional[Summary]:
        """Get a summary by ID, ensuring user owns it."""
        
        return self.db.query(Summary).filter(
            and_(
                Summary.id == summary_id,
                Summary.user_id == user_id,
                Summary.deleted_at.is_(None)
            )
        ).first()
    
    def get_summaries(
        self,
        user_id: int,
        filters: SummaryFilters
    ) -> SummaryListResponse:
        """Get paginated list of user's summaries with filters."""
        
        query = self.db.query(Summary).filter(
            and_(
                Summary.user_id == user_id,
                Summary.deleted_at.is_(None)
            )
        )
        
        # Apply filters
        if filters.status:
            query = query.filter(Summary.status.in_([s.value for s in filters.status]))
        
        if filters.summary_type:
            query = query.filter(Summary.summary_type.in_([t.value for t in filters.summary_type]))
        
        if filters.ai_provider:
            query = query.filter(Summary.ai_provider.in_([p.value for p in filters.ai_provider]))
        
        if filters.created_after:
            query = query.filter(Summary.created_at >= filters.created_after)
        
        if filters.created_before:
            query = query.filter(Summary.created_at <= filters.created_before)
        
        if filters.min_quality_score:
            query = query.filter(Summary.quality_score >= filters.min_quality_score)
        
        if filters.has_user_rating is not None:
            if filters.has_user_rating:
                query = query.filter(Summary.user_rating.is_not(None))
            else:
                query = query.filter(Summary.user_rating.is_(None))
        
        if filters.search_query:
            search = f"%{filters.search_query}%"
            query = query.filter(
                Summary.title.ilike(search) | 
                Summary.content.ilike(search)
            )
        
        # Apply sorting
        if filters.sort_by == "created_at":
            sort_col = Summary.created_at
        elif filters.sort_by == "updated_at":
            sort_col = Summary.updated_at
        elif filters.sort_by == "title":
            sort_col = Summary.title
        elif filters.sort_by == "quality_score":
            sort_col = Summary.quality_score
        else:
            sort_col = Summary.created_at
        
        if filters.sort_order == "desc":
            query = query.order_by(desc(sort_col))
        else:
            query = query.order_by(sort_col)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.page_size
        summaries = query.offset(offset).limit(filters.page_size).all()
        
        total_pages = (total + filters.page_size - 1) // filters.page_size
        
        return SummaryListResponse(
            summaries=[SummaryResponse.from_orm(s) for s in summaries],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
        )
    
    def update_summary(
        self,
        summary_id: str,
        user_id: int,
        **updates
    ) -> Optional[Summary]:
        """Update summary metadata."""
        
        summary = self.get_summary(summary_id, user_id)
        if not summary:
            return None
        
        for key, value in updates.items():
            if hasattr(summary, key) and value is not None:
                setattr(summary, key, value)
        
        self.db.commit()
        self.db.refresh(summary)
        
        logger.info(f"Updated summary {summary_id} for user {user_id}")
        return summary
    
    def delete_summary(self, summary_id: str, user_id: int) -> bool:
        """Soft delete a summary."""
        
        summary = self.get_summary(summary_id, user_id)
        if not summary:
            return False
        
        summary.soft_delete()
        self.db.commit()
        
        logger.info(f"Deleted summary {summary_id} for user {user_id}")
        return True
    
    def get_user_analytics(self, user_id: int) -> Dict:
        """Get analytics data for a user's summaries."""
        
        summaries = self.db.query(Summary).filter(
            and_(
                Summary.user_id == user_id,
                Summary.deleted_at.is_(None)
            )
        ).all()
        
        total_summaries = len(summaries)
        completed = len([s for s in summaries if s.status == "completed"])
        failed = len([s for s in summaries if s.status == "failed"])
        processing = len([s for s in summaries if s.is_processing])
        
        total_cost = sum(s.generation_cost or 0 for s in summaries)
        total_tokens = sum(s.total_tokens or 0 for s in summaries)
        
        avg_processing_time = 0
        if completed > 0:
            processing_times = [s.processing_time_ms for s in summaries if s.processing_time_ms]
            if processing_times:
                avg_processing_time = sum(processing_times) / len(processing_times)
        
        avg_quality = 0
        quality_scores = [s.quality_score for s in summaries if s.quality_score]
        if quality_scores:
            avg_quality = float(sum(quality_scores) / len(quality_scores))
        
        # Provider usage
        provider_usage = {}
        for summary in summaries:
            provider_usage[summary.ai_provider] = provider_usage.get(summary.ai_provider, 0) + 1
        
        return {
            "total_summaries": total_summaries,
            "completed_summaries": completed,
            "failed_summaries": failed,
            "processing_summaries": processing,
            "total_cost": float(total_cost),
            "total_tokens": total_tokens,
            "average_processing_time_ms": avg_processing_time,
            "average_quality_score": avg_quality,
            "provider_usage": provider_usage,
        }


class PromptTemplateService:
    """Service for managing AI prompt templates."""
    
    SUMMARY_TEMPLATES = {
        "general": {
            "system": """You are an expert at creating clear, concise summaries of documents. 
Your goal is to capture the main points and key insights while maintaining the original meaning.""",
            "user": """Please create a {summary_type} summary of the following document.

Focus on:
- Main themes and key points
- Important details and insights
- Actionable information
- Clear, readable structure

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        },
        
        "executive": {
            "system": """You are creating executive summaries for business leaders. 
Focus on key insights, strategic implications, and actionable recommendations.""",
            "user": """Create an executive summary of the following document for senior leadership.

Focus on:
- Strategic implications and business impact
- Key recommendations and action items
- Critical risks and opportunities
- High-level overview for decision making

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        },
        
        "academic": {
            "system": """You are creating academic summaries that preserve scholarly rigor and precision. 
Maintain academic tone and include methodology and findings.""",
            "user": """Create an academic summary of the following document.

Focus on:
- Research methodology and approach
- Key findings and conclusions
- Theoretical framework and contributions
- Implications for further research

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        },
        
        "technical": {
            "system": """You are creating technical summaries that preserve important technical details 
while making complex information accessible.""",
            "user": """Create a technical summary of the following document.

Focus on:
- Technical specifications and requirements
- Implementation details and architecture
- Performance characteristics and limitations
- Technical recommendations and best practices

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        },
        
        "bullet_points": {
            "system": """You create structured bullet-point summaries that organize information 
into clear, scannable sections.""",
            "user": """Create a bullet-point summary of the following document.

Structure your response as:
• Main Topic/Theme
  - Key point 1
  - Key point 2
  - Key point 3
• Secondary Topics
  - Supporting details
  - Important insights

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        },
        
        "detailed": {
            "system": """You create comprehensive, detailed summaries that preserve important 
nuances while organizing information clearly.""",
            "user": """Create a detailed summary of the following document.

Include:
- Comprehensive coverage of all major sections
- Important supporting details and context
- Relationships between different concepts
- Nuanced explanations of complex topics

{max_length_instruction}

{custom_instructions}

Document content:
{content}"""
        }
    }
    
    def generate_summary_prompt(
        self,
        content: str,
        summary_type: str = "general",
        max_length: Optional[int] = None,
        custom_instructions: Optional[str] = None
    ) -> Tuple[str, str]:
        """Generate system and user prompts for summary generation."""
        
        template = self.SUMMARY_TEMPLATES.get(summary_type, self.SUMMARY_TEMPLATES["general"])
        
        # Format max length instruction
        max_length_instruction = ""
        if max_length:
            max_length_instruction = f"Keep the summary to approximately {max_length} words."
        
        # Format custom instructions
        custom_instructions_text = ""
        if custom_instructions:
            custom_instructions_text = f"Additional instructions: {custom_instructions}"
        
        # Generate prompts
        system_prompt = template["system"]
        
        user_prompt = template["user"].format(
            summary_type=summary_type,
            content=content,
            max_length_instruction=max_length_instruction,
            custom_instructions=custom_instructions_text
        )
        
        return system_prompt, user_prompt
    
    def get_available_templates(self) -> List[str]:
        """Get list of available summary template types."""
        return list(self.SUMMARY_TEMPLATES.keys())
    
    def validate_summary_type(self, summary_type: str) -> bool:
        """Validate if a summary type is supported."""
        return summary_type in self.SUMMARY_TEMPLATES
