"""To-do business logic."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.todo import Todo
from app.models.user import User
from app.schemas.todo import CreateTodoRequest, TodoPublic, UpdateTodoRequest
from app.services import team_service


def to_public(todo: Todo) -> TodoPublic:
    return TodoPublic(
        id=str(todo.id),
        team_id=todo.team_id,
        title=todo.title,
        done=todo.done,
        assignee_id=todo.assignee_id,
        assignee_name=todo.assignee_name,
        created_at=todo.created_at,
    )


async def list_todos(user, team_id: str) -> list[TodoPublic]:
    await team_service.get_team_doc(user, team_id)
    todos = await Todo.find(Todo.team_id == team_id).sort("done", "-created_at").to_list()
    return [to_public(todo) for todo in todos]


async def create_todo(user, team_id: str, payload: CreateTodoRequest) -> TodoPublic:
    await team_service.get_team_doc(user, team_id)
    assignee_name = await _assignee_name(payload.assignee_id, user.class_id)
    todo = Todo(
        class_id=user.class_id,
        team_id=team_id,
        title=payload.title,
        assignee_id=payload.assignee_id,
        assignee_name=assignee_name,
        created_by=str(user.id),
    )
    await todo.insert()
    return to_public(todo)


async def update_todo(user, todo_id: str, payload: UpdateTodoRequest) -> TodoPublic:
    todo = await _get_todo(user, todo_id)
    if payload.done is not None:
        todo.done = payload.done
    if payload.title is not None:
        todo.title = payload.title
    if payload.assignee_id is not None:
        todo.assignee_id = payload.assignee_id or None
        todo.assignee_name = await _assignee_name(todo.assignee_id, user.class_id)
    await todo.save()
    return to_public(todo)


async def delete_todo(user, todo_id: str) -> None:
    todo = await _get_todo(user, todo_id)
    await todo.delete()


async def _assignee_name(assignee_id, class_id):
    if not assignee_id:
        return None
    try:
        member = await User.get(PydanticObjectId(assignee_id))
    except (ValueError, TypeError):
        return None
    if member is None or member.class_id != class_id:
        return None
    return member.name


async def _get_todo(user, todo_id: str) -> Todo:
    if user.class_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="To-do not found.")
    try:
        object_id = PydanticObjectId(todo_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="To-do not found.")
    todo = await Todo.get(object_id)
    if todo is None or todo.class_id != user.class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="To-do not found.")
    return todo
