"""Docs & Files routes."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.doc import CreateDocRequest, DocPublic
from app.services import doc_service

router = APIRouter(tags=["docs"])


@router.get("/teams/{team_id}/docs", response_model=list[DocPublic])
async def list_docs(team_id: str, current_user: User = Depends(get_current_user)) -> list[DocPublic]:
    return await doc_service.list_docs(current_user, team_id)


@router.post("/teams/{team_id}/docs", response_model=DocPublic, status_code=status.HTTP_201_CREATED)
async def create_doc(
    team_id: str, payload: CreateDocRequest, current_user: User = Depends(get_current_user)
) -> DocPublic:
    return await doc_service.create_doc(current_user, team_id, payload)


@router.delete("/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(doc_id: str, current_user: User = Depends(get_current_user)) -> None:
    await doc_service.delete_doc(current_user, doc_id)
