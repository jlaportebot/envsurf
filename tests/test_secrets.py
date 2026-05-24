"""Tests for envsurf secret detection."""

from envsurf.secrets import detect_secrets, is_placeholder


class TestIsPlaceholder:
    def test_empty(self) -> None:
        assert is_placeholder("") is True

    def test_whitespace(self) -> None:
        assert is_placeholder("   ") is True

    def test_changeme(self) -> None:
        assert is_placeholder("changeme") is True
        assert is_placeholder("change_me") is True
        assert is_placeholder("CHANGEME") is True

    def test_your_prefix(self) -> None:
        assert is_placeholder("your_api_key") is True

    def test_angle_brackets(self) -> None:
        assert is_placeholder("<your-key-here>") is True

    def test_square_brackets(self) -> None:
        assert is_placeholder("[insert-key]") is True

    def test_env_var_ref(self) -> None:
        assert is_placeholder("${OTHER_VAR}") is True
        assert is_placeholder("$OTHER_VAR") is True

    def test_boolean(self) -> None:
        assert is_placeholder("true") is True
        assert is_placeholder("false") is True

    def test_real_value(self) -> None:
        assert is_placeholder("sk-abc123def456ghi789") is False


class TestDetectSecrets:
    def test_real_api_key(self) -> None:
        findings = detect_secrets("OPENAI_API_KEY", "sk-abc123def456ghi789jkl012mno345pqr678", 1)
        assert len(findings) > 0
        assert findings[0].rule == "secret_key_name"

    def test_placeholder_skipped(self) -> None:
        findings = detect_secrets("API_KEY", "changeme", 1)
        assert len(findings) == 0

    def test_empty_value_skipped(self) -> None:
        findings = detect_secrets("SECRET_KEY", "", 1)
        assert len(findings) == 0

    def test_aws_key_detected(self) -> None:
        findings = detect_secrets("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE1", 1)
        aws_findings = [f for f in findings if f.rule == "aws_key"]
        assert len(aws_findings) > 0
        assert aws_findings[0].severity == "critical"

    def test_github_token_detected(self) -> None:
        findings = detect_secrets("GITHUB_TOKEN", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", 1)
        gh_findings = [f for f in findings if f.rule == "github_token"]
        assert len(gh_findings) > 0
        assert gh_findings[0].severity == "critical"

    def test_url_with_credentials(self) -> None:
        findings = detect_secrets("DATABASE_URL", "https://user:pass@host/db", 1)
        url_findings = [f for f in findings if f.rule == "url_with_creds"]
        assert len(url_findings) > 0

    def test_short_non_secret(self) -> None:
        findings = detect_secrets("PORT", "5432", 1)
        assert len(findings) == 0
