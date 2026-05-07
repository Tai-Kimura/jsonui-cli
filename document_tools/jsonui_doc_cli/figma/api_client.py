"""Figma API client using stdlib urllib.

Provides functions to fetch data from the Figma REST API.
No external dependencies required.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple


FIGMA_API_BASE = "https://api.figma.com/v1"
DEFAULT_TIMEOUT = 60

# Figma API Tier 1 rate limits (requests per minute) by plan.
# Images/render endpoints are Tier 1.
PLAN_RATE_LIMITS = {
    "starter": 10,
    "pro": 15,
    "org": 20,
    "enterprise": 0,  # unlimited
}
PLAN_CHOICES = list(PLAN_RATE_LIMITS.keys())


def get_request_interval(plan: Optional[str]) -> float:
    """Return minimum seconds between Tier 1 API requests for a plan.

    Uses 50% of the limit to leave headroom and avoid 429s.
    """
    if plan is None:
        plan = "starter"
    rpm = PLAN_RATE_LIMITS.get(plan, 10)
    if rpm <= 0:
        return 0.0
    return 60.0 / (rpm * 0.5)

# Figma URL patterns: /file/KEY/... or /design/KEY/...
_URL_PATTERN = re.compile(
    r"figma\.com/(?:file|design)/([a-zA-Z0-9]+)"
)
_NODE_ID_PATTERN = re.compile(r"node-id=([^&]+)")


class _Spinner:
    """Simple CLI spinner for long-running requests."""

    _CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str = "Downloading"):
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "_Spinner":
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            ch = self._CHARS[i % len(self._CHARS)]
            sys.stderr.write(f"\r  {ch} {self._message}...")
            sys.stderr.flush()
            i += 1
            self._stop.wait(0.1)

    def stop(self, final: str = "done") -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        sys.stderr.write(f"\r  {self._message}... {final}\n")
        sys.stderr.flush()


class FigmaAPIError(Exception):
    """Raised when a Figma API request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Optional[str] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after


def _parse_retry_after(http_error: urllib.error.HTTPError) -> Optional[int]:
    """Extract Retry-After seconds from HTTP 429 response header."""
    raw = http_error.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _format_rate_limit_message(retry_after: Optional[int]) -> str:
    """Format a user-friendly rate limit message with wait time and ready time."""
    if retry_after is None or retry_after <= 0:
        return "Rate limited by Figma API. Try again in a few minutes."

    ready_at = datetime.now() + timedelta(seconds=retry_after)

    if retry_after < 60:
        wait_str = f"{retry_after}秒"
    elif retry_after < 3600:
        mins = retry_after // 60
        secs = retry_after % 60
        wait_str = f"{mins}分{secs}秒" if secs else f"{mins}分"
    elif retry_after < 86400:
        hours = retry_after // 3600
        mins = (retry_after % 3600) // 60
        wait_str = f"{hours}時間{mins}分" if mins else f"{hours}時間"
    else:
        days = retry_after // 86400
        hours = (retry_after % 86400) // 3600
        wait_str = f"{days}日{hours}時間" if hours else f"{days}日"

    ready_str = ready_at.strftime("%H:%M:%S")

    return (
        f"Rate limited by Figma API.\n"
        f"  待ち時間: {wait_str} (Retry-After: {retry_after}s)\n"
        f"  再試行可能時刻: {ready_str}"
    )


def resolve_token(token_arg: Optional[str] = None) -> str:
    """Resolve the Figma API token.

    Priority:
      1. Explicit token_arg (from --token CLI flag)
      2. FIGMA_TOKEN environment variable

    Args:
        token_arg: Token passed via CLI argument, or None.

    Returns:
        The resolved API token string.

    Raises:
        FigmaAPIError: If no token is available from any source.
    """
    token = token_arg or os.environ.get("FIGMA_TOKEN")
    if not token:
        raise FigmaAPIError(
            "Figma API token not found. "
            "Set the FIGMA_TOKEN environment variable or pass --token."
        )
    return token


