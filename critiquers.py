import json
from typing import Dict, Any, Tuple, List, Optional
from llm import LLM

class PlanningCritic:
    def review(self, plan: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        messages: List[str] = []
        for e in plan.get("events", []):
            if e["end_time"] < e["start_time"]:
                e["end_time"] = e["start_time"]
                messages.append("Fixed negative duration.")
            e["start_time"] = max(0.0, e["start_time"])
        return plan, messages

class DomainCritic:
    def review(self, event: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        msgs: List[str] = []
        if not event.get("model_candidates"):
            msgs.append("No candidates; adding a fallback.")
        ri = event.get("refined_inputs", {})
        for m in event["model_candidates"]:
            if m not in ri:
                ri[m] = {}
        event["refined_inputs"] = ri
        return event, msgs


class AudioEvalCritic:
    def __init__(self):
        pass

    def _parse_response(self, text: str) -> Tuple[Dict[str, float], List[str]]:
        """
        Return: (scores, suggestions)
        """
        default_scores = {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}
        default_sugg: List[str] = []

        if not text:
            return default_scores, default_sugg

        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        raw = m.group(1) if m else text

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                if "scores" in obj and isinstance(obj["scores"], dict):
                    scores = obj["scores"]
                else:
                    scores = {k: float(obj.get(k, 0.0)) for k in ("quality", "alignment", "aesthetics")}
                suggestions = []
                if "suggestions" in obj and isinstance(obj["suggestions"], list):
                    suggestions = [str(s) for s in obj["suggestions"]]
                elif "suggestion" in obj and isinstance(obj["suggestion"], list):
                    suggestions = [str(s) for s in obj["suggestion"]]
                else:
                    for key in ("notes", "advice", "comment"):
                        if key in obj:
                            if isinstance(obj[key], list):
                                suggestions = [str(x) for x in obj[key]]
                            else:
                                suggestions = [str(obj[key])]
                            break

                parsed_scores = {
                    "quality": float(scores.get("quality", 0.0)),
                    "alignment": float(scores.get("alignment", 0.0)),
                    "aesthetics": float(scores.get("aesthetics", 0.0)),
                }
                return parsed_scores, suggestions
        except Exception:
            pass

        nums = {}
        for k in ("quality", "alignment", "aesthetics"):
            import re
            m = re.search(rf"{k}\D*([0-9](?:\.[0-9])?)", text, flags=re.IGNORECASE)
            if m:
                try:
                    nums[k] = float(m.group(1))
                except:
                    nums[k] = 0.0
            else:
                nums[k] = 0.0

        suggestions = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(k in line.lower() for k in ("quality", "alignment", "aesthetics", "score")):
                continue
            suggestions.append(line)
        if not suggestions:
            suggestions = ["No explicit suggestions provided."]

        return {"quality": nums["quality"], "alignment": nums["alignment"], "aesthetics": nums["aesthetics"]}, suggestions

    def evaluate(self, event: Dict[str, Any], wav_path: str, llm: LLM) -> Tuple[Dict[str, float], List[str]]:
        """
        Return (scores, suggestions)
        """
        import os
        if not wav_path or not isinstance(wav_path, str) or wav_path.strip() == "":
            return {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}, ["Error: No audio file path provided"]
        
        if not os.path.exists(wav_path):
            return {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}, [f"Error: Audio file not found: {wav_path}"]
        
        system = "You are an audio critic. Evaluate the following audio on quality, alignment to the described event, and overall aesthetics. Return JSON like: {\"quality\":0.7, \"alignment\":0.6, \"aesthetics\":0.5, \"suggestions\": [\"...\"]}."
        user = json.dumps({"event": event}, ensure_ascii=False)

        try:
            raw = llm.chat(system=system, user=user, media={"audio": wav_path})
            scores, suggestions = self._parse_response(raw)
            return scores, suggestions
        except Exception as e:
            return {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}, [f"Critic error: {e}"]

class LLMPlanningReviewer:
    """
    review the LLM's plan
    """
    def __init__(self, llm):
        self.llm = llm

    @staticmethod
    def _tolist(x):
        if not x:
            return []
        return x if isinstance(x, (list, tuple)) else [x]

    def review(self, draft_plan_json: str, multimodal_context: Optional[Dict[str, Any]] = None) -> str:
        system = (
            "You are an audio planning expert."
            "Review the draft audio event plan against the given multimodal inputs (text/images/video). "
            "Fix content suitability issues, timing alignment, and wrong audio_type classifications. "
        )

        mm = multimodal_context or {}
        media = {
            "texts":  self._tolist(mm.get("text")),   
            "images": self._tolist(mm.get("image")),
            "videos": self._tolist(mm.get("video")),
        }

        user = (
            "Keep only necessary changes\n"
            "If something is missing or overlaps incorrectly, add or correct it.\n"
            "Do not change the volume_db planning.\n"
            "Return ONLY the revised JSON plan.\n\n"
            "[Draft plan JSON]\n"
            f"{draft_plan_json}\n"
        )

        return self.llm.chat(system, user, media=media)
