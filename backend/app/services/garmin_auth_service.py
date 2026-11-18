"""Garmin authentication through the official ``garminconnect`` MFA API.

Email and password are used for a single login attempt and are never stored.
When Garmin requires MFA, the pending SSO state is kept in memory under an
opaque session id for at most :data:`_MFA_SESSION_TTL` seconds. The browser
only receives that session id; credentials, OTP codes and SSO cookies never
leave the process and are never logged.
"""

import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models.auth import DisconnectResult, GarminAuthResult, GarminAuthStatus
from app.utils.redact import redact_text

_MFA_SESSION_TTL = 300.0
_MFA_MAX_ATTEMPTS = 3


def _garmin_module() -> Any:
    """Import ``garminconnect`` lazily so a missing package degrades cleanly."""
    import garminconnect

    return garminconnect


def _garmin_class() -> Any:
    """Return the ``garminconnect.Garmin`` class (tests replace this factory)."""
    return _garmin_module().Garmin


def _logger() -> Any:
    from app.logging_config import get_logger

    return get_logger("garmin")


@dataclass
class _MfaSession:
    """Pending Garmin MFA login, kept server-side only."""

    api: Any = field(repr=False)
    client_state: dict[str, Any] = field(repr=False)
    created: float = field(default_factory=time.monotonic)
    attempts: int = 0
    closed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def expired(self) -> bool:
        return time.monotonic() - self.created >= _MFA_SESSION_TTL


