import os
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import learning, calendar, chat, dashboard, feedback, files, health, notes, onboarding, quick_note, review, teacher, teach_v2, transcript, users
from app.services.file_storage import FileStorage
from app.core.runtime import verify_database_revision
from app.core.frontend_security import nested_segment_path, preview_headers
from app.services.learning_worker import run_one
from app.services.review_worker import run_one as run_review_job
from app.api import review_sessions
from app.api import privacy, schools
from app.core.config import settings
from app.services.content_crypto import CryptoUnavailable, CiphertextInvalid
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent.parent
# Match next.config.ts distDir: static export is the build's final directory.
# Explicit deployment override remains available; never silently fall back to stale assets.
OUT_DIR = Path(os.environ.get("PIXIE_FRONTEND_DIR", str(BASE_DIR / "frontend" / ".next-build"))).resolve()

app = FastAPI(title="Study Partner", version="0.1.0")
_learning_worker_task: asyncio.Task | None = None
_review_worker_task: asyncio.Task | None = None
_privacy_worker_tasks: list[asyncio.Task] = []

# Dev CORS. The static export's API client points at http://127.0.0.1:9000, and
# `npm run dev` on :3000 is cross-origin. Auth is a Bearer header (no cookies),
# so a permissive dev allow-list is safe. Tighten before any public deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Deletion-Receipt", "X-Export-Ticket"],
)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(onboarding.router)
app.include_router(chat.router)
app.include_router(learning.router)
app.include_router(teach_v2.router)  # Postgres turn engine
app.include_router(transcript.router)  # per-child teaching record
app.include_router(teacher.router)  # teacher dashboard (teacher-only)
app.include_router(notes.router)
app.include_router(quick_note.router)
app.include_router(calendar.router)
app.include_router(feedback.router)
app.include_router(files.router)
app.include_router(review.router)
app.include_router(review_sessions.router)
app.include_router(dashboard.router)
app.include_router(privacy.router)
app.include_router(schools.router)

@app.exception_handler(CryptoUnavailable)
async def crypto_unavailable(request: Request, exc):
    return JSONResponse({"detail": "Encrypted storage is temporarily unavailable"}, status_code=503)

@app.exception_handler(CiphertextInvalid)
async def invalid_ciphertext(request: Request, exc):
    logging.getLogger(__name__).error("Encrypted storage authentication failed")
    return JSONResponse({"detail": "Stored content could not be verified"}, status_code=503)

@app.exception_handler(PermissionError)
async def processing_not_allowed(request: Request, exc):
    return JSONResponse({"detail": "This processing operation is not currently authorized"}, status_code=403)


@app.on_event("startup")
async def startup_event():
    global _learning_worker_task, _review_worker_task
    if not os.environ.get("PIXIE_TESTING"):
        if settings.content_encryption_mode not in {"legacy", "required"}:
            raise RuntimeError("Invalid content encryption mode")
        if settings.deployment_mode not in {"development", "pilot", "production"}:
            raise RuntimeError("Invalid deployment mode")
        if settings.deployment_mode != "development":
            if settings.auth_dev_mode or settings.content_encryption_mode != "required":
                raise RuntimeError("Deployed environments require real auth and encrypted storage")
            if not settings.openbao_url.startswith("https://") or not Path(settings.openbao_token_file).is_file():
                raise RuntimeError("OpenBao TLS and file-mounted credentials are required")
            if any(not origin.startswith("https://") for origin in settings.cors_origins):
                raise RuntimeError("Deployed frontend origins must use HTTPS")
        if settings.deployment_mode == "production":
            # This implementation has not received gate/testing authorization.
            # Pilot controls do not silently become a production release.
            raise RuntimeError("Production release is blocked pending verified gate, migration, provider, child and recovery evidence")
        revision = await verify_database_revision()
        print(f"Database schema verified at: {revision}")
    FileStorage.initialize()
    # One bounded at-least-once worker runs with this API process in local and
    # single-worker deployments. Production multi-worker deployments should
    # run the same worker as a separate service to avoid duplicate polling.
    async def _drain_jobs(worker):
        while True:
            try:
                did_work = await worker()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger(__name__).warning('Background worker failed; retrying polling')
                did_work = False
            if not did_work:
                await asyncio.sleep(1)
    if not os.environ.get("PIXIE_TESTING"):
        _learning_worker_task = asyncio.create_task(_drain_jobs(run_one))
        _review_worker_task = asyncio.create_task(_drain_jobs(run_review_job))
        from app.services.deletion_worker import run_one as delete_one
        from app.services.privacy_export import run_one as export_one
        from app.services.retention_worker import run_one as expire_one
        if settings.privacy_workers_enabled:
            for worker in (delete_one, export_one, expire_one):
                _privacy_worker_tasks.append(asyncio.create_task(_drain_jobs(worker)))
    print(f"File storage initialized at: {FileStorage.STORAGE_ROOT}")


