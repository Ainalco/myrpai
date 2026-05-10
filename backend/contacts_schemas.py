"""
Pydantic schemas for the contact system API.
Field names match the frontend contract exactly (camelCase where needed).
"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone


# --- Utility functions for formatting ---

def format_relative_time(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to relative time string: '2h ago', '1d ago', '3d ago', '1w ago'"""
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    # Handle naive datetimes from legacy data
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 3600:
        return f"{max(1, int(seconds / 60))}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    elif diff.days < 7:
        return f"{diff.days}d ago"
    elif diff.days < 30:
        return f"{diff.days // 7}w ago"
    elif diff.days < 365:
        return f"{diff.days // 30}mo ago"
    else:
        return f"{diff.days // 365}y ago"


def format_rate(reply_rate: Optional[float]) -> str:
    """Format reply rate as string with percent sign: '34.8%'"""
    if reply_rate is None or reply_rate == 0:
        return "0.0%"
    return f"{reply_rate:.1f}%"


def format_date_long(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Apr 15, 2026'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d, %Y")


def format_datetime_short(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Mar 13, 10:24 AM'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d, %-I:%M %p")


def format_date_short(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'Mar 13'"""
    if dt is None:
        return None
    return dt.strftime("%b %-d")


# --- Stats ---

class ContactStatsResponse(BaseModel):
    sent: int = 0
    received: int = 0
    rate: str = "0.0%"
    meetings: int = 0
    sequences: int = 0
    openDeals: int = 0
    dealValue: float = 0


# --- Pulse ---

class ContactPulseResponse(BaseModel):
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    engagement: Optional[str] = None
    intent: Optional[str] = None
    action: Optional[str] = None
    topics: List[str] = []
    objections: List[str] = []
    lastMeeting: Optional[str] = None


# --- Deals ---

class ContactDealResponse(BaseModel):
    id: int
    title: str
    status: str
    stage: Optional[str] = None
    value: Optional[float] = None
    expected: Optional[str] = None
    externalUrl: Optional[str] = None


# --- Timeline ---

class TimelineEventResponse(BaseModel):
    id: int
    type: str
    dir: Optional[str] = None
    source: Optional[str] = None
    subject: Optional[str] = None
    summary: Optional[str] = None
    at: Optional[str] = None
    deal: Optional[str] = None


# --- Threads ---

class ThreadMessageResponse(BaseModel):
    id: str
    sender: str = Field(serialization_alias="from")  # "you" or email address
    to: str
    subject: Optional[str] = None
    body: Optional[str] = None
    at: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ThreadResponse(BaseModel):
    id: str
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    status: Optional[str] = None
    msgs: int = 0
    lastAt: Optional[str] = None
    messages: List[ThreadMessageResponse] = []


# --- Meetings ---

class MeetingResponse(BaseModel):
    id: int
    date: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    keyPoints: List[str] = []
    objections: List[str] = []
    signals: List[str] = []
    stage: Optional[str] = None


# --- Contact List Item (GET /contacts) ---

class ContactListItem(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    orgId: Optional[int] = None
    orgName: Optional[str] = None
    status: str = "active"
    pipedrive: bool = False
    lastActivity: Optional[str] = None
    stats: ContactStatsResponse = ContactStatsResponse()
    emails: List[str] = []


class StatusCounts(BaseModel):
    active: int = 0
    paused: int = 0
    dnc: int = 0
    bounced: int = 0


class ContactListResponse(BaseModel):
    items: List[ContactListItem]
    counts: StatusCounts
    nextCursor: Optional[int] = None
    hasMore: bool = False


# --- Contact Detail (GET /contacts/{id}) ---

class ContactDetailResponse(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    orgId: Optional[int] = None
    orgName: Optional[str] = None
    status: str = "active"
    pipedrive: bool = False
    lastActivity: Optional[str] = None
    emails: List[str] = []
    stats: ContactStatsResponse = ContactStatsResponse()
    pulse: ContactPulseResponse = ContactPulseResponse()  # Never null — frontend accesses p.sentiment without null check
    deals: List[ContactDealResponse] = []
    timeline: List[TimelineEventResponse] = []
    threads: List[ThreadResponse] = []
    meetings: List[MeetingResponse] = []


# --- Organization List ---

class OrgListItem(BaseModel):
    id: int
    name: str
    domain: Optional[str] = None
    contacts: int = 0
    openDeals: int = 0
    totalValue: float = 0
    dnc: bool = False
    dncProp: bool = True


class OrgListResponse(BaseModel):
    items: List[OrgListItem]
    nextCursor: Optional[int] = None
    hasMore: bool = False


class OrgPersonItem(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    status: str = "active"


class OrgDetailResponse(BaseModel):
    id: int
    name: str
    domain: Optional[str] = None
    contacts: int = 0
    openDeals: int = 0
    totalValue: float = 0
    dnc: bool = False
    dncProp: bool = True
    persons: List[OrgPersonItem] = []


# --- Request Schemas ---

class ContactCreateRequest(BaseModel):
    email: str
    name: Optional[str] = None
    organization_name: Optional[str] = None


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    contact_organization_id: Optional[int] = None


class ContactStatusRequest(BaseModel):
    status: str  # active, paused, do_not_contact, bounced


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = None
    do_not_contact_propagation: Optional[bool] = None
    dnc: Optional[bool] = None


class ContactNoteRequest(BaseModel):
    content: str


class ContactMergeRequest(BaseModel):
    merge_id: int  # ID of contact to merge into this one
