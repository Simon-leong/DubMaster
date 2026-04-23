import io
import os
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, FileResponse
from typing import List
from ..schemas import GenerationPayload, GenerationResponse, Artifact, ExportResponse, GenerationStatus
from ..services.generation_service import generation_service
from ..services.storage import storage_service

router = APIRouter(prefix="/generations", tags=["generations"])


@router.post("", response_model=GenerationResponse)
async def create_generation(payload: GenerationPayload):
    job_id = generation_service.create_job(payload)

    # Resolve uploaded file refs to real file paths
    video_path = None
    image_path = None
    reference_audio_path = None
    if payload.videoRef:
        video_path = storage_service.get_filepath(payload.videoRef)
    if payload.imageRef:
        image_path = storage_service.get_filepath(payload.imageRef)
    if payload.referenceAudioRef:
        reference_audio_path = storage_service.get_filepath(payload.referenceAudioRef)

    # Determine LLM to use (map frontend languageModel to config key)
    llm_name = "kimi"

    # Launch the pipeline in background
    generation_service.run_pipeline(
        job_id=job_id,
        prompt=payload.prompt or None,
        video_path=video_path,
        image_path=image_path,
        reference_audio_path=reference_audio_path,
        reference_audio_transcript=payload.referenceAudioTranscript,
        speech_target_text=payload.speechTargetText,
        llm_name=llm_name,
        output_class=payload.outputClass,
        target_duration=payload.duration,
    )

    return generation_service.get_job(job_id)


@router.get("", response_model=List[Artifact])
async def get_generations():
    return generation_service.get_all_completed_artifacts()


@router.get("/{id}", response_model=GenerationResponse)
async def get_generation_by_id(id: str):
    job = generation_service.get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    return job


@router.get("/{id}/status", response_model=GenerationResponse)
async def get_generation_status(id: str):
    job = generation_service.get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    return job


@router.post("/{id}/export", response_model=ExportResponse)
async def export_generation(
    id: str,
    request: Request,
    format: str = Query("WAV"),
    sample_rate: str = Query("48 kHz"),
    bit_depth: str = Query("24 bit"),
    channels: str = Query("Stereo"),
):
    job = generation_service.get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    if job.status != GenerationStatus.COMPLETED or not job.artifact:
        raise HTTPException(status_code=409, detail="Generation is not ready for export")

    # Check if we have a real audio file
    audio_path = generation_service.get_audio_path(id)
    def _make_export_url() -> str:
        url = str(
            request.url_for("download_export", id=id).include_query_params(
                format=format,
                sample_rate=sample_rate,
                bit_depth=bit_depth,
                channels=channels,
            )
        )
        # Only upgrade to https when we're sure the request itself arrived over https,
        # or when a trusted reverse-proxy header says so.  A naive str.replace() would
        # corrupt legitimate http:// URLs in local/dev setups and break behind proxies
        # that forward plain http internally.
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        scheme = forwarded_proto or request.url.scheme
        if scheme == "https" and url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        return url

    if audio_path and os.path.exists(audio_path):
        return ExportResponse(url=_make_export_url())

    # Fallback to mock export URL
    return ExportResponse(url=_make_export_url())


@router.get("/{id}/preview", name="preview_media")
async def preview_media(id: str):
    """Serve the generated media for in-browser playback (no Content-Disposition: attachment)."""
    job = generation_service.get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    if job.status != GenerationStatus.COMPLETED or not job.artifact:
        raise HTTPException(status_code=409, detail="Generation is not ready for preview")

    video_output = generation_service.get_video_output_path(id)
    if video_output and os.path.exists(video_output):
        return FileResponse(path=video_output, media_type="video/mp4")

    audio_path = generation_service.get_audio_path(id)
    if audio_path and os.path.exists(audio_path):
        return FileResponse(path=audio_path, media_type="audio/wav")

    raise HTTPException(status_code=404, detail="No media file found for this generation")


@router.get("/{id}/export/download", name="download_export")
async def download_export(
    id: str,
    format: str = Query("WAV"),
    sample_rate: str = Query("48 kHz"),
    bit_depth: str = Query("24 bit"),
    channels: str = Query("Stereo"),
):
    job = generation_service.get_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    if job.status != GenerationStatus.COMPLETED or not job.artifact:
        raise HTTPException(status_code=409, detail="Generation is not ready for export")

    # Serve video (image+audio or video+audio) if available, otherwise audio only
    video_output = generation_service.get_video_output_path(id)
    if video_output and os.path.exists(video_output):
        filename = f"{id}.mp4"
        return FileResponse(
            path=video_output,
            media_type="video/mp4",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    audio_path = generation_service.get_audio_path(id)
    if audio_path and os.path.exists(audio_path):
        filename = f"{id}.wav"
        return FileResponse(
            path=audio_path,
            media_type="audio/wav",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Fallback: mock export
    sample_rate_value = 44100 if sample_rate == "44.1 kHz" else 96000 if sample_rate == "96 kHz" else 48000
    bit_depth_value = 16 if bit_depth == "16 bit" else 32 if bit_depth == "32 bit" else 24
    channel_value = 1 if channels == "Mono" else 6 if channels == "5.1 Surround" else 2

    audio_bytes = generation_service.build_mock_export(
        id,
        sample_rate=sample_rate_value,
        bit_depth=bit_depth_value,
        channels=channel_value,
    )
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{id}-{format.lower()}.wav"'},
    )
