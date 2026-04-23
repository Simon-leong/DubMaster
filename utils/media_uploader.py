from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote

import requests

from utils.runtime_logger import decorate_upload_action

_HF_DEFAULT_ENDPOINT = "https://huggingface.co"


@dataclass
class UploadedMedia:
    provider: str
    url: str
    remote_id: str = ""
    remote_path: str = ""


class BaseMediaUploader:
    def upload_file(self, local_path: str) -> UploadedMedia:
        raise NotImplementedError

    def cleanup(self, uploaded: List[UploadedMedia]) -> None:
        # Best-effort cleanup by default.
        return


class HuggingFaceDatasetUploader(BaseMediaUploader):
    def __init__(
        self,
        *,
        repo_id: str,
        token: str,
        repo_type: str = "dataset",
        prefix: str = "videos",
        public_base_url: str = _HF_DEFAULT_ENDPOINT,
        cleanup_enabled: bool = False,
    ):
        self.repo_id = str(repo_id or "").strip()
        self.token = str(token or "").strip()
        self.repo_type = str(repo_type or "dataset").strip() or "dataset"
        self.prefix = str(prefix or "videos").strip("/") or "videos"
        # Keep upload/delete operations on the official HuggingFace endpoint.
        self.api_endpoint = _HF_DEFAULT_ENDPOINT
        # URL returned to LLM can be mapped to a mirror endpoint.
        self.public_base_url = self._normalize_public_base_url(public_base_url)
        self.cleanup_enabled = bool(cleanup_enabled)
        self._api = None

        if not self.repo_id:
            raise RuntimeError("HuggingFace uploader requires repo_id")
        if not self.token:
            raise RuntimeError("HuggingFace uploader requires token")

    def _get_api(self):
        if self._api is None:
            try:
                from huggingface_hub import HfApi
            except Exception as e:
                raise RuntimeError("huggingface_hub not installed. pip install huggingface_hub") from e
            self._api = HfApi(endpoint=self.api_endpoint)
        return self._api

    @staticmethod
    def _normalize_public_base_url(value: str) -> str:
        s = str(value or "").strip()
        if not s:
            return _HF_DEFAULT_ENDPOINT
        if not s.startswith("http://") and not s.startswith("https://"):
            s = f"https://{s}"
        return s.rstrip("/")

    def _resolve_url(self, path_in_repo: str) -> str:
        safe_path = quote(path_in_repo.strip("/"), safe="/")
        if self.repo_type == "dataset":
            return f"{self.public_base_url}/datasets/{self.repo_id}/resolve/main/{safe_path}"
        return f"{self.public_base_url}/{self.repo_id}/resolve/main/{safe_path}"

    @decorate_upload_action("upload_file")
    def upload_file(self, local_path: str) -> UploadedMedia:
        p = str(local_path)
        if not os.path.exists(p):
            raise RuntimeError(f"Local file does not exist: {p}")

        name = os.path.basename(p)
        stamp = int(time.time() * 1000)
        rand = uuid.uuid4().hex[:8]
        remote_path = f"{self.prefix}/{stamp}_{rand}_{name}"

        api = self._get_api()
        api.upload_file(
            path_or_fileobj=p,
            path_in_repo=remote_path,
            repo_id=self.repo_id,
            repo_type=self.repo_type,
            token=self.token,
        )

        url = self._resolve_url(remote_path)

        return UploadedMedia(
            provider="huggingface",
            url=url,
            remote_path=remote_path,
        )

    @decorate_upload_action("cleanup")
    def cleanup(self, uploaded: List[UploadedMedia]) -> None:
        if not self.cleanup_enabled:
            return
        api = self._get_api()
        for item in uploaded:
            if item.provider != "huggingface" or not item.remote_path:
                continue
            try:
                api.delete_file(
                    path_in_repo=item.remote_path,
                    repo_id=self.repo_id,
                    repo_type=self.repo_type,
                    token=self.token,
                )
            except Exception:
                # Best effort only.
                continue


