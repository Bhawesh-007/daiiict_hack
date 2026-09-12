"""FastAPI application entry-point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.assessments import router as assessments_router
from app.api.companies import router as companies_router
from app.api.identification import router as identification_router
from app.api.knowledge import router as knowledge_router
from app.api.processes import router as processes_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Layer-1 Emission Source Identification & Calculation API",
)

# Enable CORS for local Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies_router)
app.include_router(assessments_router)
app.include_router(knowledge_router)
app.include_router(processes_router)
app.include_router(identification_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
