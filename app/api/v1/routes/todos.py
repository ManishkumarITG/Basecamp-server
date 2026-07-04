"""To-do routes."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.todo import CreateTodoRequest, TodoPublic, UpdateTodoRequest
from app.services import todo_service

router = APIRouter(tags=["todos"])


@router.get("/teams/{team_id}/todos", response_model=list[TodoPublic])
async def list_todos(team_id: str, current_user: User = Depends(get_current_user)) -> list[TodoPublic]:
    return await todo_service.list_todos(current_user, team_id)


@router.post("/teams/{team_id}/todos", response_model=TodoPublic, status_code=status.HTTP_201_CREATED)
async def create_todo(
    team_id: str, payload: CreateTodoRequest, current_user: User = Depends(get_current_user)
) -> TodoPublic:
    return await todo_service.create_todo(current_user, team_id, payload)


@router.patch("/todos/{todo_id}", response_model=TodoPublic)
async def update_todo(
    todo_id: str, payload: UpdateTodoRequest, current_user: User = Depends(get_current_user)
) -> TodoPublic:
    return await todo_service.update_todo(current_user, todo_id, payload)


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: str, current_user: User = Depends(get_current_user)) -> None:
    await todo_service.delete_todo(current_user, todo_id)
