"""Safe HTTP streaming downloader for GTFS static archives."""

import logging
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.services.gtfs.archive import DEFAULT_MAX_ARCHIVE_BYTES
from app.services.gtfs.exceptions import GTFSDownloadError

logger = logging.getLogger(__name__)

# Query parameter keys that typically contain credentials
SENSITIVE_PARAM_NAMES = frozenset(
    {"key", "api_key", "apikey", "token", "access_token", "secret", "auth"}
)


def mask_url_credentials(url: str) -> str:
    """Mask credentials and sensitive parameters in a URL for safe logging."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc

        # Mask HTTP basic credentials in netloc
        if "@" in netloc:
            creds, host = netloc.split("@", 1)
            if ":" in creds:
                user = creds.split(":", 1)[0]
                netloc = f"{user}:***@{host}"
            else:
                netloc = f"***@{host}"

        # Mask query params
        if parsed.query:
            query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
            masked_pairs = [
                (k, "***" if k.lower() in SENSITIVE_PARAM_NAMES else v)
                for k, v in query_pairs
            ]
            query = urlencode(masked_pairs, safe="*")
        else:
            query = parsed.query

        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                query,
                parsed.fragment,
            )
        )
    except Exception:
        # Fallback regex masking
        return re.sub(
            r"(key|api_key|token|secret)=[^&]+",
            r"\1=***",
            url,
            flags=re.IGNORECASE,
        )


async def download_gtfs_feed(
    url: str,
    *,
    api_key: str | None = None,
    api_key_header: str = "Authorization",
    headers: dict[str, str] | None = None,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    timeout_seconds: float = 60.0,
) -> bytes:
    """Download a GTFS archive with size bounds, streaming verification, and timeout.

    Args:
        url: Remote URL of the GTFS zip archive.
        api_key: Optional API key or bearer token.
        api_key_header: Header name to send the API key in (default 'Authorization').
        headers: Additional HTTP request headers.
        max_bytes: Maximum allowed download size in bytes.
        timeout_seconds: Total request timeout in seconds.

    Returns:
        bytes: The downloaded archive content.

    Raises:
        GTFSDownloadError: On timeout, HTTP error, size limit, or network failure.
    """
    masked_url = mask_url_credentials(url)
    req_headers = dict(headers or {})

    if api_key:
        if api_key_header.lower() == "authorization" and not api_key.lower().startswith(
            "bearer "
        ):
            req_headers[api_key_header] = f"Bearer {api_key}"
        else:
            req_headers[api_key_header] = api_key

    logger.info("Initiating download for GTFS feed from %s", masked_url)

    timeout = httpx.Timeout(timeout_seconds, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=req_headers) as response:
                if response.status_code >= 400:
                    msg = (
                        f"Download failed from {masked_url}: "
                        f"HTTP {response.status_code}"
                    )
                    raise GTFSDownloadError(msg)

                # Check Content-Length header early if available
                content_length_str = response.headers.get("content-length")
                if content_length_str and content_length_str.isdigit():
                    content_length = int(content_length_str)
                    if content_length > max_bytes:
                        raise GTFSDownloadError(
                            f"Feed Content-Length ({content_length} B) exceeds limit "
                            f"({max_bytes} B)"
                        )

                buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise GTFSDownloadError(
                            f"Feed download exceeded max allowed size of {max_bytes} B"
                        )

                logger.info(
                    "Successfully downloaded %d bytes from %s",
                    len(buffer),
                    masked_url,
                )
                return bytes(buffer)
    except httpx.TimeoutException as exc:
        raise GTFSDownloadError(
            f"Feed download timed out after {timeout_seconds}s from {masked_url}"
        ) from exc
    except httpx.RequestError as exc:
        raise GTFSDownloadError(
            f"Network error downloading feed from {masked_url}: {exc}"
        ) from exc


async def download_gtfs_archive_to_file(
    url: str,
    destination: Path | str,
    *,
    api_key: str | None = None,
    api_key_header: str = "Authorization",
    headers: dict[str, str] | None = None,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    timeout_seconds: float = 60.0,
) -> Path:
    """Download a GTFS archive directly to a file with atomic temporary replacement.

    If an error occurs at any point during download, the partial file is removed.
    """
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    masked_url = mask_url_credentials(url)
    req_headers = dict(headers or {})
    if api_key:
        if api_key_header.lower() == "authorization" and not api_key.lower().startswith(
            "bearer "
        ):
            req_headers[api_key_header] = f"Bearer {api_key}"
        else:
            req_headers[api_key_header] = api_key

    timeout = httpx.Timeout(timeout_seconds, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=req_headers) as response:
                if response.status_code >= 400:
                    msg = (
                        f"Download failed from {masked_url}: "
                        f"HTTP {response.status_code}"
                    )
                    raise GTFSDownloadError(msg)

                content_length_str = response.headers.get("content-length")
                if content_length_str and content_length_str.isdigit():
                    content_length = int(content_length_str)
                    if content_length > max_bytes:
                        raise GTFSDownloadError(
                            f"Feed Content-Length ({content_length} B) exceeds limit "
                            f"({max_bytes} B)"
                        )

                downloaded_bytes = 0
                with open(part_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_bytes:
                            msg = (
                                f"Feed download exceeded max allowed size of "
                                f"{max_bytes} B"
                            )
                            raise GTFSDownloadError(msg)
                        f.write(chunk)

                if part_path.exists():
                    part_path.replace(dest_path)
                return dest_path
    except Exception as exc:
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass
        if isinstance(exc, GTFSDownloadError):
            raise
        if isinstance(exc, httpx.TimeoutException):
            raise GTFSDownloadError(
                f"Feed download timed out after {timeout_seconds}s from {masked_url}"
            ) from exc
        raise GTFSDownloadError(
            f"Network error downloading feed from {masked_url}: {exc}"
        ) from exc
