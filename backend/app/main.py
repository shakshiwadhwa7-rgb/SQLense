"""SQLense FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import explain, health, practice, sql
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="AI-powered SQL database copilot",
)

app.include_router(health.router, tags=["health"])
app.include_router(sql.router, prefix="/api/v1/sql", tags=["sql"])
app.include_router(explain.router, prefix="/api/v1/sql", tags=["sql"])
app.include_router(practice.router, prefix="/api/v1/practice", tags=["practice"])


@app.get("/")
async def root():
    return {"message": "Welcome to SQLense API", "docs": "/docs"}