@app.on_event("shutdown")
async def shutdown_event():
    for task in (_learning_worker_task, _review_worker_task, *_privacy_worker_tasks):
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# Next.js static export (output: "export", no trailingSlash) lives in
# frontend/.next-build/. Routes are flat .html files: /app -> app.html,
# /app/calendar -> app/calendar.html. _next/ holds the JS/CSS chunks.

# Cache policy (fixed Aug 13 — stale-UI landmine): HTML is never cached so a
# rebuild is visible on the next reload; _next chunks are content-hashed by
# Next, so they get the longest safe cache (immutable) and new builds fetch
# fresh chunk names automatically.
NO_CACHE = {"Cache-Control": "no-cache"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

# MEDIUM-08: Security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' https://fonts.gstatic.com; connect-src 'self' http://127.0.0.1:* http://localhost:* https://api.dicebear.com https://example.supabase.co https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; frame-ancestors 'none'",
}


@app.middleware("http")
async def security_and_cache_headers(request, call_next):
    response = await call_next(request)
    route = request.scope.get("route")
    for key, value in preview_headers(SECURITY_HEADERS, mode=settings.deployment_mode,
            route=getattr(route, "name", ""), content_type=response.headers.get("content-type", "")).items():
        response.headers[key] = value
    if settings.deployment_mode != "development":
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    # Every API response, including errors and authenticated downloads, is private.
    response.headers["Cache-Control"] = "no-store"
    # Static asset caching
    if request.url.path.startswith("/_next/"):
        response.headers["Cache-Control"] = IMMUTABLE["Cache-Control"]
    return response


if (OUT_DIR / "_next").is_dir():
    app.mount("/_next", StaticFiles(directory=OUT_DIR / "_next"), name="next-assets")


# Resolve OUT_DIR once at startup for path containment checks
_OUT_ROOT = OUT_DIR.resolve()


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_frontend(full_path: str):
    if settings.deployment_mode != "development":
        raise HTTPException(404, "Not found")
    clean = full_path.rstrip("/") or "index"

    # SECURITY (HIGH-02): Resolve candidate paths and verify they remain
    # inside OUT_DIR before serving. Prevents path-traversal attacks like
    # "../../../.env" or "../../../app/main.py".
    candidates = [
        OUT_DIR / f"{clean}.html",
        OUT_DIR / clean / "index.html",
        OUT_DIR / clean,
    ]
    # Windows exports can retain nested segment directories while the client
    # requests dotted filenames. Only serve an existing, contained artifact.
    nested_segment = nested_segment_path(clean)
    if nested_segment:
        candidates.append(OUT_DIR / nested_segment)

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.is_relative_to(_OUT_ROOT):
            cache = IMMUTABLE if "/_next/" in str(candidate) else NO_CACHE
            return FileResponse(resolved, headers=cache)

    return FileResponse(OUT_DIR / "404.html", status_code=404, headers=NO_CACHE)
