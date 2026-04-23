"""
Generation service that runs the DubMaster multi-agent pipeline
in background threads and exposes status via SQLite.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import uuid
import random
import wave
import threading
import traceback
from pathlib import Path
from typing import List, Optional

from ..schemas import (
    GenerationStatus,
    GenerationStage,
    Artifact,
    GenerationPayload,
    GenerationResponse,
)
from .database import get_connection

# ── Add project root to sys.path so we can import the multi-agent framework ──
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


_OUTPUT_CLASS_ALLOWLIST = {
    "sound effects":     {"sound effect", "sound_effect", "sfx"},
    "speech":            {"speech", "tts", "voice"},
    "background music":  {"music"},
    "song":              {"song", "singing", "vocal"},
}


def _enforce_user_constraints(
    plan,
    output_class: Optional[str],
    target_duration: Optional[float],
    prompt: Optional[str],
) -> None:
    """Filter plan events to match user's output class and clamp to target duration.

    The planning LLM receives these as soft hints, but it routinely ignores them.
    This is the hard safety net: drop off-category events, clamp any event that
    extends past the target, and synthesize a fallback event if filtering empties
    the plan.
    """
    allow: Optional[set] = None
    if output_class:
        # Support comma-separated multi-select: "Sound Effects,Music" → union of allowlists
        parts = [p.strip().lower() for p in output_class.split(",") if p.strip()]
        combined: set = set()
        for p in parts:
            subset = _OUTPUT_CLASS_ALLOWLIST.get(p)
            if subset:
                combined |= subset
        if combined:
            allow = combined

    target = float(target_duration) if target_duration else None

    kept = []
    for ev in plan.events:
        etype = (ev.audio_type or "").strip().lower()
        if allow is not None and etype not in allow:
            continue
        if target is not None:
            if ev.start_time >= target:
                continue
            if ev.end_time > target:
                ev.end_time = target
        kept.append(ev)

    if not kept:
        # Fallback: single event of the preferred type covering the full target.
        from plan import AudioEvent

        _canonical = {
            "sound effects":     "sound_effect",
            "speech":            "speech",
            "background music":  "music",
            "song":              "song",
        }
        first_class = parts[0] if parts else "sound_effect"
        preferred = _canonical.get(first_class, "sound_effect")
        desc = (prompt or "").strip() or f"{output_class or 'audio'} track"
        kept = [
            AudioEvent(
                audio_type=preferred,
                object=output_class or "Audio",
                start_time=0.0,
                end_time=float(target or 6.0),
                description=desc,
                volume_db=-6.0,
            )
        ]

    plan.events = kept


def _clean_reference_transcript(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""

    fenced = re.search(r"```(?:text|json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for key in ("transcript", "text", "content"):
                if isinstance(obj.get(key), str):
                    text = obj[key].strip()
                    break
    except Exception:
        pass

    for prefix in (
        "transcript:",
        "transcription:",
        "reference transcript:",
        "the transcript is:",
        "参考音频内容：",
        "转录：",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()

    text = text.strip().strip('"').strip("'").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)[:500]


def _auto_transcribe_reference_audio(reference_audio_path: Optional[str], audio_llm) -> str:
    """Best-effort helper so users do not need to type the reference transcript."""
    if not reference_audio_path or not os.path.exists(reference_audio_path) or audio_llm is None:
        return ""

    system = (
        "You are an exact speech transcriber. "
        "Listen to the reference audio and return only the spoken words. "
        "Do not explain, translate, summarize, or add labels."
    )
    user = "Transcribe the attached reference audio verbatim. Return plain text only."

    try:
        raw = audio_llm.chat(system=system, user=user, media={"audio": reference_audio_path})
    except Exception as exc:
        print(f"[WARN] Failed to auto-transcribe reference audio: {exc}")
        return ""

    return _clean_reference_transcript(raw)


class GenerationService:
    """Generation service backed by SQLite + real DubMaster pipeline."""

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _heights_to_str(heights: List[int]) -> str:
        return ",".join(str(h) for h in heights)

    @staticmethod
    def _str_to_heights(raw: Optional[str]) -> List[int]:
        if not raw:
            return []
        return [int(x) for x in raw.split(",") if x]

    @staticmethod
    def _row_to_response(row) -> GenerationResponse:
        artifact = None
        if row["art_title"] is not None:
            artifact = Artifact(
                id=row["id"],
                title=row["art_title"],
                type=row["art_type"],
                duration=row["art_duration"],
                heights=GenerationService._str_to_heights(row["art_heights"]),
            )
        return GenerationResponse(
            id=row["id"],
            status=GenerationStatus(row["status"]),
            artifact=artifact,
            stage=row["stage"] if "stage" in row.keys() else None,
            stageDetail=row["stage_detail"] if "stage_detail" in row.keys() else None,
        )

    # ── DB update helpers ─────────────────────────────────────────

    def _update_stage(self, job_id: str, stage: str, detail: str = "") -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE generations SET stage = ?, stage_detail = ? WHERE id = ?",
                (stage, detail, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_status(self, job_id: str, status: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE generations SET status = ? WHERE id = ?",
                (status, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_completed(
        self,
        job_id: str,
        title: str,
        art_type: str,
        duration: str,
        heights: List[int],
        audio_path: str = "",
        video_path: str = "",
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE generations
                   SET status = ?, stage = ?, stage_detail = ?,
                       art_title = ?, art_type = ?, art_duration = ?,
                       art_heights = ?, audio_path = ?, video_path = ?
                   WHERE id = ?""",
                (
                    GenerationStatus.COMPLETED.value,
                    GenerationStage.DONE.value,
                    "Generation complete",
                    title,
                    art_type,
                    duration,
                    self._heights_to_str(heights),
                    audio_path,
                    video_path,
                    job_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_failed(self, job_id: str, error: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE generations SET status = ?, stage_detail = ?, error_message = ? WHERE id = ?",
                (GenerationStatus.FAILED.value, f"Error: {error[:200]}", error, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── public API ────────────────────────────────────────────────

    def create_job(self, payload: GenerationPayload) -> str:
        job_id = f"gen_{uuid.uuid4().hex[:8]}"
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO generations (id, status, stage, prompt) VALUES (?, ?, ?, ?)",
                (job_id, GenerationStatus.PENDING.value, GenerationStage.UPLOADING.value, payload.prompt),
            )
            conn.commit()
        finally:
            conn.close()
        return job_id

    def get_job(self, job_id: str) -> Optional[GenerationResponse]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM generations WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return self._row_to_response(row)

    def get_all_completed_artifacts(self) -> List[Artifact]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM generations WHERE status = ? AND art_title IS NOT NULL ORDER BY created_at DESC",
                (GenerationStatus.COMPLETED.value,),
            ).fetchall()
        finally:
            conn.close()
        artifacts = []
        for row in rows:
            artifacts.append(
                Artifact(
                    id=row["id"],
                    title=row["art_title"],
                    type=row["art_type"],
                    duration=row["art_duration"],
                    heights=self._str_to_heights(row["art_heights"]),
                )
            )
        return artifacts

    def get_audio_path(self, job_id: str) -> Optional[str]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT audio_path FROM generations WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        if row and row["audio_path"]:
            return row["audio_path"]
        return None

    def get_video_output_path(self, job_id: str) -> Optional[str]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT video_path FROM generations WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        if row and row["video_path"]:
            return row["video_path"]
        return None

    # ── pipeline execution (runs in background thread) ────────────

    def run_pipeline(
        self,
        job_id: str,
        prompt: Optional[str],
        video_path: Optional[str],
        image_path: Optional[str],
        reference_audio_path: Optional[str] = None,
        reference_audio_transcript: Optional[str] = None,
        speech_target_text: Optional[str] = None,
        llm_name: str = "kimi",
        max_depth: int = 3,
        max_siblings: int = 1,
        output_class: Optional[str] = None,
        target_duration: Optional[float] = None,
    ) -> None:
        """Launch the multi-agent pipeline in a daemon thread."""
        thread = threading.Thread(
            target=self._pipeline_worker,
            args=(
                job_id, prompt, video_path, image_path, llm_name,
                max_depth, max_siblings, output_class, target_duration,
                reference_audio_path, reference_audio_transcript,
                speech_target_text,
            ),
            daemon=True,
        )
        thread.start()

    def _pipeline_worker(
        self,
        job_id: str,
        prompt: Optional[str],
        video_path: Optional[str],
        image_path: Optional[str],
        llm_name: str,
        max_depth: int,
        max_siblings: int,
        output_class: Optional[str] = None,
        target_duration: Optional[float] = None,
        reference_audio_path: Optional[str] = None,
        reference_audio_transcript: Optional[str] = None,
        speech_target_text: Optional[str] = None,
    ) -> None:
        try:
            self._update_status(job_id, GenerationStatus.PROCESSING.value)

            # Import the multi-agent framework (lazy import to avoid startup cost)
            from router import load_llm
            from agents import DubMasterSystem

            # Prepare output directory — use OUTPUT_DIR env var if set
            # (production: Fly.io Volume at /data/outputs), else project root /outputs/
            _output_base = os.environ.get("OUTPUT_DIR", os.path.join(_PROJECT_ROOT, "outputs"))
            outdir = os.path.join(_output_base, job_id)
            os.makedirs(outdir, exist_ok=True)

            # Save output dir to DB
            conn = get_connection()
            try:
                conn.execute("UPDATE generations SET output_dir = ? WHERE id = ?", (outdir, job_id))
                conn.commit()
            finally:
                conn.close()

            # Stage 1: Planning
            self._update_stage(job_id, GenerationStage.PLANNING.value, "Analyzing inputs and creating audio event plan...")

            llm = load_llm(llm_name)
            try:
                critic_llm = load_llm("qwen-omni-critic")
            except Exception as _critic_err:
                print(f"[WARN] Failed to load qwen-omni-critic, audio scoring disabled: {_critic_err}")
                critic_llm = None
            system = DubMasterSystem(llm, outdir=outdir, critic_llm=critic_llm)

            reference_audio_transcript = (reference_audio_transcript or "").strip()
            if reference_audio_path and not reference_audio_transcript:
                self._update_stage(
                    job_id,
                    GenerationStage.PLANNING.value,
                    "Preparing reference voice automatically...",
                )
                reference_audio_transcript = _auto_transcribe_reference_audio(
                    reference_audio_path,
                    critic_llm,
                )

            ctx = {
                "text": prompt,
                "image": image_path,
                "video": video_path if video_path not in (None, "None", "none", "") else None,
                "output_class": output_class,
                "target_duration": target_duration,
                "reference_audio": reference_audio_path,
                "reference_audio_transcript": reference_audio_transcript or "",
                "prompt_wav_path": reference_audio_path,
                "prompt_transcript": reference_audio_transcript or "",
                "speech_target_text": speech_target_text or "",
            }

            # Run stage 1: plan
            plan = system.generation.plan(ctx)

            # Hard filter/clamp: enforce user's output class + target duration even
            # if the LLM ignored the soft hints in the planning prompt.
            _enforce_user_constraints(plan, output_class, target_duration, prompt)

            with open(os.path.join(outdir, "stage1_output.json"), "w", encoding="utf-8") as f:
                f.write(plan.to_json())

            num_events = len(plan.events)
            self._update_stage(
                job_id,
                GenerationStage.ASSIGNING.value,
                f"Routing {num_events} audio events to domain experts...",
            )

            # Run stage 2: assign & refine
            plan = system.generation.assign_and_refine(
                plan,
                system.supervisor.get_domain_critic(),
                plan_ctx=ctx,
                outdir=outdir,
            )
            with open(os.path.join(outdir, "stage2_output.json"), "w", encoding="utf-8") as f:
                f.write(plan.to_json())

            self._update_stage(
                job_id,
                GenerationStage.SYNTHESIZING.value,
                f"Generating audio for {num_events} events with Tree-of-Thought refinement...",
            )

            # Run stage 3: synthesize with ToT
            results = system.generation.synthesize_with_tot(
                plan,
                outdir=outdir,
                eval_critic=system.eval_critic,
                max_depth=max_depth,
                max_siblings=max_siblings,
                critic_llm=critic_llm,
            )

            # Mixing
            self._update_stage(job_id, GenerationStage.MIXING.value, "Compositing audio tracks and applying spatial mix...")

            audio_segments = []
            res_events = results.get("events", [])
            seen_wavs = set()

            for i, e in enumerate(plan.events):
                wav = (res_events[i].get("wav") if i < len(res_events) else None) or ""
                if wav and os.path.exists(wav) and (wav not in seen_wavs):
                    seen_wavs.add(wav)
                    audio_segments.append({
                        "audio_type": e.audio_type,
                        "Object": e.object or "",
                        "start_time": e.start_time,
                        "end_time": e.end_time,
                        "duration": e.end_time - e.start_time,
                        "description": e.description,
                        "volume": getattr(e, "volume_db", 0.0),
                        "wav_file": wav,
                    })

            # Check for kept SFX segments
            keep_file = os.path.join(outdir, "stage2_sfx_probe_keep.json")
            if os.path.exists(keep_file):
                try:
                    with open(keep_file, "r", encoding="utf-8") as _kf:
                        keep_list = json.load(_kf)
                    if isinstance(keep_list, list):
                        for seg in keep_list:
                            w = seg.get("wav_file")
                            if w and os.path.exists(w) and w not in seen_wavs:
                                seen_wavs.add(w)
                                audio_segments.append(seg)
                except Exception:
                    pass

            final_audio = ""
            final_video = ""
            total_duration_sec = 0.0

            if audio_segments:
                from mixer import mix_and_maybe_mux

                final_wav = os.path.join(outdir, "final_mixed_audio.wav")
                final_mp4 = os.path.join(outdir, "final_video_with_audio.mp4")
                try:
                    mixed = mix_and_maybe_mux(
                        video_path=ctx.get("video"),
                        image_path=ctx.get("image"),
                        audio_segments=audio_segments,
                        output_audio_path=final_wav,
                        output_video_path=final_mp4,
                    )
                    final_audio = mixed.get("audio", "")
                    final_video = mixed.get("video", "")
                except Exception as e:
                    print(f"Mixing error: {e}")
                    # If mixing fails but we have individual wavs, use the first one
                    if audio_segments:
                        final_audio = audio_segments[0].get("wav_file", "")

                # Calculate total duration from segments
                for seg in audio_segments:
                    end = float(seg.get("end_time", 0))
                    if end > total_duration_sec:
                        total_duration_sec = end

            # Save stage 3 outputs
            with open(os.path.join(outdir, "stage3_mix_segments.json"), "w", encoding="utf-8") as f:
                json.dump(audio_segments, f, ensure_ascii=False, indent=2)
            with open(os.path.join(outdir, "stage3_output.json"), "w", encoding="utf-8") as f:
                json.dump({"results": results, "mixed": {"audio": final_audio, "video": final_video}}, f, ensure_ascii=False, indent=2, default=str)

            # If the pipeline produced no usable audio, collect node errors and fail the job
            # so the frontend shows the actual cause instead of a 00:00.0s "success".
            if not final_audio or not os.path.exists(final_audio):
                node_errors: List[str] = []
                for ev in res_events:
                    nodes = ev.get("nodes") or {}
                    for nid, node in nodes.items():
                        if not isinstance(node, dict):
                            continue
                        meta = node.get("meta") or {}
                        err = meta.get("error")
                        if err and err not in node_errors:
                            etype = meta.get("error_type") or "Error"
                            node_errors.append(f"{etype}: {err}")
                if node_errors:
                    summary = node_errors[0]
                    if len(node_errors) > 1:
                        summary += f" (and {len(node_errors) - 1} more)"
                    raise RuntimeError(f"Synthesis failed: {summary}")
                raise RuntimeError("Synthesis produced no audio (no tool errors captured)")

            # Generate waveform heights for frontend visualization
            heights = [random.randint(2, 24) for _ in range(20)]

            # Determine art_type from events
            event_types = set()
            for e in plan.events:
                event_types.add(e.audio_type)
            art_type = " + ".join(sorted(event_types)) if event_types else "Audio"

            # Format duration
            mins = int(total_duration_sec // 60)
            secs = total_duration_sec % 60
            duration_str = f"{mins:02d}:{secs:04.1f}s"

            self._mark_completed(
                job_id,
                title=f"DubMaster_{job_id[-4:]}",
                art_type=art_type,
                duration=duration_str,
                heights=heights,
                audio_path=final_audio,
                video_path=final_video,
            )

        except Exception as e:
            traceback.print_exc()
            self._mark_failed(job_id, str(e))

    # ── legacy mock export (fallback) ─────────────────────────────

    def build_mock_export(
        self,
        job_id: str,
        sample_rate: int = 22050,
        bit_depth: int = 16,
        channels: int = 1,
    ) -> bytes:
        job = self.get_job(job_id)
        if not job or job.status != GenerationStatus.COMPLETED or not job.artifact:
            raise ValueError("Generation is not ready for export")

        duration_seconds = 1.2
        total_frames = int(sample_rate * duration_seconds)
        tone_seed = sum(ord(char) for char in job_id[-4:])
        frequency = 220 + (tone_seed % 220)
        amplitude = 16000

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            sample_width = max(2, bit_depth // 8)
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)

            frames = bytearray()
            for index in range(total_frames):
                sample = int(amplitude * math.sin((2 * math.pi * frequency * index) / sample_rate))
                sample_bytes = sample.to_bytes(sample_width, byteorder="little", signed=True)
                for _ in range(channels):
                    frames.extend(sample_bytes)

            wav_file.writeframes(bytes(frames))

        return buffer.getvalue()


generation_service = GenerationService()
