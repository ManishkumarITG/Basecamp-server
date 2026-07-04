"""Aggregates all v1 routers into a single router mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1.routes import (
    activity,
    auth,
    cards,
    classes,
    comments,
    docs,
    health,
    teams,
    todos,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(classes.router)
api_router.include_router(teams.router)
api_router.include_router(cards.router)
api_router.include_router(comments.router)
api_router.include_router(todos.router)
api_router.include_router(docs.router)
api_router.include_router(activity.router)
api_router.include_router(ws.router)
