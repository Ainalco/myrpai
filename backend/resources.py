import os
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

from database import get_db
from auth import get_current_active_user
from plan_features import get_feature_limit
import models

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB default

# Cloudflare R2 configuration (S3-compatible)
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def _r2_key(account_id: int, resource_id: int) -> str:
    return f"resources/{account_id}/{resource_id}.pdf"


class ResourceCreate(BaseModel):
    type: str
    label: str
    description: Optional[str] = None
    url: Optional[str] = None


class ResourceUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None


class ResourceResponse(BaseModel):
    id: int
    account_id: int
    type: str
    label: str
    description: Optional[str] = None
    url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_original_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _get_account(db: Session, user: models.User) -> models.Account:
    if not user.org_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    account = db.query(models.Account).filter(models.Account.org_id == user.org_id).first()
    if not account:
        raise HTTPException(status_code=400, detail="No account found for organization")
    return account


def _check_plan_limit(db: Session, account: models.Account, resource_type: str):
    limit_key = "max_resource_links" if resource_type == "link" else "max_resource_files"
    limit = get_feature_limit(account, limit_key)
    if limit is not None:
        current_count = db.query(models.Resource).filter(
            models.Resource.account_id == account.id,
            models.Resource.type == resource_type,
        ).count()
        if current_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Plan limit reached: {current_count}/{limit} {resource_type}s. Upgrade for more.",
            )


@router.get("/resources", response_model=List[ResourceResponse])
async def list_resources(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = _get_account(db, current_user)
    resources = (
        db.query(models.Resource)
        .filter(models.Resource.account_id == account.id)
        .order_by(models.Resource.created_at.desc())
        .all()
    )
    return resources


@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: ResourceCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if data.type not in ("link", "file"):
        raise HTTPException(status_code=400, detail="type must be 'link' or 'file'")
    if data.type == "link" and not data.url:
        raise HTTPException(status_code=400, detail="URL is required for link resources")
    if not data.label or len(data.label.strip()) == 0:
        raise HTTPException(status_code=400, detail="Label is required")
    if len(data.label) > 50:
        raise HTTPException(status_code=400, detail="Label must be 50 characters or less")

    account = _get_account(db, current_user)
    _check_plan_limit(db, account, data.type)

    existing = db.query(models.Resource).filter(
        models.Resource.account_id == account.id,
        models.Resource.type == data.type,
        models.Resource.label == data.label.strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A {data.type} resource with label '{data.label}' already exists")

    resource = models.Resource(
        account_id=account.id,
        type=data.type,
        label=data.label.strip(),
        description=data.description,
        url=data.url,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    logger.info(f"Resource created: id={resource.id} type={resource.type} label={resource.label}")
    return resource


@router.post("/resources/upload", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_resource(
    file: UploadFile = File(...),
    label: str = Form(...),
    description: str = Form(""),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if not label or len(label.strip()) == 0:
        raise HTTPException(status_code=400, detail="Label is required")
    if len(label) > 50:
        raise HTTPException(status_code=400, detail="Label must be 50 characters or less")

    account = _get_account(db, current_user)
    _check_plan_limit(db, account, "file")

    existing = db.query(models.Resource).filter(
        models.Resource.account_id == account.id,
        models.Resource.type == "file",
        models.Resource.label == label.strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A file resource with label '{label}' already exists")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)}MB")

    resource = models.Resource(
        account_id=account.id,
        type="file",
        label=label.strip(),
        description=description or None,
        file_size_bytes=len(content),
        file_original_name=file.filename,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    r2_key = _r2_key(account.id, resource.id)
    try:
        s3 = _get_r2_client()
        s3.put_object(Bucket=R2_BUCKET_NAME, Key=r2_key, Body=content, ContentType="application/pdf")
    except ClientError as e:
        db.delete(resource)
        db.commit()
        logger.error(f"R2 upload failed for resource {resource.id}: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

    resource.file_path = r2_key
    db.commit()
    db.refresh(resource)

    logger.info(f"PDF resource uploaded: id={resource.id} size={len(content)} filename={file.filename}")

    # RAG: extract text from PDF and store embeddings (synchronous, non-blocking on failure)
    try:
        from rag_service import extract_text_from_pdf, store_resource as rag_store_resource

        pdf_text = extract_text_from_pdf(content)
        if pdf_text and pdf_text.strip():
            stored = await rag_store_resource(
                db=db,
                account_id=account.id,
                resource_id=resource.id,
                text_content=pdf_text,
                resource_label=resource.label,
            )
            logger.info(f"RAG: stored {stored} embeddings for resource {resource.id}")
        else:
            logger.warning(f"RAG: no text extracted from PDF resource {resource.id}")
    except Exception as e:
        # RAG embedding failure should not block the upload
        logger.error(f"RAG embedding failed for resource {resource.id}: {e}")

    return resource


@router.put("/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = _get_account(db, current_user)
    resource = db.query(models.Resource).filter(
        models.Resource.id == resource_id,
        models.Resource.account_id == account.id,
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    if data.label is not None:
        if len(data.label) > 50:
            raise HTTPException(status_code=400, detail="Label must be 50 characters or less")
        if data.label.strip() != resource.label:
            existing = db.query(models.Resource).filter(
                models.Resource.account_id == account.id,
                models.Resource.type == resource.type,
                models.Resource.label == data.label.strip(),
                models.Resource.id != resource.id,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"A {resource.type} resource with label '{data.label}' already exists")
        resource.label = data.label.strip()
    if data.description is not None:
        resource.description = data.description
    if data.url is not None and resource.type == "link":
        resource.url = data.url

    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = _get_account(db, current_user)
    resource = db.query(models.Resource).filter(
        models.Resource.id == resource_id,
        models.Resource.account_id == account.id,
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    if resource.type == "file" and resource.file_path:
        try:
            s3 = _get_r2_client()
            s3.delete_object(Bucket=R2_BUCKET_NAME, Key=resource.file_path)
        except ClientError as e:
            logger.warning(f"Failed to delete R2 object {resource.file_path}: {e}")

    # Clean up RAG embeddings for this resource
    try:
        source_id = f"resource:{resource_id}"
        db.query(models.ContentEmbedding).filter(
            models.ContentEmbedding.source_type == "resource",
            models.ContentEmbedding.source_id == source_id,
        ).delete()
    except Exception as e:
        logger.warning(f"Failed to clean up RAG embeddings for resource {resource_id}: {e}")

    db.delete(resource)
    db.commit()
    logger.info(f"Resource deleted: id={resource_id}")


@router.patch("/resources/{resource_id}/toggle", response_model=ResourceResponse)
async def toggle_resource(
    resource_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = _get_account(db, current_user)
    resource = db.query(models.Resource).filter(
        models.Resource.id == resource_id,
        models.Resource.account_id == account.id,
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource.is_active = not resource.is_active
    db.commit()
    db.refresh(resource)
    logger.info(f"Resource toggled: id={resource_id} is_active={resource.is_active}")
    return resource
