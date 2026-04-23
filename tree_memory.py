from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

SCORE_WEIGHTS: Dict[str, float] = {
    "alignment": 0.5,
    "quality": 0.35,
    "aesthetics": 0.15,
}


@dataclass
class NodeRecord:
    node_id: str
    model: str
    attempt: int
    node_type: str
    parent_id: Optional[str]
    text_used: str
    args_used: Dict[str, Any]
    scores: Dict[str, float]
    suggestions: List[str]
    timestamp: float = field(default_factory=time.time)

    @property
    def score_sum(self) -> float:
        return sum(self.scores.values())

    @property
    def weighted_score(self) -> float:
        return sum(self.scores.get(k, 0.0) * w for k, w in SCORE_WEIGHTS.items())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "model": self.model,
            "attempt": self.attempt,
            "node_type": self.node_type,
            "parent_id": self.parent_id,
            "text_used": self.text_used,
            "scores": self.scores,
            "weighted_score": round(self.weighted_score, 4),
            "suggestions": self.suggestions,
        }


class TreeMemory:
    def __init__(self):
        self._records: Dict[str, NodeRecord] = {}

    def record(
        self,
        node_id: str,
        model: str,
        attempt: int,
        node_type: str,
        parent_id: Optional[str],
        args_used: Dict[str, Any],
        scores: Dict[str, float],
        suggestions: List[str],
    ) -> None:
        text_used = (
            args_used.get("text")
            or args_used.get("prompt")
            or args_used.get("ref_prompt")
            or args_used.get("tts_text")
            or ""
        )
        self._records[node_id] = NodeRecord(
            node_id=node_id,
            model=model,
            attempt=attempt,
            node_type=node_type,
            parent_id=parent_id,
            text_used=str(text_used),
            args_used=args_used,
            scores=scores,
            suggestions=suggestions,
        )

    def get_path_history(self, node_id: str) -> List[NodeRecord]:
        path: List[NodeRecord] = []
        curr_id: Optional[str] = node_id
        while curr_id and curr_id in self._records:
            rec = self._records[curr_id]
            path.append(rec)
            curr_id = rec.parent_id
        path.reverse()
        return path

    def get_model_history(self, model: str) -> List[NodeRecord]:
        recs = [r for r in self._records.values() if r.model == model]
        return sorted(recs, key=lambda r: (r.attempt, r.timestamp))

    def get_all_suggestions(self, deduplicate: bool = True) -> List[str]:
        seen: set = set()
        result: List[str] = []
        for rec in self._records.values():
            for s in rec.suggestions:
                key = s.strip().lower()
                if not deduplicate or key not in seen:
                    seen.add(key)
                    result.append(s)
        return result

    def get_best_record(self) -> Optional[NodeRecord]:
        if not self._records:
            return None
        return max(self._records.values(), key=lambda r: r.weighted_score)

    def to_refinement_context(self, current_node_id: str) -> Dict[str, Any]:
        path = self.get_path_history(current_node_id)
        best = self.get_best_record()
        return {
            "path_history": [r.to_dict() for r in path],
            "global_best": best.to_dict() if best else None,
            "all_suggestions": self.get_all_suggestions(deduplicate=True),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {nid: rec.to_dict() for nid, rec in self._records.items()}

    def __len__(self) -> int:
        return len(self._records)
