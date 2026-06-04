import contextlib
import hashlib
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from chroot_distro.atomic import atomic_replace
from chroot_distro.constants import (
    MIN_SEGMENT_BYTES,
    PROGRAM_NAME,
    PROGRAM_VERSION,
)
from chroot_distro.message import log_error, log_info, msg, warn
from chroot_distro.progress import (
    REDRAW_THRESHOLD_BYTES,
    AggregateByteProgress,
    clear_bar,
    draw_bytes_bar,
    fmt_size,
    loading_line,
)

__all__ = ("download_file", "sha256_file")

_MAX_RETRIES = 3
_RETRY_DELAYS = (1, 2, 4)  # seconds between retries (exponential backoff)
_READ_CHUNK = 262144  # 256 KiB — balances syscall overhead vs memory


def _ua_headers() -> dict[str, str]:
    return {"User-Agent": f"{PROGRAM_NAME}/{PROGRAM_VERSION}"}


def _is_retriable(exc: BaseException) -> bool:
    """Return True for transient server or connection failures."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    return isinstance(exc, ConnectionError) or (
        isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ConnectionError)
    )


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProbeResult:
    """Result of probing a URL for Range support."""

    content_length: int  # total bytes (0 if unknown)
    final_url: str  # URL after redirects
    range_ok: bool  # server supports Accept-Ranges: bytes


@dataclass(frozen=True)
class _Segment:
    """One byte-range slice of a segmented download."""

    index: int
    start: int  # inclusive byte offset
    end: int  # inclusive byte offset
    tmp_path: str  # absolute path to .chunkN.tmp


class _RangeNotSupportedError(Exception):
    """Server responded 200 instead of 206 to a Range request."""


class _FallbackToSingleError(Exception):
    """Signal to retry the whole download as a single connection."""


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def _probe_server(url: str, headers: dict[str, str]) -> "_ProbeResult | None":
    """Send HEAD (or fallback GET Range:0-0) to discover size + Range support.

    Returns *None* on any network error so the caller can fall back silently.
    """
    # --- 1st try: HEAD ---
    try:
        head_req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(head_req) as resp:
            content_length = int(resp.headers.get("Content-Length", 0))
            accept_ranges = (resp.headers.get("Accept-Ranges", "")).lower()
            range_ok = accept_ranges == "bytes"
            return _ProbeResult(
                content_length=content_length,
                final_url=resp.url,
                range_ok=range_ok,
            )
    except urllib.error.HTTPError as exc:
        if exc.code != 405:
            return None  # non-405 → give up probing
    except (OSError, urllib.error.URLError):
        return None

    # --- 2nd try: GET Range: bytes=0-0 ---
    try:
        range_headers = {**headers, "Range": "bytes=0-0", "Accept-Encoding": "identity"}
        range_req = urllib.request.Request(url, headers=range_headers)
        with urllib.request.urlopen(range_req) as resp:
            resp.read(1)  # consume minimal body
            if resp.status == 206:
                # Parse Content-Range: bytes 0-0/TOTAL
                cr = resp.headers.get("Content-Range", "")
                total = 0
                if "/" in cr:
                    with contextlib.suppress(ValueError, IndexError):
                        total = int(cr.rsplit("/", 1)[1])
                return _ProbeResult(
                    content_length=total,
                    final_url=resp.url,
                    range_ok=True,
                )
            # Server returned 200 — no range support
            return _ProbeResult(
                content_length=int(resp.headers.get("Content-Length", 0)),
                final_url=resp.url,
                range_ok=False,
            )
    except (OSError, urllib.error.URLError):
        return None


# ---------------------------------------------------------------------------
# Segment computation
# ---------------------------------------------------------------------------


def _compute_segments(total: int, n: int, dest: str) -> list[_Segment]:
    """Split *total* bytes into up to *n* non-overlapping segments.

    Enforces ``MIN_SEGMENT_BYTES`` — the actual segment count may be less
    than *n* for small files.
    """
    n = min(n, max(1, total // MIN_SEGMENT_BYTES))
    n = max(1, n)
    chunk_size = total // n
    segments: list[_Segment] = []
    for i in range(n):
        start = i * chunk_size
        end = total - 1 if i == n - 1 else (i + 1) * chunk_size - 1
        segments.append(
            _Segment(
                index=i,
                start=start,
                end=end,
                tmp_path=f"{dest}.chunk{i}.tmp",
            )
        )
    return segments


# ---------------------------------------------------------------------------
# Per-segment download
# ---------------------------------------------------------------------------


def _download_segment(
    seg: _Segment,
    url: str,
    ua_headers: dict[str, str],
    aggregate: "AggregateByteProgress | None",
    abort_event: threading.Event,
) -> None:
    """Download one byte-range segment to *seg.tmp_path*.

    Raises ``_RangeNotSupportedError`` if the server responds 200 instead of 206.
    Raises ``KeyboardInterrupt`` if *abort_event* is set.
    """
    downloaded = 0
    if os.path.isfile(seg.tmp_path):
        downloaded = os.path.getsize(seg.tmp_path)

    expected = seg.end - seg.start + 1
    if downloaded >= expected:
        return

    # Each thread gets its own opener to avoid urllib's internal
    # connection serialisation when sharing the default global opener.
    opener = urllib.request.build_opener()
    for attempt in range(_MAX_RETRIES + 1):
        try:
            start_pos = seg.start + downloaded
            headers = {
                **ua_headers,
                "Range": f"bytes={start_pos}-{seg.end}",
                "Accept-Encoding": "identity",  # critical: no gzip, breaks range math
            }
            req = urllib.request.Request(url, headers=headers)
            mode = "ab" if downloaded > 0 else "wb"
            with opener.open(req) as resp, open(seg.tmp_path, mode) as fh:
                if resp.status != 206:
                    raise _RangeNotSupportedError(f"Expected 206, got {resp.status}")
                unsent = 0  # bytes not yet reported to aggregate
                while True:
                    if abort_event.is_set():
                        raise KeyboardInterrupt
                    chunk = resp.read(_READ_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    if aggregate:
                        unsent += len(chunk)
                        if unsent >= REDRAW_THRESHOLD_BYTES:
                            aggregate.add(unsent)
                            unsent = 0
                # flush remaining unsent bytes
                if aggregate and unsent:
                    aggregate.add(unsent)
                fh.flush()
                os.fsync(fh.fileno())
            # verify size
            actual = os.path.getsize(seg.tmp_path)
            if actual != expected:
                raise RuntimeError(f"Segment {seg.index}: expected {expected} bytes, got {actual}")
            return
        except _RangeNotSupportedError:
            raise  # not retriable; bubble up immediately
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            if _is_retriable(exc) and attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt])
                if os.path.isfile(seg.tmp_path):
                    downloaded = os.path.getsize(seg.tmp_path)
                continue
            raise


# ---------------------------------------------------------------------------
# Chunk concatenation
# ---------------------------------------------------------------------------


def _concat_chunks(segments: list[_Segment], dest: str) -> None:
    """Concatenate segment temp files in order into *dest* atomically."""
    with atomic_replace(dest) as tmp, open(tmp, "wb") as out:
        for seg in sorted(segments, key=lambda s: s.index):
            with open(seg.tmp_path, "rb") as inp:
                shutil.copyfileobj(inp, out, length=1 << 20)
        out.flush()
        os.fsync(out.fileno())


# ---------------------------------------------------------------------------
# Multi-connection orchestrator
# ---------------------------------------------------------------------------


def _download_multi(
    url: str,
    dest: str,
    probe: _ProbeResult,
    connections: int,
) -> None:
    """Download *url* to *dest* using multiple parallel Range connections."""
    chunks_meta_path = f"{dest}.chunks.json"
    segments = None

    # Try to load existing chunk metadata
    if os.path.isfile(chunks_meta_path):
        try:
            with open(chunks_meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("total") == probe.content_length:
                segments = [
                    _Segment(
                        index=s["index"],
                        start=s["start"],
                        end=s["end"],
                        tmp_path=s["tmp_path"],
                    )
                    for s in meta.get("segments", [])
                ]
        except Exception:
            pass

    if not segments:
        # Clean up any potential stale chunk files
        for i in range(connections + 5):
            with contextlib.suppress(OSError):
                os.remove(f"{dest}.chunk{i}.tmp")
        with contextlib.suppress(OSError):
            os.remove(chunks_meta_path)

        segments = _compute_segments(probe.content_length, connections, dest)
        if len(segments) == 1:
            raise _FallbackToSingleError

        # Save metadata
        try:
            meta = {
                "total": probe.content_length,
                "segments": [
                    {
                        "index": s.index,
                        "start": s.start,
                        "end": s.end,
                        "tmp_path": s.tmp_path,
                    }
                    for s in segments
                ],
            }
            with open(chunks_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except Exception:
            pass

    if len(segments) == 1:
        raise _FallbackToSingleError

    total = probe.content_length
    aggregate = AggregateByteProgress(total, label="download")

    already_downloaded = 0
    for seg in segments:
        if os.path.isfile(seg.tmp_path):
            already_downloaded += os.path.getsize(seg.tmp_path)
    if already_downloaded:
        aggregate.add(already_downloaded)

    abort_event = threading.Event()
    ua = _ua_headers()

    if already_downloaded:
        log_info(
            f"Resuming download of {fmt_size(total)} (already downloaded {fmt_size(already_downloaded)}) in {len(segments)} segments..."
        )
    else:
        log_info(f"Downloading {fmt_size(total)} in {len(segments)} segments ({len(segments)} connections)...")

    success = False
    try:
        with ThreadPoolExecutor(max_workers=len(segments)) as pool:
            futures = {
                pool.submit(
                    _download_segment,
                    seg,
                    probe.final_url,
                    ua,
                    aggregate,
                    abort_event,
                ): seg
                for seg in segments
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except _RangeNotSupportedError as exc:
                    abort_event.set()
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise _FallbackToSingleError from exc
                except KeyboardInterrupt:
                    abort_event.set()
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
                except Exception:
                    abort_event.set()
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise

        clear_bar()
        log_info("Assembling segments...")
        _concat_chunks(segments, dest)
        log_info(f"Finished downloading ({fmt_size(total)}).")
        success = True

    finally:
        aggregate.clear()
        if success:
            for seg in segments:
                with contextlib.suppress(OSError):
                    os.remove(seg.tmp_path)
            with contextlib.suppress(OSError):
                os.remove(chunks_meta_path)


# ---------------------------------------------------------------------------
# Single-connection download (original logic, renamed)
# ---------------------------------------------------------------------------


def _download_single(url: str, dest: str) -> None:
    """Download *url* to *dest* with a single connection (original path)."""
    req = urllib.request.Request(url, headers=_ua_headers())
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt - 1]
            warn(f"Retry {attempt}/{_MAX_RETRIES} in {delay}s (reason: {last_exc})...")
            time.sleep(delay)

        try:
            with atomic_replace(dest) as tmp, urllib.request.urlopen(req) as resp, open(tmp, "wb") as fh:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    draw_bytes_bar(downloaded, total, noun="downloaded")
                fh.flush()
                os.fsync(fh.fileno())
            clear_bar()
            log_info(f"Finished downloading ({fmt_size(downloaded)}).")
            return
        except KeyboardInterrupt:
            clear_bar()
            raise
        except BaseException as exc:
            clear_bar()
            if _is_retriable(exc) and attempt < _MAX_RETRIES:
                last_exc = exc
                continue
            msg()
            log_error("Download failure, please check your network connection.")
            raise RuntimeError(f"Cannot download {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def download_file(url: str, dest: str) -> None:
    """Download *url* to *dest* with progress output, redirects, and retries.

    Uses multiple parallel Range connections when ``CD_DOWNLOAD_WORKERS > 1``
    and the server advertises ``Accept-Ranges`` support.  Falls back to a
    single connection automatically on any incompatibility.
    """
    from chroot_distro.constants import layer_download_workers

    connections = layer_download_workers()

    if connections > 1:
        # Probe with immediate spinner feedback
        with loading_line("Connecting..."):
            probe = _probe_server(url, _ua_headers())

        if probe is not None and probe.range_ok and probe.content_length > 0:
            try:
                _download_multi(url, dest, probe, connections)
                return
            except _FallbackToSingleError:
                log_info("Range download not possible, falling back to single connection.")
            except KeyboardInterrupt:
                clear_bar()
                raise
            except Exception as exc:
                clear_bar()
                raise RuntimeError(f"Cannot download {url}: {exc}") from exc

    # Single-connection fallback
    _download_single(url, dest)


def sha256_file(path: str) -> str:
    """Compute and return the SHA-256 hex digest of *path*, with a progress bar."""
    h = hashlib.sha256()
    total = os.path.getsize(path)
    processed = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            processed += len(chunk)
            draw_bytes_bar(processed, total, noun="processed")
    clear_bar()
    return h.hexdigest()