class DashScopeFileUploader(BaseMediaUploader):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://dashscope-intl.aliyuncs.com/api/v1",
        purpose: str = "file-extract",
        description: str = "",
        cleanup_enabled: bool = True,
        timeout: int = 300,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or "https://dashscope-intl.aliyuncs.com/api/v1").rstrip("/")
        self.purpose = str(purpose or "file-extract").strip() or "file-extract"
        self.description = str(description or "").strip()
        self.cleanup_enabled = bool(cleanup_enabled)
        self.timeout = int(timeout)

        if not self.api_key:
            raise RuntimeError("DashScope uploader requires api_key")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _endpoint(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @decorate_upload_action("request_json")
    def _request_json(self, method: str, path: str, **kwargs) -> dict:
        resp = requests.request(
            method=method,
            url=self._endpoint(path),
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )
        if resp.status_code >= 400:
            msg = resp.text
            try:
                data = resp.json()
                msg = data.get("message") or data.get("code") or msg
            except Exception:
                pass
            raise RuntimeError(f"DashScope API {method} {path} failed ({resp.status_code}): {msg}")
        try:
            payload = resp.json()
            return payload
        except Exception as e:
            raise RuntimeError(f"DashScope API {method} {path} returned non-JSON response") from e

    def get_file_info(self, file_id: str) -> dict:
        payload = self._request_json("GET", f"files/{file_id}")
        return payload.get("data") or {}

    @decorate_upload_action("upload_file")
    def upload_file(self, local_path: str) -> UploadedMedia:
        p = str(local_path)
        if not os.path.exists(p):
            raise RuntimeError(f"Local file does not exist: {p}")

        form_data = {"purpose": self.purpose, "descriptions": self.description}
        if self.description:
            form_data["descriptions"] = self.description

        with open(p, "rb") as f:
            files = {"files": (os.path.basename(p), f)}
            payload = self._request_json("POST", "files", data=form_data, files=files)

        uploaded_files = ((payload.get("data") or {}).get("uploaded_files") or [])
        if not uploaded_files:
            failed = ((payload.get("data") or {}).get("failed_uploads") or [])
            raise RuntimeError(f"DashScope upload failed: {failed or payload}")

        first = uploaded_files[0]
        file_id = str(first.get("file_id") or "").strip()
        if not file_id:
            raise RuntimeError(f"DashScope upload response missing file_id: {first}")

        info = self.get_file_info(file_id)
        file_url = str(info.get("url") or "").strip()
        if not file_url:
            raise RuntimeError(f"DashScope file info missing url for file_id={file_id}")

        return UploadedMedia(provider="dashscope", url=file_url, remote_id=file_id)

    @decorate_upload_action("cleanup")
    def cleanup(self, uploaded: List[UploadedMedia]) -> None:
        if not self.cleanup_enabled:
            return
        for item in uploaded:
            if item.provider != "dashscope" or not item.remote_id:
                continue
            try:
                self._request_json("DELETE", f"files/{item.remote_id}")
            except Exception:
                # Best effort only.
                continue


def build_media_uploader(
    *,
    method: str,
    cleanup: bool,
    hf_repo_id: str,
    hf_repo_type: str,
    hf_token: str,
    hf_prefix: str,
    hf_public_base_url: str,
    dashscope_api_key: str,
    dashscope_base_url: str,
    dashscope_purpose: str,
    dashscope_description: str,
) -> Optional[BaseMediaUploader]:
    m = str(method or "").strip().lower()
    if m in ("", "none", "disabled", "off"):
        return None
    if m in ("hf", "huggingface"):
        return HuggingFaceDatasetUploader(
            repo_id=hf_repo_id,
            token=hf_token,
            repo_type=hf_repo_type,
            prefix=hf_prefix,
            public_base_url=hf_public_base_url,
            cleanup_enabled=cleanup,
        )
    if m in ("dashscope", "bailian", "aliyun"):
        return DashScopeFileUploader(
            api_key=dashscope_api_key,
            base_url=dashscope_base_url,
            purpose=dashscope_purpose,
            description=dashscope_description,
            cleanup_enabled=cleanup,
        )
    raise RuntimeError(f"Unsupported media upload method: {method}")