def parse_figma_url(url: str) -> Tuple[str, Optional[str]]:
    """Parse a Figma URL to extract file key and optional node ID.

    Supported formats:
      - https://www.figma.com/file/FILE_KEY/Name
      - https://www.figma.com/design/FILE_KEY/Name?node-id=0-1

    Args:
        url: Full Figma URL string.

    Returns:
        Tuple of (file_key, node_id or None).
        node_id uses Figma's colon format (e.g. "0:1").

    Raises:
        FigmaAPIError: If the URL cannot be parsed.
    """
    m = _URL_PATTERN.search(url)
    if not m:
        raise FigmaAPIError(
            f"Could not parse Figma file key from URL: {url}\n"
            "Expected format: https://www.figma.com/design/FILE_KEY/..."
        )
    file_key = m.group(1)

    node_id = None
    nm = _NODE_ID_PATTERN.search(url)
    if nm:
        # URL uses "0-1" format, API uses "0:1" format
        raw = urllib.parse.unquote(nm.group(1))
        node_id = raw.replace("-", ":")

    return file_key, node_id


def fetch_file(file_key: str, token: str, depth: Optional[int] = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch a Figma file via the REST API.

    Args:
        file_key: The Figma file key (from the file URL).
        token: Figma personal access token.
        depth: Optional tree depth limit (Figma API ?depth=N parameter).
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        FigmaAPIError: On authentication, not-found, rate-limit, or network errors.
    """
    url = f"{FIGMA_API_BASE}/files/{urllib.parse.quote(file_key, safe='')}"
    if depth is not None:
        params = urllib.parse.urlencode({"depth": depth})
        url = f"{url}?{params}"

    req = urllib.request.Request(url)
    req.add_header("X-Figma-Token", token)

    spinner = _Spinner("Fetching from Figma API").start()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            spinner.stop("done")
            return json.loads(raw)

    except urllib.error.HTTPError as e:
        spinner.stop("error")
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        if e.code == 403:
            raise FigmaAPIError(
                "Authentication failed. Check that your Figma token is valid "
                "and has access to this file.",
                status_code=403,
                body=body,
            )
        elif e.code == 404:
            raise FigmaAPIError(
                f"File not found: '{file_key}'. "
                "Verify the file key from your Figma URL.",
                status_code=404,
                body=body,
            )
        elif e.code == 429:
            retry_after = _parse_retry_after(e)
            raise FigmaAPIError(
                _format_rate_limit_message(retry_after),
                status_code=429,
                body=body,
                retry_after=retry_after,
            )
        else:
            raise FigmaAPIError(
                f"Figma API returned HTTP {e.code}: {e.reason}",
                status_code=e.code,
                body=body,
            )

    except urllib.error.URLError as e:
        spinner.stop("error")
        raise FigmaAPIError(f"Network error: {e.reason}")

    except json.JSONDecodeError:
        raise FigmaAPIError("Failed to parse Figma API response (file) as JSON.")


def fetch_nodes(
    file_key: str,
    token: str,
    node_ids: List[str],
    depth: Optional[int] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Fetch specific nodes from a Figma file via the REST API.

    Uses GET /v1/files/{key}/nodes?ids=...

    Args:
        file_key: The Figma file key.
        token: Figma personal access token.
        node_ids: List of node IDs (e.g. ["0:1", "1:2"]).
        depth: Optional tree depth limit.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        FigmaAPIError: On API errors.
    """
    params = {"ids": ",".join(node_ids)}
    if depth is not None:
        params["depth"] = depth
    qs = urllib.parse.urlencode(params)
    url = f"{FIGMA_API_BASE}/files/{urllib.parse.quote(file_key, safe='')}/"
    url += f"nodes?{qs}"

    req = urllib.request.Request(url)
    req.add_header("X-Figma-Token", token)

    spinner = _Spinner("Fetching nodes from Figma API").start()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            spinner.stop("done")
            return json.loads(raw)

    except urllib.error.HTTPError as e:
        spinner.stop("error")
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if e.code == 429:
            retry_after = _parse_retry_after(e)
            raise FigmaAPIError(
                _format_rate_limit_message(retry_after),
                status_code=429,
                body=body,
                retry_after=retry_after,
            )
        raise FigmaAPIError(
            f"Figma API returned HTTP {e.code}: {e.reason}",
            status_code=e.code,
            body=body,
        )

    except urllib.error.URLError as e:
        spinner.stop("error")
        raise FigmaAPIError(f"Network error: {e.reason}")

    except json.JSONDecodeError:
        raise FigmaAPIError("Failed to parse Figma API response (nodes) as JSON.")


def fetch_file_images(
    file_key: str,
    token: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Fetch IMAGE fill URLs from a Figma file.

    Uses GET /v1/files/{key}/images to get download URLs
    for all IMAGE type fills in the file.

    Returns:
        Dict mapping imageRef to download URL.
    """
    url = f"{FIGMA_API_BASE}/files/{urllib.parse.quote(file_key, safe='')}/images"

    req = urllib.request.Request(url)
    req.add_header("X-Figma-Token", token)

    spinner = _Spinner("Fetching image fill URLs").start()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            spinner.stop("done")
            data = json.loads(raw)
            return data.get("meta", {}).get("images", {})

    except urllib.error.HTTPError as e:
        spinner.stop("error")
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if e.code == 429:
            retry_after = _parse_retry_after(e)
            raise FigmaAPIError(
                _format_rate_limit_message(retry_after),
                status_code=429,
                body=body,
                retry_after=retry_after,
            )
        raise FigmaAPIError(
            f"Figma API returned HTTP {e.code}: {e.reason}",
            status_code=e.code,
            body=body,
        )

    except urllib.error.URLError as e:
        spinner.stop("error")
        raise FigmaAPIError(f"Network error: {e.reason}")

    except json.JSONDecodeError:
        raise FigmaAPIError("Failed to parse image fill response as JSON.")


def fetch_image_renders(
    file_key: str,
    token: str,
    node_ids: List[str],
    format: str = "png",
    scale: int = 2,
    timeout: int = DEFAULT_TIMEOUT,
    request_interval: float = 0.0,
) -> dict:
    """Render nodes as images via the Figma API.

    Uses GET /v1/images/{key}?ids=...&format=png&scale=2.
    Batches requests (100 IDs per batch) with rate limit retry.

    Args:
        request_interval: Minimum seconds between batch requests (plan-based throttle).

    Returns:
        Dict mapping node_id to download URL (or None if render failed).
    """
    BATCH_SIZE = 100
    MAX_RETRIES = 5
    DEFAULT_RETRY_WAIT = 30
    MAX_RETRY_WAIT = 300  # cap at 5 minutes per retry

    all_images = {}
    batches = [node_ids[i:i + BATCH_SIZE] for i in range(0, len(node_ids), BATCH_SIZE)]
    total_batches = len(batches)
    last_request_time = time.monotonic()

    for batch_idx, batch in enumerate(batches):
        # Throttle ALL batches (including first) based on plan rate limit
        if request_interval > 0:
            elapsed = time.monotonic() - last_request_time
            wait = request_interval - elapsed
            if wait > 0:
                time.sleep(wait)
        params = urllib.parse.urlencode({
            "ids": ",".join(batch),
            "format": format,
            "scale": scale,
        })
        url = f"{FIGMA_API_BASE}/images/{urllib.parse.quote(file_key, safe='')}?{params}"

        req = urllib.request.Request(url)
        req.add_header("X-Figma-Token", token)

        label = f"Rendering nodes (batch {batch_idx + 1}/{total_batches})"
        spinner = _Spinner(label).start()

        for retry in range(MAX_RETRIES):
            try:
                last_request_time = time.monotonic()
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    raw = response.read()
                    spinner.stop("done")
                    data = json.loads(raw)
                    images = data.get("images", {})
                    all_images.update(images)
                    break

            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if e.code == 429 and retry < MAX_RETRIES - 1:
                    retry_after = _parse_retry_after(e)
                    raw_wait = retry_after or DEFAULT_RETRY_WAIT
                    wait = min(raw_wait, MAX_RETRY_WAIT)
                    ready_at = (datetime.now() + timedelta(seconds=wait)).strftime("%H:%M:%S")
                    cap_note = f" (Retry-After: {raw_wait}s, capped at {MAX_RETRY_WAIT}s)" if raw_wait > MAX_RETRY_WAIT else f" (Retry-After: {raw_wait}s)"
                    spinner.stop(f"rate limited, waiting {wait}s{cap_note} (retry at {ready_at})")
                    time.sleep(wait)
                    spinner = _Spinner(f"{label} (retry {retry + 2})").start()
                    continue

                spinner.stop("error")
                retry_after = _parse_retry_after(e) if e.code == 429 else None
                raise FigmaAPIError(
                    _format_rate_limit_message(retry_after) if e.code == 429
                    else f"Figma API returned HTTP {e.code}: {e.reason}",
                    status_code=e.code,
                    body=body,
                    retry_after=retry_after,
                )

            except urllib.error.URLError as e:
                spinner.stop("error")
                raise FigmaAPIError(f"Network error: {e.reason}")

            except json.JSONDecodeError:
                spinner.stop("error")
                raise FigmaAPIError("Failed to parse render response as JSON.")

    return all_images


def download_url(url: str, dest_path: Path, timeout: int = 30) -> bool:
    """Download a file from URL to local path.

    Returns:
        True on success, False on error.
    """
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(response.read())
        return True
    except Exception:
        return False
