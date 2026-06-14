"""
Announcement endpoints for the High School Management System API
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(min_length=5, max_length=300)
    expires_on: str
    starts_on: Optional[str] = None


def _validate_dates(starts_on: Optional[str], expires_on: str) -> None:
    try:
        expires_date = date.fromisoformat(expires_on)
        starts_date = date.fromisoformat(starts_on) if starts_on else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD format") from exc

    if starts_date and starts_date > expires_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after expiration date")


def _require_authenticated_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "message": doc["message"],
        "starts_on": doc.get("starts_on"),
        "expires_on": doc["expires_on"],
        "created_by": doc.get("created_by"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at")
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get currently active announcements for display in the public banner."""
    today = date.today().isoformat()

    query = {
        "expires_on": {"$gte": today},
        "$or": [
            {"starts_on": {"$exists": False}},
            {"starts_on": None},
            {"starts_on": {"$lte": today}}
        ]
    }

    docs = announcements_collection.find(query).sort("expires_on", 1)
    return [_serialize_announcement(doc) for doc in docs]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management; requires teacher authentication."""
    _require_authenticated_teacher(teacher_username)

    docs = announcements_collection.find({}).sort("updated_at", -1)
    return [_serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Create a new announcement; requires teacher authentication."""
    teacher = _require_authenticated_teacher(teacher_username)
    _validate_dates(payload.starts_on, payload.expires_on)

    now_iso = datetime.utcnow().isoformat() + "Z"
    new_doc = {
        "message": payload.message.strip(),
        "starts_on": payload.starts_on,
        "expires_on": payload.expires_on,
        "created_by": teacher["username"],
        "created_at": now_iso,
        "updated_at": now_iso
    }

    result = announcements_collection.insert_one(new_doc)
    saved = announcements_collection.find_one({"_id": result.inserted_id})
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _serialize_announcement(saved)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement; requires teacher authentication."""
    _require_authenticated_teacher(teacher_username)
    _validate_dates(payload.starts_on, payload.expires_on)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "message": payload.message.strip(),
                "starts_on": payload.starts_on,
                "expires_on": payload.expires_on,
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    saved = announcements_collection.find_one({"_id": object_id})
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(saved)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Delete an announcement; requires teacher authentication."""
    _require_authenticated_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
