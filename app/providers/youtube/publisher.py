from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time
from typing import Callable, Protocol

from app.core.credentials import CredentialStore


UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
SCOPES = (UPLOAD_SCOPE, MANAGE_SCOPE)


class YouTubeDependencyError(RuntimeError):
    pass


class YouTubeAuthError(RuntimeError):
    pass


class YouTubeUploadError(RuntimeError):
    pass


class TokenStore(Protocol):
    def load(self) -> str: ...
    def save(self, token_json: str) -> bool: ...
    def delete(self) -> None: ...


class KeyringYouTubeTokenStore:
    def __init__(self, credentials: CredentialStore | None = None) -> None:
        self.credentials = credentials or CredentialStore()

    def load(self) -> str:
        return self.credentials.load("youtube-oauth")

    def save(self, token_json: str) -> bool:
        return self.credentials.save("youtube-oauth", token_json)

    def delete(self) -> None:
        self.credentials.delete("youtube-oauth")


@dataclass(frozen=True, slots=True)
class YouTubeAccount:
    channel_id: str
    title: str


@dataclass(frozen=True, slots=True)
class YouTubeVideoMetadata:
    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    category_id: str = "24"
    privacy_status: str = "private"
    publish_at: str | None = None

    def body(self) -> dict:
        if not self.title.strip():
            raise ValueError("YouTube title is required")
        if self.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status must be private, unlisted, or public")
        status: dict[str, object] = {"privacyStatus": self.privacy_status, "selfDeclaredMadeForKids": False}
        if self.publish_at:
            instant = datetime.fromisoformat(self.publish_at.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("publish_at must include a timezone")
            if instant.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise ValueError("publish_at must be in the future")
            status["privacyStatus"] = "private"
            status["publishAt"] = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "snippet": {
                "title": self.title.strip(), "description": self.description.strip(),
                "tags": list(self.tags), "categoryId": self.category_id,
            },
            "status": status,
        }


class YouTubePublisher:
    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, token_store: TokenStore | None = None, *,
                 service_factory: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.token_store = token_store or KeyringYouTubeTokenStore()
        self._service_factory = service_factory
        self._sleep = sleep

    @staticmethod
    def _libraries():
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise YouTubeDependencyError(
                "Install YouTube support with: pip install -e '.[youtube]'"
            ) from exc
        return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload

    def connect(self, client_secrets_path: str | Path) -> YouTubeAccount:
        path = Path(client_secrets_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        _Request, _Credentials, InstalledAppFlow, _build, _HttpError, _Media = self._libraries()
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(path), scopes=list(SCOPES))
            credentials = flow.run_local_server(
                host="127.0.0.1", port=0, open_browser=True, timeout_seconds=180,
            )
        except Exception as exc:
            raise YouTubeAuthError(str(exc)) from exc
        if not self.token_store.save(credentials.to_json()):
            raise YouTubeAuthError("Cannot save YouTube refresh token in the operating-system keyring")
        return self.account()

    def disconnect(self) -> None:
        self.token_store.delete()

    def _credentials(self):
        Request, Credentials, _Flow, _build, _HttpError, _Media = self._libraries()
        raw = self.token_store.load()
        if not raw:
            raise YouTubeAuthError("Connect a YouTube account first")
        try:
            credentials = Credentials.from_authorized_user_info(json.loads(raw), scopes=list(SCOPES))
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                if not self.token_store.save(credentials.to_json()):
                    raise YouTubeAuthError("Cannot update refreshed YouTube credentials")
        except YouTubeAuthError:
            raise
        except Exception as exc:
            raise YouTubeAuthError(f"YouTube authorization expired: {exc}") from exc
        return credentials

    def _service(self):
        credentials = self._credentials()
        if self._service_factory is not None:
            return self._service_factory(credentials)
        _Request, _Credentials, _Flow, build, _HttpError, _Media = self._libraries()
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def account(self) -> YouTubeAccount:
        try:
            response = self._service().channels().list(part="id,snippet", mine=True).execute()
            items = response.get("items") or []
            if not items:
                raise YouTubeAuthError("The Google account has no accessible YouTube channel")
            return YouTubeAccount(str(items[0]["id"]), str(items[0]["snippet"]["title"]))
        except YouTubeAuthError:
            raise
        except Exception as exc:
            raise YouTubeAuthError(str(exc)) from exc

    @staticmethod
    def _http_status(exc: Exception) -> int | None:
        response = getattr(exc, "resp", None)
        return int(response.status) if response is not None and hasattr(response, "status") else None

    def upload(self, video_path: str | Path, metadata: YouTubeVideoMetadata, *,
               progress: Callable[[float], None] | None = None,
               on_remote_id: Callable[[str], None] | None = None,
               remote_id: str | None = None, max_retries: int = 5) -> str:
        if remote_id:
            return remote_id
        path = Path(video_path).expanduser().resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)
        _Request, _Credentials, _Flow, _build, _HttpError, MediaFileUpload = self._libraries()
        request = self._service().videos().insert(
            part="snippet,status", body=metadata.body(),
            media_body=MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True),
        )
        retries = 0
        while True:
            try:
                upload_status, response = request.next_chunk(num_retries=0)
                if upload_status is not None and progress is not None:
                    progress(float(upload_status.progress()))
                if response is not None:
                    video_id = str(response.get("id") or "")
                    if not video_id:
                        raise YouTubeUploadError("YouTube returned no video ID")
                    if on_remote_id is not None:
                        on_remote_id(video_id)
                    if progress is not None:
                        progress(1.0)
                    return video_id
            except Exception as exc:
                status = self._http_status(exc)
                if status not in self.RETRYABLE_STATUS or retries >= max_retries:
                    if status in {401, 403}:
                        raise YouTubeAuthError(str(exc)) from exc
                    raise YouTubeUploadError(str(exc)) from exc
                delay = min(60.0, 2.0 ** retries) + random.random()
                retries += 1
                self._sleep(delay)

    def processing_status(self, video_id: str) -> tuple[str, str | None]:
        try:
            response = self._service().videos().list(
                part="status,processingDetails", id=video_id,
            ).execute()
            items = response.get("items") or []
            if not items:
                raise YouTubeUploadError(f"YouTube video not found: {video_id}")
            details = items[0].get("processingDetails") or {}
            status = str(details.get("processingStatus") or items[0].get("status", {}).get("uploadStatus") or "unknown")
            reason = details.get("processingFailureReason") or items[0].get("status", {}).get("failureReason")
            return status, str(reason) if reason else None
        except YouTubeUploadError:
            raise
        except Exception as exc:
            raise YouTubeUploadError(str(exc)) from exc
