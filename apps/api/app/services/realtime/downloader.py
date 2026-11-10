"""Safe HTTP streaming downloader for GTFS-Realtime feeds."""

import logging

import httpx

from app.services.gtfs.downloader import mask_url_credentials
from app.services.realtime.exceptions import RealtimeDownloadError

logger = logging.getLogger(__name__)

DEFAULT_MAX_REALTIME_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_REALTIME_TIMEOUT_SECONDS = 20.0


async def download_realtime_feed(
    url: str,
    *,
    api_key: str | None = None,
    api_key_header: str = "Authorization",
    headers: dict[str, str] | None = None,
    max_bytes: int = DEFAULT_MAX_REALTIME_BYTES,
    timeout_seconds: float = DEFAULT_REALTIME_TIMEOUT_SECONDS,
) -> bytes:
    """Download a GTFS-Realtime binary feed with bounded size and timeouts.

    Args:
        url: Remote URL of the GTFS-Realtime endpoint.
        api_key: Optional transit API key or token.
        api_key_header: Header name to send the API key in (default 'Authorization').
        headers: Additional HTTP request headers.
        max_bytes: Maximum allowed payload size in bytes.
        timeout_seconds: Request timeout in seconds.

    Returns:
        bytes: Raw protobuf payload bytes.

    Raises:
        RealtimeDownloadError: On timeout, HTTP error, size limit, or network failure.
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

    logger.info("Fetching GTFS-Realtime feed from %s", masked_url)

    try:
        timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url, headers=req_headers) as response:
                if response.status_code >= 400:
                    raise RealtimeDownloadError(
                        f"HTTP {response.status_code} error fetching realtime feed "
                        f"from {masked_url}"
                    )

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise RealtimeDownloadError(
                        f"Realtime feed payload size ({content_length} bytes) "
                        f"exceeds limit ({max_bytes} bytes)"
                    )

                buffer = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise RealtimeDownloadError(
                            "Realtime feed download exceeded maximum size limit "
                            f"({max_bytes} bytes)"
                        )

                logger.info(
                    "Downloaded %d bytes of realtime data from %s",
                    len(buffer),
                    masked_url,
                )
                return bytes(buffer)
    except httpx.TimeoutException as exc:
        raise RealtimeDownloadError(
            f"Timeout fetching realtime feed from {masked_url} after {timeout_seconds}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RealtimeDownloadError(
            f"HTTP status error {exc.response.status_code} from {masked_url}"
        ) from exc
    except httpx.RequestError as exc:
        raise RealtimeDownloadError(
            f"Network error fetching realtime feed from {masked_url}: "
            f"{type(exc).__name__}"
        ) from exc
