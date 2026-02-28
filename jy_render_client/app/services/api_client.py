from __future__ import annotations

import tempfile
import time
import zipfile
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from urllib3.util.retry import Retry


@dataclass
class ApiConfig:
    base_url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    jobs_endpoint: str = "/api/v1/jobs"
    health_endpoint: str = "/"
    connect_timeout: float = 8.0
    read_timeout: float = 300.0

    def normalize(self) -> "ApiConfig":
        self.base_url = self.base_url.strip().rstrip("/")
        return self


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, config: ApiConfig):
        self.config = config.normalize()
        self.session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def clone(self) -> "ApiClient":
        return ApiClient(ApiConfig(**vars(self.config)))

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.config.connect_timeout, self.config.read_timeout)

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {}
        if self.config.api_key:
            h["X-API-KEY"] = self.config.api_key
        if extra:
            h.update(extra)
        return h

    def build_url(self, endpoint_or_url: str) -> str:
        text = endpoint_or_url.strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
        return urljoin(self.config.base_url + "/", text.lstrip("/"))

    def health_check(self) -> dict:
        if not self.config.base_url:
            raise ApiError("Base URL is empty.")
        candidates = [self.config.health_endpoint, "/"]
        last_error = None
        for path in candidates:
            try:
                url = self.build_url(path)
                resp = self.session.get(url, headers=self.headers(), timeout=self.timeout)
                if resp.ok:
                    try:
                        return resp.json()
                    except ValueError:
                        return {"text": resp.text[:200]}
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.RequestException as exc:
                last_error = str(exc)
        raise ApiError(f"Connection test failed: {last_error}")

    def _zip_dir(
        self,
        draft_dir: Path,
        progress_cb: Callable[[int, int, float], None],
    ) -> Path:
        if not draft_dir.exists() or not draft_dir.is_dir():
            raise ApiError(f"Draft directory not found: {draft_dir}")
        files = [p for p in draft_dir.rglob("*") if p.is_file()]
        if not files:
            raise ApiError(f"Draft directory has no files: {draft_dir}")
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        zip_path = Path(temp.name)
        temp.close()
        start_t = time.perf_counter()
        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                total = len(files)
                for idx, path in enumerate(files, start=1):
                    arc = path.relative_to(draft_dir)
                    zf.write(path, arcname=str(arc))
                    elapsed = max(time.perf_counter() - start_t, 0.001)
                    progress_cb(idx, total, elapsed)
            return zip_path
        except Exception as exc:
            zip_path.unlink(missing_ok=True)
            raise ApiError(f"Zip draft directory failed: {exc}") from exc

    def create_job(
        self,
        draft_dir: Path,
        zip_progress_cb: Callable[[int, int, float], None],
        upload_progress_cb: Callable[[int, int, float], None],
    ) -> dict:
        zip_path = self._zip_dir(draft_dir, zip_progress_cb)
        url = self.build_url(self.config.jobs_endpoint)
        fp = None
        try:
            fp = zip_path.open("rb")
            encoder = MultipartEncoder(
                fields=[("draft", (f"{draft_dir.name}.zip", fp, "application/zip"))]
            )
            start_t = time.perf_counter()

            def _cb(monitor: MultipartEncoderMonitor) -> None:
                elapsed = max(time.perf_counter() - start_t, 0.001)
                upload_progress_cb(monitor.bytes_read, monitor.len, elapsed)

            monitor = MultipartEncoderMonitor(encoder, _cb)
            resp = self.session.post(
                url,
                data=monitor,
                headers=self.headers({"Content-Type": monitor.content_type}),
                timeout=(self.config.connect_timeout, max(self.config.read_timeout, 300.0)),
            )
            if not resp.ok:
                raise ApiError(f"Create job failed HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise ApiError(f"Create job response is not JSON: {resp.text[:200]}") from exc
        except requests.RequestException as exc:
            raise ApiError(f"Create job network error: {exc}") from exc
        finally:
            if fp:
                try:
                    fp.close()
                except Exception:
                    pass
            zip_path.unlink(missing_ok=True)

    def get_job(self, job_id: str) -> dict:
        url = self.build_url(f"{self.config.jobs_endpoint.rstrip('/')}/{job_id}")
        try:
            resp = self.session.get(
                url, headers=self.headers(), timeout=self.timeout
            )
            if not resp.ok:
                raise ApiError(f"Get job failed HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise ApiError(f"Get job response is not JSON: {resp.text[:200]}") from exc
        except requests.RequestException as exc:
            raise ApiError(f"Get job network error: {exc}") from exc

    def download_job(
        self,
        job_id: str,
        dest_path: Path,
        progress_cb: Callable[[int, int, float], None],
    ) -> None:
        full_url = self.build_url(f"{self.config.jobs_endpoint.rstrip('/')}/{job_id}/download")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.session.get(
                full_url, headers=self.headers(), timeout=self.timeout, stream=True
            ) as resp:
                if not resp.ok:
                    raise ApiError(f"Download failed HTTP {resp.status_code}")
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if "application/json" in content_type:
                    raw = resp.content.decode("utf-8", errors="ignore")
                    try:
                        payload = json.loads(raw)
                        msg = payload.get("msg") or payload.get("message") or raw[:200]
                    except Exception:
                        msg = raw[:200]
                    raise ApiError(f"Download failed: {msg}")
                total = int(resp.headers.get("Content-Length", "0"))
                written = 0
                start_t = time.perf_counter()
                with dest_path.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                        elapsed = max(time.perf_counter() - start_t, 0.001)
                        progress_cb(written, total, elapsed)
                if written == 0:
                    raise ApiError("Download failed: empty response.")
        except requests.RequestException as exc:
            raise ApiError(f"Download network error: {exc}") from exc
        except Exception:
            dest_path.unlink(missing_ok=True)
            raise
