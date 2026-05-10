import httpx
import logging
from typing import Dict, Any, List, Optional
import os
from datetime import datetime
from sqlalchemy.orm import Session
from cache_service import cache_get, cache_set
from tracing import traced_call

logger = logging.getLogger(__name__)


async def fetch_transcript(meeting_id: str, db: Session = None, user_id: int = None) -> Dict[str, Any]:
    """
    Fetch transcript from Fireflies.ai using GraphQL API
    
    Args:
        meeting_id: The Fireflies meeting ID
        
    Returns:
        Dict containing transcript sentences, meeting attendees, and formatted data
    """
    
    # Get API key - try user's personal key first, fall back to global env key
    fireflies_api_key = None
    fireflies_api_url = os.getenv("FIREFLIES_API_URL", "https://api.fireflies.ai/graphql")

    # Try to get user's personal API key
    if db and user_id:
        try:
            from api_keys import get_decrypted_api_key
            fireflies_api_key = get_decrypted_api_key(db, user_id, "fireflies")
            if fireflies_api_key:
                logger.info(f"Using personal Fireflies API key for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to retrieve user API key: {e}")

    # Fall back to global environment variable
    if not fireflies_api_key:
        fireflies_api_key = os.getenv("FIREFLIES_API_KEY")
        if fireflies_api_key:
            logger.warning("Using global FIREFLIES_API_KEY from environment. Consider adding personal API key for better security.")

    if not fireflies_api_key:
        logger.error("FIREFLIES_API_KEY not configured - no personal or global key found")
        raise ValueError("Fireflies API key not configured. Please add your API key in settings.")
    
    # GraphQL query to fetch transcript
    query = """
    query GetTranscript($id: String!) {
        transcript(id: $id) {
            sentences {
                speaker_name
                text
            }
            meeting_attendees {
                displayName
                email
                name
            }
            speakers {
                id
                name
            }
            meeting_attendance {
                name
            }
            user {
                name
                email
            }
            organizer_email
            title
            date
            duration
            transcript_url
            meeting_link
            summary {
                keywords
                action_items
                short_summary
                overview
            }
            analytics {
                sentiments {
                    negative_pct
                    neutral_pct
                    positive_pct
                }
            }
        }
    }
    """
    
    # Prepare the request
    headers = {
        "Authorization": f"Bearer {fireflies_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query,
        "variables": {
            "id": meeting_id
        }
    }
    
    # Make the GraphQL request
    async with httpx.AsyncClient() as client:
        try:
            async with traced_call(
                "fireflies.fetch_transcript",
                request={"meeting_id": meeting_id, "url": fireflies_api_url},
            ) as t:
                response = await client.post(
                    fireflies_api_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                if t:
                    transcript = (data.get("data") or {}).get("transcript") or {}
                    t["response"] = {
                        "status_code": response.status_code,
                        "title": transcript.get("title"),
                        "duration": transcript.get("duration"),
                        "sentence_count": len(transcript.get("sentences") or []),
                        "attendee_count": len(transcript.get("meeting_attendees") or []),
                        "errors": data.get("errors"),
                    }

            # Check for GraphQL errors
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                raise Exception(f"Fireflies API error: {data['errors']}")

            # Extract transcript data
            transcript_data = data.get("data", {}).get("transcript", {})
            
            if not transcript_data:
                logger.warning(f"No transcript data found for meeting ID: {meeting_id}")
                return None
            
            sentences = transcript_data.get("sentences", [])
            meeting_attendees = transcript_data.get("meeting_attendees", [])
            speakers = transcript_data.get("speakers", [])
            title = transcript_data.get("title", "")
            summary_data = transcript_data.get("summary") or {}
            analytics_data = transcript_data.get("analytics") or {}

            # Convert date from Unix timestamp to ISO format if needed
            date_value = transcript_data.get("date", "")
            if isinstance(date_value, (int, float)):
                # Convert Unix timestamp (milliseconds) to ISO format string
                date = datetime.fromtimestamp(date_value / 1000).isoformat()
            else:
                date = date_value

            # Convert duration to int if it's a float
            duration_value = transcript_data.get("duration", 0)
            duration = int(duration_value) if isinstance(duration_value, float) else duration_value

            # Format transcript as text
            transcript_text = "\n".join([
                f"{sentence['speaker_name']}: {sentence['text']}"
                for sentence in sentences
            ])

            # Build participants by merging attendee emails with speaker/attendance names
            # Step 1: Collect all known names from speakers and meeting_attendance
            attendance = transcript_data.get("meeting_attendance") or []
            host_user = transcript_data.get("user") or {}
            organizer_email = transcript_data.get("organizer_email", "")
            known_names = []
            for s in speakers:
                if s.get("name"):
                    known_names.append(s["name"])
            for a in attendance:
                if a.get("name") and a["name"] not in known_names:
                    known_names.append(a["name"])

            # Step 2: Build email→name mapping
            email_to_name = {}
            # The host/organizer is identifiable
            if host_user.get("name") and host_user.get("email"):
                email_to_name[host_user["email"].lower()] = host_user["name"]
            if host_user.get("name") and organizer_email:
                email_to_name[organizer_email.lower()] = host_user["name"]

            # Step 3: Try to match remaining names to remaining emails
            # Get attendee emails that don't have names yet
            attendee_emails = [a.get("email", "").lower() for a in meeting_attendees if a.get("email")]
            unmatched_names = [n for n in known_names if n not in email_to_name.values()]
            unmatched_emails = [e for e in attendee_emails if e not in email_to_name]

            # Only match when exactly one unmatched name and one unmatched email — guaranteed correct
            # For multiple unmatched, positional order isn't reliable so leave names empty
            if len(unmatched_names) == 1 and len(unmatched_emails) == 1:
                email_to_name[unmatched_emails[0]] = unmatched_names[0]

            # Step 4: Build final participants list
            participants = []
            seen_emails = set()
            for attendee in meeting_attendees:
                email = attendee.get("email", "")
                if not email or email.lower() in seen_emails:
                    continue
                seen_emails.add(email.lower())
                name = email_to_name.get(email.lower()) or attendee.get("displayName") or attendee.get("name") or ""
                is_organizer = email.lower() == organizer_email.lower() if organizer_email else False
                participants.append({"name": name, "email": email, "is_organizer": is_organizer})

            # Extract sentiment from analytics
            sentiments = analytics_data.get("sentiments") or {}
            sentiment = {}
            if sentiments:
                sentiment = {
                    "positive": f"{sentiments.get('positive_pct', 0)}%",
                    "neutral": f"{sentiments.get('neutral_pct', 0)}%",
                    "negative": f"{sentiments.get('negative_pct', 0)}%",
                }

            # Extract action items — Fireflies returns them as a single markdown string
            action_items_raw = summary_data.get("action_items", "")
            action_items = []
            if action_items_raw and isinstance(action_items_raw, str):
                for line in action_items_raw.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("**"):  # Skip speaker header lines
                        action_items.append(line)

            # Use Fireflies summary if available
            summary = summary_data.get("short_summary") or summary_data.get("overview") or ""

            # Meeting URL: prefer transcript_url (Fireflies viewer), fall back to meeting_link (Zoom/Meet)
            meeting_url = transcript_data.get("transcript_url") or transcript_data.get("meeting_link") or ""

            return {
                "transcript": transcript_text,
                "sentences": sentences,
                "participants": participants,
                "organizer_email": transcript_data.get("organizer_email", ""),
                "meeting_title": title,
                "meeting_url": meeting_url,
                "meeting_date": date,
                "duration": duration,
                "summary": summary,
                "action_items": action_items,
                "keywords": summary_data.get("keywords") or [],
                "sentiment": sentiment,
                "source": "fireflies_api",
                "meeting_id": meeting_id
            }
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching transcript for meeting {meeting_id}: {str(e)}")
            raise Exception(f"Failed to fetch transcript: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching transcript for meeting {meeting_id}: {str(e)}")
            raise


async def get_meeting_url(meeting_id: str, db: Session = None, user_id: int = None) -> Optional[str]:
    """
    Get the meeting URL for a given meeting ID

    Args:
        meeting_id: The Fireflies meeting ID

    Returns:
        Meeting URL if available, None otherwise
    """

    # Get API key - try user's personal key first, fall back to global env key
    fireflies_api_key = None
    fireflies_api_url = os.getenv("FIREFLIES_API_URL", "https://api.fireflies.ai/graphql")

    # Try to get user's personal API key
    if db and user_id:
        try:
            from api_keys import get_decrypted_api_key
            fireflies_api_key = get_decrypted_api_key(db, user_id, "fireflies")
        except Exception as e:
            logger.warning(f"Failed to retrieve user API key: {e}")

    # Fall back to global environment variable
    if not fireflies_api_key:
        fireflies_api_key = os.getenv("FIREFLIES_API_KEY")

    if not fireflies_api_key:
        return None

    query = """
    query GetMeetingUrl($id: String!) {
        transcript(id: $id) {
            transcript_url
            meeting_link
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {fireflies_api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "query": query,
        "variables": {
            "id": meeting_id
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                fireflies_api_url,
                json=payload,
                headers=headers,
                timeout=15.0
            )
            response.raise_for_status()

            data = response.json()

            if "errors" in data:
                logger.error(f"GraphQL errors fetching meeting URL: {data['errors']}")
                return None

            transcript_data = data.get("data", {}).get("transcript", {})
            return transcript_data.get("transcript_url") or transcript_data.get("meeting_link")

    except Exception as e:
        logger.error(f"Error fetching meeting URL for {meeting_id}: {str(e)}")
        return None


async def list_recent_transcripts(db: Session = None, user_id: int = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    List recent transcripts from Fireflies.ai with Redis caching

    Args:
        db: Database session
        user_id: User ID to fetch personal API key
        limit: Maximum number of transcripts to return (default 20)

    Returns:
        List of transcript summaries with id, title, date, and duration
    """

    # Create cache key based on user_id and limit
    cache_key = f"fireflies:transcripts:user_{user_id or 'global'}:limit_{limit}"

    # Try to get from cache first
    cached_result = cache_get(cache_key)
    if cached_result is not None:
        logger.info(f"Returning cached transcripts for user {user_id}")
        return cached_result

    # Get API key - try user's personal key first, fall back to global env key
    fireflies_api_key = None
    fireflies_api_url = os.getenv("FIREFLIES_API_URL", "https://api.fireflies.ai/graphql")

    # Try to get user's personal API key
    if db and user_id:
        try:
            from api_keys import get_decrypted_api_key
            fireflies_api_key = get_decrypted_api_key(db, user_id, "fireflies")
            if fireflies_api_key:
                logger.info(f"Using personal Fireflies API key for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to retrieve user API key: {e}")

    # Fall back to global environment variable
    if not fireflies_api_key:
        fireflies_api_key = os.getenv("FIREFLIES_API_KEY")
        if fireflies_api_key:
            logger.warning("Using global FIREFLIES_API_KEY from environment")

    if not fireflies_api_key:
        logger.error("FIREFLIES_API_KEY not configured")
        raise ValueError("Fireflies API key not configured. Please add your API key in settings.")

    # GraphQL query to list transcripts
    query = """
    query GetTranscripts($limit: Int!) {
        transcripts(limit: $limit) {
            id
            title
            date
            duration
            meeting_attendees {
                name
                email
            }
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {fireflies_api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "query": query,
        "variables": {
            "limit": limit
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                fireflies_api_url,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

            data = response.json()

            # Check for GraphQL errors
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                raise Exception(f"Fireflies API error: {data['errors']}")

            # Extract transcripts data
            transcripts = data.get("data", {}).get("transcripts", [])

            # Format transcript summaries
            result = []
            for transcript in transcripts:
                # Extract participants, handling None values
                participants = []
                for attendee in transcript.get("meeting_attendees", []):
                    name = attendee.get("name") or attendee.get("email") or "Unknown"
                    if name and name != "Unknown":  # Only add non-Unknown participants
                        participants.append(name)

                # Convert date from timestamp to string if needed
                date_value = transcript.get("date")
                if isinstance(date_value, (int, float)):
                    # Convert Unix timestamp (milliseconds) to ISO format string
                    date_str = datetime.fromtimestamp(date_value / 1000).isoformat()
                else:
                    date_str = date_value

                # Convert duration to int if it's a float
                duration = transcript.get("duration", 0)
                duration_int = int(duration) if isinstance(duration, float) else duration

                result.append({
                    "id": transcript.get("id"),
                    "title": transcript.get("title", "Untitled Meeting"),
                    "date": date_str,
                    "duration": duration_int,
                    "participants": participants[:3],  # Limit to first 3 participants
                    "participant_count": len(participants)
                })

            # Cache the result for 15 minutes (900 seconds)
            cache_set(cache_key, result, ttl=900)
            logger.info(f"Cached {len(result)} transcripts for user {user_id}")

            return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching transcripts: {str(e)}")
            raise Exception(f"Failed to fetch transcripts: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching transcripts: {str(e)}")
            raise