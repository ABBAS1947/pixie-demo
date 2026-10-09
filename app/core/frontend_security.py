"""Pure local-preview header policy; no configuration, storage or service imports."""

import re


def nested_segment_path(request_path: str) -> str | None:
    """Resolve Next's dotted segment request against Windows-exported folders."""
    parent, _, leaf = request_path.rpartition("/")
    match = re.fullmatch(r"(__next\.[A-Za-z0-9_-]+)((?:\.[A-Za-z0-9_-]+)+)\.txt", leaf)
    if not match:
        return None
    nested = match[1] + match[2].replace(".", "/") + ".txt"
    return f"{parent}/{nested}" if parent else nested


def preview_headers(base: dict[str, str], *, mode: str, route: str, content_type: str) -> dict[str, str]:
    headers = dict(base)
    if mode == "development" and route == "serve_frontend" and content_type.startswith("text/html"):
        # Blob documents inherit the creator's policy. Restrict their ancestors
        # to this origin and frame sources to blobs, not arbitrary sites.
        headers["X-Frame-Options"] = "SAMEORIGIN"
        headers["Content-Security-Policy"] = base["Content-Security-Policy"].replace(
            "frame-ancestors 'none'", "frame-src blob:; frame-ancestors 'self'")
    return headers
