from fastapi import APIRouter, UploadFile, File
from app.services.ingestion_service import ingest_pdf

router = APIRouter()

@router.post("/")
async def ingest(file: UploadFile = File(...)):
    return await ingest_pdf(file)