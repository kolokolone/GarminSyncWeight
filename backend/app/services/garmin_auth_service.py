"""Local Garmin authentication helpers inspired by Garmin-MCP.

This service delegates authentication to ``garmin-mcp-auth`` and only stores
the tokens created by that tool in the standard local Garmin token directory.
Email, password and OTP are passed to the subprocess environment/stdin for the
current attempt only; they are never persisted by GarminSyncWeight.
"""

import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models.auth import DisconnectResult, GarminAuthResult, GarminAuthStatus
from app.utils.redact import redact_text


class GarminAuthService:
    """Authentication status/login/disconnect flow for Garmin MCP tokens."""

    # ── OTP session storage (in-memory, not shared between workers) ──
    _sessions: dict[str, dict[str, Any]] = {}
    _sessions_lock: threading.Lock = threading.Lock()
    _SESSION_TTL: float = 300.0  # 5 minutes

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ── Session helpers ────────────────────────────────────────

    @classmethod
    def _create_session(cls, email: str, password: str, process: subprocess.Popen[str]) -> str:
        """Store credentials and subprocess for the MFA step."""
        sid = str(uuid.uuid4())
        with cls._sessions_lock:
            cls._sessions[sid] = {
                "email": email,
                "password": password,
                "process": process,
                "created": time.time(),
            }
        return sid

    @classmethod
    def _get_session(cls, sid: str) -> dict[str, Any] | None:
        """Retrieve a session, or None if expired / missing."""
        with cls._sessions_lock:
            s = cls._sessions.get(sid)
            if s and time.time() - s["created"] < cls._SESSION_TTL:
                return s
            if s:
                del cls._sessions[sid]
        return None

    @classmethod
    def _cleanup_session(cls, sid: str) -> None:
        """Remove a session after use."""
        with cls._sessions_lock:
            cls._sessions.pop(sid, None)

    @property
    def token_dir(self) -> Path:
        return self._settings.garmin_token_path

    def has_token(self) -> bool:
        """Return True when local Garmin token files exist."""
        return self.token_dir.exists() and any(path.is_file() for path in self.token_dir.rglob("*"))

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

        result = self._run_command(
            self._settings.garmin_verify_args,
            timeout_seconds=self._settings.garmin_verify_timeout_seconds,
        )
        if result["ok"]:
            return GarminAuthStatus(
                state="connected",
                token_found=True,
                token_valid=True,
                token_dir=token_dir,
                message="Token Garmin valide.",
            )
        return GarminAuthStatus(
            state="auth_invalid",
            token_found=True,
            token_valid=False,
            token_dir=token_dir,
            message=result["output"] or "Token Garmin présent mais invalide.",
        )

    def login(
        self,
        email: str | None = None,
        password: str | None = None,
        otp: str | None = None,
        auth_session_id: str | None = None,
    ) -> GarminAuthResult:
        """Start or complete Garmin auth via garmin-mcp-auth.

        Two-step MFA flow:
        1. Send email+password → get auth_session_id (needs_otp=True)
        2. Send auth_session_id+otp → complete authentication
        """
        # ── Step 2: complete MFA session with OTP ──────────────
        if auth_session_id and otp:
            return self._complete_session_with_otp(auth_session_id, otp)

        # ── Assisted mode (no credentials) ─────────────────────
        if not email or not password:
            return GarminAuthResult(
                ok=False,
                assisted=True,
                message=(
                    "Authentification Garmin assistée: exécute la commande localement, "
                    "puis clique sur Vérifier. Aucun mot de passe n'est stocké."
                ),
                command=self._settings.garmin_auth_args,
                status=self.status(),
            )

        # ── Legacy: credentials + OTP in one call ──────────────
        if otp:
            return self._complete_with_otp(email, password, otp)

        # ── Step 1: start with credentials, detect MFA ─────────
        return self._start_with_credentials(email, password)

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

    def _start_with_credentials(self, email: str, password: str) -> GarminAuthResult:
        process, stdout, stderr, mfa_detected = self._spawn_auth_reader(email, password)
        mfa_detected.wait(timeout=20)
        if mfa_detected.is_set():
            # MFA required — keep process alive and return a session id
            sid = self._create_session(email, password, process)
            return GarminAuthResult(
                ok=False,
                needs_otp=True,
                auth_session_id=sid,
                error_code="otp_required",
                message="Code MFA Garmin requis. Saisis le code reçu pour terminer.",
                status=self.status(),
            )

        try:
            process.wait(timeout=self._settings.garmin_auth_timeout_seconds)
        except subprocess.TimeoutExpired:
            self._terminate(process)
            return GarminAuthResult(
                ok=False,
                error_code="timeout",
                message="Authentification Garmin interrompue: délai dépassé.",
                status=self.status(),
            )

        output = self._clean_output("\n".join(stdout + stderr))
        status = self.status()
        is_valid = process.returncode == 0 and status.token_valid
        return GarminAuthResult(
            ok=is_valid,
            error_code=None if is_valid else "invalid_credentials",
            message="Authentification Garmin réussie." if is_valid else output,
            status=status,
        )

    def _complete_session_with_otp(self, session_id: str, otp: str) -> GarminAuthResult:
        """Complete MFA by writing OTP to the existing subprocess stdin."""
        session = self._get_session(session_id)
        if session is None:
            return GarminAuthResult(
                ok=False,
                error_code="otp_expired",
                message="Session OTP expirée. Recommence la connexion depuis le début.",
                status=self.status(),
            )

        process = session["process"]
        try:
            if process.stdin is not None:
                process.stdin.write(otp + "\n")
                process.stdin.flush()
                process.stdin.close()
        except OSError:
            self._terminate(process)
            self._cleanup_session(session_id)
            return GarminAuthResult(
                ok=False,
                error_code="otp_invalid",
                message="Erreur de communication avec garmin-mcp-auth. Réessaie.",
                status=self.status(),
            )

        try:
            process.wait(timeout=self._settings.garmin_auth_timeout_seconds)
        except subprocess.TimeoutExpired:
            self._terminate(process)
            self._cleanup_session(session_id)
            return GarminAuthResult(
                ok=False,
                error_code="timeout",
                message="Authentification Garmin interrompue: délai dépassé.",
                status=self.status(),
            )

        self._cleanup_session(session_id)
        status = self.status()
        if process.returncode != 0 or not status.token_valid:
            return GarminAuthResult(
                ok=False,
                error_code="otp_invalid",
                message="Code OTP invalide. Vérifie le code et réessaie.",
                status=status,
            )
        return GarminAuthResult(
            ok=True,
            message="Authentification Garmin réussie.",
            status=status,
        )

    def _complete_with_otp(self, email: str, password: str, otp: str) -> GarminAuthResult:
        process, stdout, stderr, _mfa_detected = self._spawn_auth_reader(email, password)
        try:
            time.sleep(2)
            if process.stdin is not None:
                process.stdin.write(otp + "\n")
                process.stdin.flush()
                process.stdin.close()
        except OSError:
            pass

        try:
            process.wait(timeout=self._settings.garmin_auth_timeout_seconds)
        except subprocess.TimeoutExpired:
            self._terminate(process)

        output = self._clean_output("\n".join(stdout + stderr))
        status = self.status()
        return GarminAuthResult(
            ok=process.returncode == 0 and status.token_valid,
            needs_otp=not status.token_valid,
            error_code=None if (process.returncode == 0 and status.token_valid) else "otp_invalid",
            message="Authentification Garmin réussie." if status.token_valid else output,
            status=status,
        )

    def _spawn_auth_reader(
        self, email: str, password: str,
    ) -> tuple[subprocess.Popen[str], list[str], list[str], threading.Event]:
        env = os.environ.copy()
        env["GARMIN_EMAIL"] = email
        env["GARMIN_PASSWORD"] = password
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        process = subprocess.Popen(
            self._settings.garmin_auth_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout: list[str] = []
        stderr: list[str] = []
        mfa_detected = threading.Event()

        def _reader(stream: Any, dest: list[str], detect_mfa: bool) -> None:
            for line in iter(stream.readline, ""):
                clean = line.rstrip("\n\r")
                dest.append(clean)
                if detect_mfa and "Enter MFA code" in clean:
                    mfa_detected.set()
                    break

        threading.Thread(target=_reader, args=(process.stdout, stdout, True), daemon=True).start()
        threading.Thread(target=_reader, args=(process.stderr, stderr, False), daemon=True).start()
        return process, stdout, stderr, mfa_detected

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @staticmethod
    def _clean_output(output: str) -> str:
        normalized = output.replace("✓", "OK").replace("✗", "ERREUR")
        lines = [line.strip() for line in normalized.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return "Erreur d'authentification Garmin. Vérifie tes identifiants."
        return redact_text(lines[-1])

    @staticmethod
    def _run_command(command: list[str], timeout_seconds: int) -> dict[str, Any]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            return {"ok": False, "output": redact_text(f"Commande introuvable: {exc}")}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "Commande interrompue: délai dépassé."}
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        return {"ok": completed.returncode == 0, "output": redact_text(output.strip())}
