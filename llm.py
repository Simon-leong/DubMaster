import os, json, mimetypes
from typing import Optional, List, Dict, Any
from pathlib import Path
import requests, base64

from utils.media_uploader import UploadedMedia, build_media_uploader

_MAX_INLINE_BYTES = int(os.environ.get("GEMINI_INLINE_LIMIT", str(15 * 1024 * 1024)))


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return bool(value)


def _normalize_media_upload_types(value: Any) -> set[str]:
    aliases = {
        "video": "videos",
        "videos": "videos",
        "image": "images",
        "images": "images",
        "audio": "audios",
        "audios": "audios",
    }

    if value is None:
        raw_items = ["videos"]
    elif isinstance(value, str):
        raw_items = [x.strip() for x in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(x).strip() for x in value]
    else:
        raw_items = [str(value).strip()]

    media_types: set[str] = set()
    for item in raw_items:
        key = aliases.get(str(item).lower())
        if key:
            media_types.add(key)
    return media_types or {"videos"}

def _mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"

def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

class LLM:
    def __init__(self, **common_config):
        # Shared basic settings for all providers in this project.
        self.hf_token = str(common_config.get("hf_token") or os.environ.get("HF_TOKEN") or "").strip()

        media_cfg = dict(common_config.get("media_upload") or {})
        media_upload_method_override = common_config.get("media_upload_method", None)
        media_upload_enabled_override = common_config.get("media_upload_enabled", None)
        media_upload_types_override = common_config.get("media_upload_types", None)

        media_upload_method_value = (
            media_upload_method_override
            if media_upload_method_override is not None
            else media_cfg.get("method")
        )
        media_upload_enabled_value = (
            media_upload_enabled_override
            if media_upload_enabled_override is not None
            else media_cfg.get("enabled", False)
        )
        media_upload_types_value = (
            media_upload_types_override
            if media_upload_types_override is not None
            else media_cfg.get("types", ["videos"])
        )

        self.media_upload_method = str(media_upload_method_value or "").strip().lower()
        self.media_upload_enabled = _as_bool(media_upload_enabled_value, default=False)
        self.media_upload_types = _normalize_media_upload_types(media_upload_types_value)
        self.media_upload_cleanup = _as_bool(
            media_cfg.get("cleanup", common_config.get("hf_cache_cleanup", False)),
            default=False,
        )

        hf_cfg = dict(media_cfg.get("huggingface") or {})
        self.hf_cache_repo_id = str(
            hf_cfg.get("repo_id") or common_config.get("hf_cache_repo_id") or os.environ.get("HF_CACHE_REPO_ID") or ""
        ).strip()
        self.hf_cache_repo_type = str(
            hf_cfg.get("repo_type")
            or common_config.get("hf_cache_repo_type")
            or os.environ.get("HF_CACHE_REPO_TYPE")
            or "dataset"
        ).strip() or "dataset"
        self.hf_cache_token = str(
            hf_cfg.get("token") or common_config.get("hf_cache_token") or self.hf_token or os.environ.get("HF_TOKEN") or ""
        ).strip()
        self.hf_cache_prefix = str(
            hf_cfg.get("prefix") or common_config.get("hf_cache_prefix") or os.environ.get("HF_CACHE_PREFIX") or "videos"
        ).strip("/")
        self.hf_cache_public_base_url = str(
            hf_cfg.get("public_base_url")
            or common_config.get("hf_cache_public_base_url")
            or os.environ.get("HF_CACHE_PUBLIC_BASE_URL")
            or "https://huggingface.co"
        ).strip()

        dash_cfg = dict(media_cfg.get("dashscope") or {})
        self.dashscope_api_key = str(
            dash_cfg.get("api_key")
            or common_config.get("dashscope_api_key")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        ).strip()
        self.dashscope_base_url = str(
            dash_cfg.get("base_url")
            or common_config.get("dashscope_base_url")
            or "https://dashscope.aliyuncs.com/api/v1"
        ).strip().rstrip("/")
        self.dashscope_purpose = str(
            dash_cfg.get("purpose")
            or common_config.get("dashscope_purpose")
            or "file-extract"
        ).strip() or "file-extract"
        self.dashscope_description = str(
            dash_cfg.get("description") or common_config.get("dashscope_description") or ""
        ).strip()

        # Backward compatibility: if legacy HF cache fields are configured, auto-enable HF uploader.
        if not self.media_upload_method and self.hf_cache_repo_id:
            self.media_upload_method = "huggingface"

        self._media_uploader = None

    def chat(self, system: str, user: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        raise NotImplementedError

    def _media_upload_enabled(self) -> bool:
        if not self.media_upload_enabled:
            return False
        return self.media_upload_method not in ("", "none", "disabled", "off")

    def _media_type_upload_enabled(self, media_kind: str) -> bool:
        aliases = {
            "video": "videos",
            "videos": "videos",
            "image": "images",
            "images": "images",
            "audio": "audios",
            "audios": "audios",
        }
        kind = aliases.get(str(media_kind or "").strip().lower(), "")
        if not kind:
            return False
        return kind in self.media_upload_types

    def _hf_enabled(self) -> bool:
        return self.media_upload_method in ("hf", "huggingface") and bool(self.hf_cache_repo_id)

    def _build_media_uploader(self):
        dashscope_api_key = self.dashscope_api_key or str(getattr(self, "api_key", "") or "").strip()
        return build_media_uploader(
            method=self.media_upload_method,
            cleanup=self.media_upload_cleanup,
            hf_repo_id=self.hf_cache_repo_id,
            hf_repo_type=self.hf_cache_repo_type,
            hf_token=self.hf_cache_token,
            hf_prefix=self.hf_cache_prefix,
            hf_public_base_url=self.hf_cache_public_base_url,
            dashscope_api_key=dashscope_api_key,
            dashscope_base_url=self.dashscope_base_url,
            dashscope_purpose=self.dashscope_purpose,
            dashscope_description=self.dashscope_description,
        )

    def _get_media_uploader(self):
        if not self._media_upload_enabled():
            return None
        if self._media_uploader is None:
            self._media_uploader = self._build_media_uploader()
        return self._media_uploader

    def _upload_local_media_file(
        self,
        local_path: str,
        uploaded_media: Optional[List[UploadedMedia]] = None,
        media_kind: str = "videos",
    ) -> Optional[str]:
        if not self._media_upload_enabled() or not self._media_type_upload_enabled(media_kind):
            return None
        uploader = self._get_media_uploader()
        if uploader is None:
            return None
        result = uploader.upload_file(local_path)
        if uploaded_media is not None:
            uploaded_media.append(result)
        return result.url

    def _cleanup_uploaded_media(self, uploaded_media: List[UploadedMedia]) -> None:
        if not uploaded_media:
            return
        uploader = self._get_media_uploader()
        if uploader is None:
            return
        uploader.cleanup(uploaded_media)

class GeminiLLM(LLM):
    def __init__(self, model: str = "gemini-2.5-flash", api_key: Optional[str] = None, **parameters):
        super().__init__(**parameters)
        self.model = model
        self._client = None
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set.")
        self._init_client()

    def _init_client(self):
        try:
            from google import genai
            from google.genai import types
        except Exception as e:
            raise RuntimeError("google-genai not installed. pip install google-genai") from e
        from google import genai
        self._genai = genai
        self._types = __import__("google.genai", fromlist=["types"]).types
        self._client = genai.Client(api_key=self.api_key)


    def _tolist(self, x):
        if not x:
            return []
        return x if isinstance(x, (list, tuple)) else [x]

    def _parts_for_media(self, images, videos, texts):
        parts = []

        # image
        for img in self._tolist(images):
            p = str(img)
            mt = _mime(p)
            try:
                size = Path(p).stat().st_size
            except Exception:
                size = 0
            if size and size <= _MAX_INLINE_BYTES:
                parts.append(self._types.Part(
                    inline_data=self._types.Blob(data=_read_bytes(p), mime_type=mt or "image/jpeg")
                ))
            else:
                try:
                    uploaded = self._client.files.upload(file=p) 
                    parts.append(self._types.Part(
                        file_data=self._types.FileData(file_uri=getattr(uploaded, "uri", None) or getattr(uploaded, "path", None), mime_type=mt or "image/jpeg")
                    ))
                except Exception:
                    parts.append(self._types.Part(
                        inline_data=self._types.Blob(data=_read_bytes(p), mime_type=mt or "image/jpeg")
                    ))

        # video
        for vid in self._tolist(videos):
            p = str(vid)
            mt = _mime(p) or "video/mp4"
            try:
                size = Path(p).stat().st_size
            except Exception:
                size = 0

            if size and size <= _MAX_INLINE_BYTES:
                parts.append(self._types.Part(
                    inline_data=self._types.Blob(data=_read_bytes(p), mime_type=mt)
                ))
            else:
                # files API
                try:
                    uploaded = self._client.files.upload(file=p)
                    # file_uri, file.name
                    file_uri = getattr(uploaded, "uri", None) or getattr(uploaded, "path", None) or getattr(uploaded, "name", None)
                    parts.append(self._types.Part(
                        file_data=self._types.FileData(file_uri=file_uri, mime_type=mt)
                    ))
                except Exception as e:
                    raise RuntimeError(f"[GeminiLLM] The video is too large and the file upload failed: {p}; please verify network connectivity and Files API permissions. Original error: {e}")
                                            
        # text
        for text in self._tolist(texts):
            if isinstance(text, str):
                parts.append(self._types.Part(
                    inline_data=self._types.Blob(data=text.encode("utf-8"), mime_type="text/plain")
                ))
            else:
                raise TypeError("The text must be a string.")

        return parts

    def _read_bytes(self, path: str) -> bytes:
        """audio file"""
        with open(path, "rb") as f:
            return f.read()

    def chat(self, system: str, user: str, stop=None, media: Optional[Dict[str, Any]] = None) -> str:
        if self._client is None:
            self._init_client()

        media = media or {}
        images = media.get("images")
        videos = media.get("videos")
        texts = media.get("texts")
        audio = media.get("audio")

        parts = []
        if images or videos or texts:
            parts.extend(self._parts_for_media(images, videos, texts))
        
        if audio:
            data = self._read_bytes(audio) if isinstance(audio, str) else audio
            audio_part = self._types.Part(
                inline_data=self._types.Blob(data=data, mime_type="audio/wav")
            )
            parts.append(audio_part)


        parts.append(self._types.Part(text=f"[SYSTEM]\n{system}"))
        parts.append(self._types.Part(text=f"[USER]\n{user}"))

        content = self._types.Content(parts=parts)
        resp = self._client.models.generate_content(model=self.model, contents=content)
        text = getattr(resp, "text", None) or getattr(resp, "output_text", None)
        return text or ""


class OpenaiLLM(LLM):
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None, base_url: Optional[str] = None, stream: bool = False, **parameters):
        super().__init__(**parameters)
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.stream = _as_bool(stream, default=False)

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError("openai not installed. pip install openai") from e
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system: str, user: str, stop=None, media: Optional[Dict[str, Any]] = None) -> str:
        if self._client is None:
            self._init_client()

        media = media or {}
        content = []
        uploaded_media: List[UploadedMedia] = []
        
        content.append({"type": "text", "text": user})

        for text in self._to_list(media.get("texts")):
            content.append({"type": "text", "text": str(text)})

        for img in self._to_list(media.get("images")):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._to_data_url(
                            img,
                            fallback_mime="image/jpeg",
                            uploaded_media=uploaded_media,
                            media_kind="images",
                        )
                    },
                }
            )

        for vid in self._to_list(media.get("videos")):
            content.append(
                {
                    "type": "video_url",
                    "video_url": {
                        "url": self._to_data_url(
                            vid,
                            fallback_mime="video/mp4",
                            uploaded_media=uploaded_media,
                            media_kind="videos",
                        )
                    },
                }
            )

        for aud in self._to_list(media.get("audio")):
            content.append({"type": "input_audio", "input_audio": self._to_input_audio(aud, uploaded_media=uploaded_media)})

        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]

        try:
            if self.stream:
                return self._send_streaming(messages, stop)
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                stop=stop,
                max_tokens=8192,
            )
            msg = resp.choices[0].message
            text = getattr(msg, "content", None) or ""
            if not text:
                # Some reasoning models (e.g. Kimi K2.5) put the answer in reasoning_content
                text = getattr(msg, "reasoning_content", None) or ""
            return text
        finally:
            self._cleanup_uploaded_media(uploaded_media)

    def _send_streaming(self, messages: list, stop=None) -> str:
        """Handle streaming responses (required by e.g. Qwen-Omni)."""
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            stop=stop,
            max_tokens=8192,
            stream=True,
            stream_options={"include_usage": True},
            modalities=["text"],
        )
        chunks: list[str] = []
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    chunks.append(delta.content)
        return "".join(chunks)

    def _to_list(self, x):
        if not x:
            return []
        return x if isinstance(x, (list, tuple)) else [x]

    def _to_data_url(
        self,
        item: Any,
        fallback_mime: str,
        uploaded_media: Optional[List[UploadedMedia]] = None,
        media_kind: str = "videos",
    ) -> str:
        # Support {"base64": "...", "mime_type": "..."} / {"path": "..."} / {"url": "..."}
        if isinstance(item, dict):
            if item.get("url"):
                return str(item["url"])
            if item.get("base64"):
                mt = str(item.get("mime_type") or fallback_mime)
                return f"data:{mt};base64,{item['base64']}"
            if item.get("path"):
                item = item["path"]

        if isinstance(item, (bytes, bytearray)):
            return f"data:{fallback_mime};base64,{base64.b64encode(item).decode('utf-8')}"

        s = str(item)
        if s.startswith("data:") or s.startswith("http://") or s.startswith("https://"):
            return s
        if os.path.exists(s):
            uploaded_url = self._upload_local_media_file(s, uploaded_media, media_kind=media_kind)
            if uploaded_url:
                return uploaded_url
            return f"data:{_mime(s) or fallback_mime};base64,{self._encode_file(s)}"

        # If not a file/URL, treat it as a raw base64 payload.
        return f"data:{fallback_mime};base64,{s}"

    def _audio_format(self, item: Any, default_fmt: str = "wav") -> str:
        if isinstance(item, dict):
            fmt = item.get("format")
            if isinstance(fmt, str) and fmt.strip():
                return fmt.strip().lower()
            mt = str(item.get("mime_type") or "").lower()
            if "wav" in mt:
                return "wav"
            if "mpeg" in mt or "mp3" in mt:
                return "mp3"
        s = str(item)
        ext = os.path.splitext(s)[1].lower().lstrip(".")
        if ext in ("wav", "mp3", "m4a", "flac", "ogg"):
            return ext
        return default_fmt

    def _to_input_audio(self, item: Any, uploaded_media: Optional[List[UploadedMedia]] = None) -> Dict[str, str]:
        # OpenAI-compatible multimodal input uses:
        # {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}}
        if isinstance(item, dict):
            if item.get("url"):
                return {"data": str(item["url"]), "format": self._audio_format(item)}
            if item.get("base64"):
                return {"data": str(item["base64"]), "format": self._audio_format(item)}
            if item.get("path"):
                item = item["path"]

        if isinstance(item, (bytes, bytearray)):
            b64 = base64.b64encode(bytes(item)).decode("utf-8")
            return {
                "data": b64,
                "format": "wav",
            }

        s = str(item)
        if s.startswith("http://") or s.startswith("https://"):
            return {"data": s, "format": self._audio_format(s)}
        if s.startswith("data:"):
            # Keep data URL as-is for compatibility with endpoints that accept URLs in `data`.
            return {"data": s, "format": self._audio_format(s)}
        if os.path.exists(s):
            uploaded_url = self._upload_local_media_file(s, uploaded_media, media_kind="audios")
            if uploaded_url:
                return {
                    "data": str(uploaded_url),
                    "format": self._audio_format(s),
                }
            b64 = self._encode_file(s)
            return {
                "data": b64,
                "format": self._audio_format(s),
            }

        # Fallback: treat as raw base64 string.
        return {"data": s, "format": "wav"}

    def _encode_image(self, path: str) -> str:
        return self._encode_file(path)

    def _encode_file(self, path: str) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
        
