from fastapi import APIRouter, UploadFile, File
from ..schemas import UploadResponse
from ..services.storage import storage_service

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/video", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    content = await file.read()
    ref = storage_service.save_file(file.filename or "video.mp4", content)
    return UploadResponse(ref=ref)


@router.post("/image", response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()
    ref = storage_service.save_file(file.filename or "image.png", content)
    return UploadResponse(ref=ref)


@router.post("/audio", response_model=UploadResponse)
async def upload_audio(file: UploadFile = File(...)):
    content = await file.read()
    ref = storage_service.save_file(file.filename or "reference.wav", content)
    return UploadResponse(ref=ref)
