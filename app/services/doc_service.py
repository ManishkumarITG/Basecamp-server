"""Docs & Files business logic."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.doc import Doc
from app.schemas.doc import CreateDocRequest, DocPublic
from app.services import activity_service, team_service


def to_public(doc: Doc) -> DocPublic:
    return DocPublic(
        id=str(doc.id),
        team_id=doc.team_id,
        title=doc.title,
        kind=doc.kind,
        url=doc.url,
        created_at=doc.created_at,
    )


async def list_docs(user, team_id: str) -> list[DocPublic]:
    await team_service.get_team_doc(user, team_id)
    docs = await Doc.find(Doc.team_id == team_id).sort("-created_at").to_list()
    return [to_public(doc) for doc in docs]


async def create_doc(user, team_id: str, payload: CreateDocRequest) -> DocPublic:
    team = await team_service.get_team_doc(user, team_id)
    doc = Doc(
        class_id=user.class_id,
        team_id=team_id,
        title=payload.title,
        kind=payload.kind,
        url=payload.url,
        created_by=str(user.id),
    )
    await doc.insert()
    await activity_service.record(
        class_id=user.class_id,
        actor=user,
        verb="added a document",
        team_id=team_id,
        team_name=team.name,
        target_type="doc",
        target_title=doc.title,
        target_id=str(doc.id),
    )
    return to_public(doc)


async def delete_doc(user, doc_id: str) -> None:
    if user.class_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    try:
        object_id = PydanticObjectId(doc_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    doc = await Doc.get(object_id)
    if doc is None or doc.class_id != user.class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    await doc.delete()