class NvidiaLLM(LLM):
    def __init__(
        self,
        model: str = "microsoft/phi-4-multimodal-instruct",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **parameters,
    ):
        super().__init__(**parameters)
        self.model = model
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        self.invoke_url = base_url or "https://integrate.api.nvidia.com/v1/chat/completions"
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY not set.")

    def chat(self, system: str, user: str, stop=None, media: Optional[Dict[str, Any]] = None) -> str:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        content = [{"type": "text", "text": user}]
        media = media or {}

        if media.get("texts"):
            texts = media["texts"] if isinstance(media["texts"], list) else [media["texts"]]
            for text in texts:
                content.append({"type": "text", "text": text})

        if media.get("images"):
            imgs = media["images"] if isinstance(media["images"], list) else [media["images"]]
            for img in imgs:
                with open(img, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}})

        if media.get("videos"):
            vids = media["videos"] if isinstance(media["videos"], list) else [media["videos"]]
            for vid in vids:
                content.append({"type": "video_url", "video_url": {"url": vid}})

        if media.get("audio"):
            audios = media["audio"] if isinstance(media["audio"], list) else [media["audio"]]
            for audio in audios:
                with open(audio, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode()
                content.append({"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"}})

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 512,
            "temperature": 0.3,
            "top_p": 0.3,
            "repetition_penalty": 1.2,
            "reasoning": "false"
        }

        resp = requests.post(self.invoke_url, headers=headers, json=payload)
        if not resp.ok:
            raise RuntimeError(f"NvidiaLLM API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise RuntimeError(f"NvidiaLLM unexpected response: {data}")
        return data["choices"][0]["message"]["content"]
    

class HuggingfaceLLM(LLM):
    def __init__(self, model: str = "Qwen/Qwen3-VL-4B-Instruct", **parameters):
        super().__init__(**parameters)
        try:
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
            import torch
        except Exception as e:
            raise RuntimeError("transformers not installed. pip install transformers") from e
        
        quantization_config = BitsAndBytesConfig(
            load_in_8bit=True,
            # 如果你想进一步压榨显存，可以改成 4-bit：
            # load_in_4bit=True,
            # bnb_4bit_compute_dtype=torch.float16
        )

        self._model = Qwen3VLForConditionalGeneration.from_pretrained(model,
                                                                      quantization_config=quantization_config,
                                                                      dtype=torch.bfloat16,
                                                                      **parameters)
        self.processor = AutoProcessor.from_pretrained(model)

    def chat(self, system: str, user: str, stop=None, media: Optional[Dict[str, Any]] = None) -> str:
        media = media or {}

        content = []
        messages = []
        # if system:
        #     content.append({"type": "text", "text": f"{system}"})
        #     messages.append({"role": "system", "content": content})
        #     content = []

        for img in (media.get("images") or []) if isinstance(media.get("images"), list) else ([media["images"]] if media.get("images") else []):
            content.append({"type": "image", "image": str(img)})

        for vid in (media.get("videos") or []) if isinstance(media.get("videos"), list) else ([media["videos"]] if media.get("videos") else []):
            content.append({"type": "video", "video": str(vid)})
            
        for text in (media.get("texts") or []) if isinstance(media.get("texts"), list) else ([media["texts"]] if media.get("texts") else []):
            content.append({"type": "text", "text": str(text)})

        content.append({"type": "text", "text": f"{user}"})
        messages.append({"role": "user", "content": content})

        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt"
        )
        inputs = inputs.to(self._model.device)

        generated_ids = self._model.generate(**inputs, max_new_tokens=512)
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        return output_text[0] if output_text else ""
    
