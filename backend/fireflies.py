from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

from database import get_db
from auth import get_current_active_user
import models
from fireflies_service import list_recent_transcripts, fetch_transcript
from cache_service import cache_clear_pattern

logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models
class TranscriptSummary(BaseModel):
    id: str
    title: str
    date: Optional[str] = None
    duration: int
    participants: List[str]
    participant_count: int

class TranscriptData(BaseModel):
    transcript: str
    sentences: List[dict]
    participants: List[dict]
    meeting_title: str
    meeting_date: Optional[str] = None
    duration: int
    source: str
    meeting_id: str

@router.get("/fireflies/transcripts", response_model=List[TranscriptSummary])
async def get_fireflies_transcripts(
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List recent transcripts from Fireflies.ai
    """
    try:
        transcripts = await list_recent_transcripts(db, current_user.id, limit)
        return transcripts
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error fetching Fireflies transcripts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch transcripts: {str(e)}"
        )

@router.get("/fireflies/transcripts/{transcript_id}", response_model=TranscriptData)
async def get_fireflies_transcript(
    transcript_id: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Fetch a specific transcript from Fireflies.ai by ID
    """
    try:
        transcript_data = await fetch_transcript(transcript_id, db, current_user.id)

        if not transcript_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transcript not found: {transcript_id}"
            )

        return transcript_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Fireflies transcript {transcript_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch transcript: {str(e)}"
        )

@router.post("/fireflies/cache/clear")
async def clear_fireflies_cache(
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Clear cached Fireflies transcripts for the current user.
    Use this to force refresh when new meetings are added.
    """
    try:
        # Clear cache for this specific user
        pattern = f"fireflies:transcripts:user_{current_user.id}:*"
        deleted_count = cache_clear_pattern(pattern)

        logger.info(f"Cleared {deleted_count} cache entries for user {current_user.id}")

        return {
            "success": True,
            "message": f"Cleared {deleted_count} cached transcript entries",
            "cache_cleared": deleted_count > 0
        }
    except Exception as e:
        logger.error(f"Error clearing Fireflies cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )
