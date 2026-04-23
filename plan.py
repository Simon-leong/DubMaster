from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json

AUDIO_TYPES = ("speech", "sound_effect", "music", "song")

def _norm_audio_type(x: str) -> str:
    t = (x or "").strip().lower().replace("_", " ")
    if "sound" in t and "effect" in t:
        return "sound_effect"
    if "speech" in t:
        return "speech"
    if "song" in t:
        return "song"
    if "music" in t:
        return "music"
    return "sound_effect"

def _to_float(v) -> float:
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0

@dataclass
class AudioEvent:
    audio_type: str
    start_time: float
    end_time: float
    description: str
    volume_db: float = -6.0
    object: Optional[str] = None
    model_candidates: list[str] = field(default_factory=list)
    refined_inputs: Dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def validate(self) -> None:
        if self.audio_type not in AUDIO_TYPES:
            raise ValueError(f"Invalid audio_type: {self.audio_type}")
        if self.start_time < 0 or self.end_time < 0:
            raise ValueError("start_time/end_time must be non-negative")
        if self.end_time < self.start_time:
            raise ValueError("end_time must be >= start_time")

@dataclass
class Plan:
    events: List[AudioEvent] = field(default_factory=list)
    visual_caption: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "visual_caption": self.visual_caption,
                "events": [asdict(e) for e in self.events],
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def from_json(s: str) -> "Plan":
        obj = json.loads(s)
        if isinstance(obj, list):
            raw_list = obj
        else:
            raw_list = obj.get("audio_seg") or obj.get("events") or []
        events: List[AudioEvent] = []
        for item in raw_list:
            audio_type = _norm_audio_type(item.get("audio_type", ""))
            object_name = item.get("Object") or item.get("object")
            start_time = _to_float(item.get("start_time", 0))
            end_time = _to_float(item.get("end_time", 0))
            desc = item.get("description") or ""
            vol = item.get("volume")
            vol_db = _to_float(vol) if vol is not None else -6.0
            e = AudioEvent(
                audio_type=audio_type,
                start_time=start_time,
                end_time=end_time,
                description=desc,
                volume_db=vol_db,
                object=object_name,
            )
            try:
                e.validate()
            except Exception:
                e.start_time = max(0.0, start_time)
                e.end_time = max(e.start_time, end_time)
            events.append(e)
        return Plan(events=events, visual_caption=obj.get("visual_caption"))