class GradioLLM(LLM):
    def __init__(self, model: str = "Qwen/Qwen3.5-Omni-Offline-Demo",
                 **gradio_kwargs):
        super().__init__(**gradio_kwargs)
        self.space = model
        self.hf_token = gradio_kwargs.get("hf_token") or self.hf_token or os.environ.get("HF_TOKEN")
        self.temperature = gradio_kwargs.get("temperature", 0.7)
        self.top_p = gradio_kwargs.get("top_p", 0.8)
        self.top_k = gradio_kwargs.get("top_k", 20)
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from gradio_client import Client
        except Exception as e:
            raise RuntimeError("gradio_client not installed. pip install gradio_client") from e
        kwargs = {}
        if self.hf_token:
            kwargs["hf_token"] = self.hf_token
        self._client = Client(self.space, verbose=True, **kwargs)

    def chat(self, system: str, user: str, stop=None, media: Optional[Dict[str, Any]] = None) -> str:
        if self._client is None:
            self._init_client()

        from gradio_client import handle_file

        media = media or {}
        text = media.get("texts") or []
        audio = media.get("audio")
        image = media.get("images")
        video = media.get("videos")

        # handle_file wraps a local path or URL; None falls back to a dummy value
        # The API requires all media fields, so pass None-safe defaults
        audio_input = handle_file(str(audio)) if audio else None

        if image:
            image_input = handle_file(str(image[0] if isinstance(image, list) else image))
        else:
            image_input = None

        if video:
            vid_path = str(video[0] if isinstance(video, list) else video)
            video_input = {"video": handle_file(vid_path)}
        else:
            video_input = None
            
        prompt_text = user + ("\n" + "\n".join(text) if text else "")

        result = self._client.predict(
            text=prompt_text,
            audio=audio_input,
            image=image_input,
            video=video_input,
            history=[],
            system_prompt=system,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            api_name="/chat_predict",
        )
        # result[0] is the text response
        chat_history = result[-1]
        if chat_history and isinstance(chat_history, list):
            last_message = chat_history[-1]
            if last_message.get("role") == "assistant":
                return last_message.get("content") or ""
            raise RuntimeError(f"Last message is not from assistant: {last_message}")
        else:
            raise RuntimeError(f"Unexpected response format from Gradio LLM: {result}")