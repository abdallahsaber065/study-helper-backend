"""
Summary generation service for handling AI-powered summaries.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from models.models import User, Summary, ContentTypeEnum
from services.ai_manager import AIManager
from services.notification_service import NotificationService


class SummaryResponse(BaseModel):
    """Structured response schema for summary generation."""

    title: str = Field(..., description="A concise title for the summary")
    summary_markdown: str = Field(..., description="The full markdown summary content")
    key_points: list[str] = Field(
        ..., description="List of key points from the content"
    )


class SummaryGeneratorService:
    """
    Service for generating summaries using AI.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ai_manager = AIManager(db)

    async def generate_summary(
        self,
        user: User,
        physical_file_ids: List[int] = None,
        custom_instructions: str = None,
        community_id: Optional[int] = None,
    ) -> Summary:
        """
        Generate a summary from files, text, or both using AI.

        Args:
            user: The user requesting the summary
            physical_file_ids: Optional list of file IDs to summarize
            text_content: Optional text content to summarize
            custom_instructions: Optional custom instructions for the AI
            community_id: Optional community ID to associate with the summary

        Returns:
            Summary: The generated summary
        """

        with open(
            "prompts/summary/system_instruction.md", "r", encoding="utf-8"
        ) as file:
            system_instruction = file.read()

        # Construct the prompt
        base_prompt = "Create a comprehensive summary of the provided content. Include: 1) A concise title, 2) A detailed summary in markdown format with headings and bullet points, 3) Key points or takeaways. Ensure the summary is well-structured, clear, and captures the main concepts."

        prompt = custom_instructions if custom_instructions else base_prompt

        # Generate summary using AI
        summary_data = await self.ai_manager.generate_content_with_gemini(
            user_id=user.id,
            prompt=prompt,
            physical_file_ids=physical_file_ids,
            response_schema=SummaryResponse,
            system_instruction=system_instruction,
        )

        # Check if we got a structured response
        if not isinstance(summary_data, SummaryResponse):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to generate a structured summary",
            )

        # Create a new Summary record
        new_summary = Summary(
            user_id=user.id,
            title=summary_data.title,
            full_markdown=summary_data.summary_markdown,
        )

        # If we have files, associate the first file with the summary
        if physical_file_ids and len(physical_file_ids) > 0:
            new_summary.physical_file_id = physical_file_ids[0]

        if community_id:
            new_summary.community_id = community_id

        self.db.add(new_summary)
        self.db.commit()
        self.db.refresh(new_summary)

        # Send notifications for community content
        if community_id:
            notification_service = NotificationService(self.db)
            notification_service.notify_new_community_content(
                content_type=ContentTypeEnum.summary,
                content_id=new_summary.id,
                community_id=community_id,
                actor_id=user.id,
                content_title=summary_data.title
            )

        return new_summary
