from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"            # default / legacy
    deepseek_chat_model: str = "deepseek-chat"           # extraction, classification, summarization
    deepseek_reasoner_model: str = "deepseek-reasoner"   # main chat conversations

    # Resilience for model calls: tunable read timeout + transient retries.
    # A brief gateway blip retries instead of silently dropping; a slow
    # gateway fails fast instead of holding the request for the full timeout.
    llm_timeout_read: float = 60.0
    llm_max_retries: int = 2

    # Per-task model routing (OpenCode Go subscription). Each Pixie task can
    # use a different model. Default = the model validated fastest + cleanest
    # on this plan (clean output + working json_mode). Tune any task via
    # PIXIE_*_MODEL in .env with no code changes.
    pixie_chat_model: str = "qwen3.8-flash"
    pixie_extraction_model: str = "qwen3.8-flash"
    pixie_classification_model: str = "qwen3.8-flash"
    pixie_summarization_model: str = "qwen3.8-flash"

    # Honcho
    honcho_base_url: str = "http://127.0.0.1:58000"
    honcho_workspace: str = "pixie_demo"

    # Postgres
    database_url: str = "postgresql+asyncpg://demo_user@127.0.0.1:55432/pixie_demo"

    # Ollama embeddings
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "embeddinggemma:latest"
    embedding_dim: int = 768

    # Auth (Supabase)
    # supabase_jwt_secret is the HS256 secret used ONLY for dev-mode tokens
    # (create_dev_token). Real Supabase user tokens are ES256, verified against
    # the project JWKS at {supabase_url}/auth/v1/.well-known/jwks.json.
    supabase_jwt_secret: str = "dev-secret-change-me"

    def model_post_init(self, __context) -> None:
        """Validate critical security settings."""
        import secrets as _secrets
        if self.database_url_file:
            self.database_url = Path(self.database_url_file).read_text().strip()

        if not self.auth_dev_mode and self.supabase_jwt_secret == "dev-secret-change-me":
            raise ValueError(
                "SECURITY: supabase_jwt_secret must be changed from default when auth_dev_mode is False. "
                "Set SUPABASE_JWT_SECRET in .env."
            )
        if self.auth_dev_mode:
            import warnings
            warnings.warn(
                "AUTH_DEV_MODE is enabled — locally-minted HS256 test tokens are accepted. "
                "Do NOT use this in production or public-facing deployments.",
                stacklevel=2,
            )
            # When dev mode is on with the default secret, generate a random
            # secret so forged tokens signed with the default won't be accepted.
            if self.supabase_jwt_secret == "dev-secret-change-me":
                self.supabase_jwt_secret = _secrets.token_hex(32)
    supabase_url: str = ""
    supabase_public_key: str = ""
    database_url_file: str = ""
    auth_dev_mode: bool = False

    # Explicit cutover: legacy mode is local-only and is never deployable.
    deployment_environment: str = Field(default="local", pattern=r"^[a-z][a-z0-9-]{0,31}$")
    deployment_mode: str = "development"
    content_encryption_mode: str = "legacy"
    key_registry_root: str = str(BASE_DIR / "runtime" / "key-registry")
    deletion_ledger_root: str = str(BASE_DIR / "runtime" / "deletion-ledger")
    openbao_url: str = ""
    openbao_token_file: str = ""
    openbao_ca_file: str = ""
    supabase_admin_key_file: str = ""
    honcho_erasure_verified: bool = False
    provider_processing_approved: bool = False
    child_processing_approved: bool = False
    privacy_workers_enabled: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:9000", "http://127.0.0.1:9000"]

    # Legacy Pixie vault only. Never point runtime storage at the personal wiki.
    vault_root: str = str(BASE_DIR / "vault")

    # Google Calendar OAuth (MASTER-CALENDAR Part 2). Register the redirect
    # URI in Google Cloud Console → Credentials → OAuth client.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:9000/calendar/google/callback"

    # Token encryption key (Fernet) — encrypts Google OAuth tokens at rest
    token_encryption_key: str = ""

    #File Storage System
      
    # File Storage
    # Dedicated Pixie storage. Deployments mount an encrypted managed volume.
    # Preserve the existing local store until an explicit migration. Linux
    # deployment must override this to the dedicated /vault mount.
    FILE_STORAGE_ROOT: str = str(BASE_DIR / "runtime" / "demo-files")
    MAX_FILE_SIZE_MB: int = 50
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {'.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
    
    @property
    def ALLOWED_MIME_TYPES(self) -> list:
        return [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain',
            'image/png',
            'image/jpeg',
            'image/gif',
            'image/webp',
        ]


settings = Settings()
