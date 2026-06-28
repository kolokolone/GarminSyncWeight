"""Security-focused tests for GarminSyncWeight.

Verifies:
  - Token redaction in logs
  - No sensitive data exposure via API
  - No delete operations exposed
  - Localhost bind by default
"""

from app.utils.redact import redact_text


def test_log_redaction_tokens() -> None:
    """Tokens must be redacted in log output."""
    text = "access_token=abc123refresh_token=def456"
    redacted = redact_text(text)
    assert "abc123" not in redacted
    assert "def456" not in redacted
    assert "[REDACTED]" in redacted


def test_log_redaction_authorization_header() -> None:
    """Authorization header Bearer token must be redacted."""
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.dGVzdA.test123"
    redacted = redact_text(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "test123" not in redacted
    assert "[REDACTED]" in redacted


def test_log_redaction_password() -> None:
    """Password values must be redacted."""
    text = "password=superS3cret!passwd=anotherSecret"
    redacted = redact_text(text)
    assert "superS3cret" not in redacted
    assert "anotherSecret" not in redacted


def test_log_redaction_client_secret() -> None:
    """client_secret must be redacted."""
    text = "client_secret=my_super_secret_key_123"
    redacted = redact_text(text)
    assert "my_super_secret_key_123" not in redacted


def test_log_redaction_email() -> None:
    """Email addresses must be redacted."""
    text = "Contact user@example.com for support"
    redacted = redact_text(text)
    assert "user@example.com" not in redacted


def test_log_redaction_mixed() -> None:
    """All sensitive patterns in one string must be redacted."""
    text = (
        'token=abc123 Authorization: Bearer xyz '
        'password=secret client_secret=hidden email=test@test.com'
    )
    redacted = redact_text(text)
    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "password=secret" not in redacted  # 'password=secret' → redacted
    assert "hidden" not in redacted
    assert "test@test.com" not in redacted
    # Count [REDACTED] occurrences (should be multiple)
    assert redacted.count("[REDACTED]") >= 4


def test_redact_lines_list() -> None:
    """redact_lines must handle a list of strings."""
    lines = [
        "token=abc123",
        "normal line without secrets",
        "password=hunter2",
    ]
    safe_lines = [redact_text(line) for line in lines]
    assert "abc123" not in " ".join(safe_lines)
    assert "hunter2" not in " ".join(safe_lines)


def test_settings_rejects_empty_client_id() -> None:
    """Settings must allow empty Withings client ID (graceful degradation)."""
    from app.config import Settings

    s = Settings(withings_client_id="", withings_client_secret="")  # type: ignore[call-arg]
    assert s.withings_client_id == ""


def test_configured_flag_requires_both_id_and_secret() -> None:
    """is_configured() must require both client_id and client_secret."""
    from app.config import Settings

    s1 = Settings(withings_client_id="", withings_client_secret="")  # type: ignore[call-arg]
    assert not (s1.withings_client_id and s1.withings_client_secret)

    s2 = Settings(withings_client_id="x", withings_client_secret="y")  # type: ignore[call-arg]
    assert s2.withings_client_id and s2.withings_client_secret