class GarminAuthService:
    """Authentication status/login/disconnect flow for Garmin Connect tokens."""

    _sessions: dict[str, _MfaSession] = {}
    _sessions_lock: threading.Lock = threading.Lock()

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ── Session helpers ────────────────────────────────────────

    @classmethod
    def _purge_expired_locked(cls) -> None:
        expired = [sid for sid, session in cls._sessions.items() if session.expired()]
        for sid in expired:
            cls._sessions.pop(sid, None)

    @classmethod
    def _create_session(cls, api: Any, client_state: dict[str, Any]) -> str:
        sid = uuid.uuid4().hex
        with cls._sessions_lock:
            cls._purge_expired_locked()
            cls._sessions[sid] = _MfaSession(api=api, client_state=client_state)
        return sid

    @classmethod
    def _get_session(cls, sid: str) -> _MfaSession | None:
        with cls._sessions_lock:
            cls._purge_expired_locked()
            return cls._sessions.get(sid)

    @classmethod
    def _drop_session(cls, sid: str) -> None:
        with cls._sessions_lock:
            cls._sessions.pop(sid, None)

    @classmethod
    def clear_sessions(cls) -> None:
        """Drop all pending MFA sessions."""
        with cls._sessions_lock:
            cls._sessions.clear()

    @property
    def token_dir(self) -> Path:
        return self._settings.garmin_token_path

    def has_token(self) -> bool:
        """Return True when local Garmin token files exist."""
        return self.token_dir.exists() and any(path.is_file() for path in self.token_dir.rglob("*"))

    # ── Status ─────────────────────────────────────────────────

    def status(self) -> GarminAuthStatus:
        """Verify local Garmin auth without exposing token contents."""
        token_dir = str(self.token_dir)
        if not self.has_token():
            return GarminAuthStatus(
                state="no_token",
                token_found=False,
                token_valid=False,
                token_dir=token_dir,
                message="Aucun token Garmin local détecté. Connecte Garmin depuis l'admin.",
            )

        try:
            api = _garmin_class()(retry_attempts=1)
            api.login(tokenstore=token_dir)
            api.get_full_name()
        except Exception as exc:  # classification below never exposes raw details
            return self._invalid_status(token_dir, exc)

        return GarminAuthStatus(
            state="connected",
            token_found=True,
            token_valid=True,
            token_dir=token_dir,
            message="Token Garmin valide.",
        )

    @staticmethod
    def _invalid_status(token_dir: str, exc: Exception) -> GarminAuthStatus:
        """Map a token check failure to a safe, user-facing status."""
        try:
            gc = _garmin_module()
        except ImportError:
            return GarminAuthStatus(
                state="error",
                token_found=True,
                token_valid=False,
                token_dir=token_dir,
                message="Le module garminconnect est indisponible. Réinstalle les dépendances.",
            )

        _logger().warning("Garmin token verification failed: %s", type(exc).__name__)
        if isinstance(exc, gc.GarminConnectAuthenticationError):
            message = "Token Garmin présent mais invalide ou expiré. Reconnecte Garmin."
        elif isinstance(exc, gc.GarminConnectTooManyRequestsError):
            message = "Garmin limite les tentatives. Patiente quelques minutes puis réessaie."
        elif isinstance(exc, gc.GarminConnectConnectionError):
            message = "Connexion à Garmin impossible. Vérifie le réseau puis réessaie."
        else:
            message = "Vérification des tokens Garmin impossible."
        return GarminAuthStatus(
            state="auth_invalid",
            token_found=True,
            token_valid=False,
            token_dir=token_dir,
            message=message,
        )

    # ── Login ──────────────────────────────────────────────────

    def login(
        self,
        email: str | None = None,
        password: str | None = None,
        otp: str | None = None,
        auth_session_id: str | None = None,
    ) -> GarminAuthResult:
        """Start or complete Garmin authentication.

        Two-step MFA flow:
        1. ``email`` + ``password`` → ``needs_otp`` + ``auth_session_id``
        2. ``auth_session_id`` + ``otp`` → complete authentication
        """
        otp = otp.strip() if otp else None

        if auth_session_id:
            if not otp:
                return GarminAuthResult(
                    ok=False,
                    error_code="otp_invalid",
                    message="Saisis le code de vérification reçu par email.",
                    status=self.status(),
                )
            return self._complete_session_with_otp(auth_session_id, otp)

        if not email or not password:
            return GarminAuthResult(
                ok=False,
                error_code="invalid_credentials",
                message="Email et mot de passe Garmin requis.",
                status=self.status(),
            )

        started = self._start_with_credentials(email, password)
        if otp and started.needs_otp and started.auth_session_id:
            # Legacy single-request flow: credentials + OTP in one call.
            return self._complete_session_with_otp(started.auth_session_id, otp)
        return started

    def _start_with_credentials(self, email: str, password: str) -> GarminAuthResult:
        try:
            gc = _garmin_module()
        except ImportError:
            return self._failure(
                "garmin_unavailable",
                "Le module garminconnect est indisponible. Réinstalle les dépendances.",
            )

        try:
            api = _garmin_class()(return_on_mfa=True)
            mfa_status, client_state = api.client.login(
                email, password, return_on_mfa=True
            )
        except gc.GarminConnectAuthenticationError:
            return self._failure(
                "invalid_credentials",
                "Email ou mot de passe Garmin incorrect.",
            )
        except gc.GarminConnectTooManyRequestsError:
            return self._failure(
                "rate_limited",
                "Garmin limite les tentatives. Patiente quelques minutes puis réessaie.",
            )
        except gc.GarminConnectConnectionError:
            return self._failure(
                "garmin_unavailable",
                "Connexion à Garmin impossible. Vérifie le réseau puis réessaie.",
            )
        except Exception as exc:
            _logger().warning("Garmin credential login failed: %s", type(exc).__name__)
            return self._failure(
                "garmin_unavailable",
                "Authentification Garmin impossible pour le moment. Réessaie plus tard.",
            )

        if mfa_status == "needs_mfa":
            if not isinstance(client_state, dict) or not client_state:
                return self._failure(
                    "garmin_unavailable",
                    "Garmin a demandé un code mais la session MFA est inutilisable. Réessaie.",
                )
            sid = self._create_session(api, client_state)
            return GarminAuthResult(
                ok=False,
                needs_otp=True,
                auth_session_id=sid,
                error_code="otp_required",
                message=(
                    "Code de vérification Garmin envoyé par email. "
                    "Saisis-le pour terminer la connexion."
                ),
                status=self.status(),
            )

        return self._finalize(api)

    def _complete_session_with_otp(self, session_id: str, otp: str) -> GarminAuthResult:
        """Complete MFA by resuming the pending login with the received code."""
        try:
            gc = _garmin_module()
        except ImportError:
            return self._failure(
                "garmin_unavailable",
                "Le module garminconnect est indisponible. Réinstalle les dépendances.",
            )

        session = self._get_session(session_id)
        if session is None:
            return self._failure(
                "otp_expired",
                "Session OTP expirée. Recommence la connexion depuis le début.",
            )

        with session.lock:
            if session.closed or session.expired():
                session.closed = True
                self._drop_session(session_id)
                return self._failure(
                    "otp_expired",
                    "Session OTP expirée. Recommence la connexion depuis le début.",
                )
            if session.attempts >= _MFA_MAX_ATTEMPTS:
                session.closed = True
                self._drop_session(session_id)
                return self._failure(
                    "otp_locked",
                    "Trop de codes incorrects. Recommence la connexion depuis le début.",
                )

            try:
                session.api.resume_login(session.client_state, otp)
            except gc.GarminConnectTooManyRequestsError:
                session.attempts += 1
                if session.attempts >= _MFA_MAX_ATTEMPTS:
                    session.closed = True
                    self._drop_session(session_id)
                return self._failure(
                    "rate_limited",
                    "Garmin limite les tentatives. Patiente quelques minutes puis réessaie.",
                )
            except gc.GarminConnectAuthenticationError as exc:
                text = str(exc).lower()
                if "client_state" in text or "mfa required" in text:
                    session.closed = True
                    self._drop_session(session_id)
                    return self._failure(
                        "otp_expired",
                        "Session OTP expirée. Recommence la connexion depuis le début.",
                    )
                if "connection error" in text:
                    # The MFA endpoints were unreachable; the pending session
                    # is still usable, so do not count this as a wrong code.
                    return self._failure(
                        "garmin_unavailable",
                        "Connexion à Garmin impossible. Vérifie le réseau puis réessaie.",
                    )
                if "mfa verification failed" in text:
                    session.attempts += 1
                    if session.attempts >= _MFA_MAX_ATTEMPTS:
                        session.closed = True
                        self._drop_session(session_id)
                        return self._failure(
                            "otp_locked",
                            "Trop de codes incorrects. Recommence la connexion depuis le début.",
                        )
                    return self._failure(
                        "otp_invalid",
                        "Code de vérification invalide ou expiré. Vérifie le code et réessaie.",
                    )
                _logger().warning(
                    "Garmin MFA completed but profile setup failed: %s",
                    type(exc).__name__,
                )
                session.closed = True
                self._drop_session(session_id)
                return self._failure(
                    "verify_failed",
                    "Garmin a accepté le code mais la session n'a pas pu être finalisée. "
                    "Recommence la connexion.",
                )
            except gc.GarminConnectConnectionError as exc:
                _logger().warning("Garmin MFA token check failed: %s", type(exc).__name__)
                session.closed = True
                self._drop_session(session_id)
                return self._failure(
                    "verify_failed",
                    "Garmin n'a pas pu valider la session après le code. "
                    "Recommence la connexion.",
                )
            except Exception as exc:
                _logger().warning("Garmin MFA resume failed: %s", type(exc).__name__)
                session.closed = True
                self._drop_session(session_id)
                return self._failure(
                    "garmin_unavailable",
                    "Validation du code Garmin impossible. Recommence la connexion.",
                )

            result = self._finalize(session.api)
            session.closed = True
            self._drop_session(session_id)
            return result

    # ── Token persistence ──────────────────────────────────────

    def _finalize(self, api: Any) -> GarminAuthResult:
        """Persist the authenticated tokens and verify them by a fresh login."""
        try:
            api.client.dump(str(self.token_dir))
        except OSError as exc:
            _logger().warning("Garmin token write failed: %s", type(exc).__name__)
            return self._failure(
                "token_write_failed",
                "Authentification réussie mais écriture des tokens impossible. "
                "Vérifie les droits du dossier de tokens.",
            )

        status = self.status()
        if not status.token_valid:
            return GarminAuthResult(
                ok=False,
                error_code="verify_failed",
                message=(
                    "Garmin a accepté la connexion, mais la vérification des tokens "
                    "enregistrés a échoué. Clique sur Vérifier ou recommence."
                ),
                status=status,
            )
        return GarminAuthResult(
            ok=True,
            message="Authentification Garmin réussie.",
            status=status,
        )

    def _failure(self, code: str, message: str) -> GarminAuthResult:
        return GarminAuthResult(
            ok=False,
            error_code=code,
            message=redact_text(message),
            status=self.status(),
        )

    # ── Disconnect ─────────────────────────────────────────────

    def disconnect(self, confirm: bool) -> DisconnectResult:
        """Delete local Garmin token files after explicit confirmation."""
        if not confirm:
            return DisconnectResult(
                ok=False,
                message="Confirmation explicite requise pour supprimer les tokens Garmin locaux.",
            )
        if not self.token_dir.exists():
            return DisconnectResult(ok=True, message="Aucun token Garmin local à supprimer.")
        for child in self.token_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        return DisconnectResult(ok=True, message="Tokens Garmin locaux supprimés.")
