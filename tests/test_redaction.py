"""Tests for tracea.server.redaction."""

import pytest
from tracea.server.redaction import redact, redact_dict, DEFAULT_PATTERNS


class TestRedact:
    """Test the core redact() function."""

    def test_no_secrets_unchanged(self):
        text = "This is a normal log message with no secrets."
        assert redact(text) == text

    def test_openai_api_key(self):
        text = "The API key is sk-abc123def456ghi789jkl012mno345pqr"
        result = redact(text)
        assert "sk-abc123" not in result
        assert "***REDACTED_API_KEY***" in result

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact(text)
        assert "eyJhbGci" not in result
        assert "Bearer ***REDACTED_TOKEN***" in result

    def test_json_api_key(self):
        text = '{"api_key": "super_secret_key_12345", "name": "test"}'
        result = redact(text)
        assert "super_secret_key" not in result
        assert '"api_key": "***REDACTED***"' in result

    def test_python_dict_api_key(self):
        text = "{'token': 'my_secret_token_value', 'other': 'ok'}"
        result = redact(text)
        assert "my_secret_token_value" not in result
        assert "'token': '***REDACTED***'" in result

    def test_env_var_assignment(self):
        text = "export OPENAI_API_KEY=sk-live-abc123def456"
        result = redact(text)
        assert "sk-live-abc123" not in result
        assert "OPENAI_API_KEY=***REDACTED***" in result

    def test_connection_string(self):
        text = "postgresql://admin:secretpass@localhost:5432/mydb"
        result = redact(text)
        assert "secretpass" not in result
        assert "postgresql://***REDACTED***@localhost:5432/mydb" in result

    def test_aws_key(self):
        text = "Access key: AKIAIOSFODNN7EXAMPLE"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "***REDACTED_AWS_KEY***" in result

    def test_github_token(self):
        text = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        result = redact(text)
        assert "ghp_xxx" not in result
        assert "***REDACTED_GH_TOKEN***" in result

    def test_private_key_block(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        result = redact(text)
        assert "-----BEGIN RSA PRIVATE KEY-----" not in result
        assert "-----BEGIN REDACTED PRIVATE KEY-----" in result

    def test_multiple_secrets(self):
        text = (
            "api_key=sk-abc123def456ghi789jkl012\n"
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n"
            '\"password\": \"mypassword123\"'
        )
        result = redact(text)
        assert "sk-abc123" not in result
        assert "eyJhbGci" not in result
        assert "mypassword123" not in result

    def test_empty_string(self):
        assert redact("") == ""

    def test_none_returns_none(self):
        assert redact(None) is None  # type: ignore[arg-type]


class TestRedactDict:
    """Test recursive dict redaction."""

    def test_flat_dict(self):
        data = {"api_key": "sk-abc123def456ghi789jkl012", "name": "test"}
        result = redact_dict(data)
        assert "sk-abc123" not in result["api_key"]
        assert "***REDACTED" in result["api_key"]
        assert result["name"] == "test"

    def test_nested_dict(self):
        data = {
            "config": {
                "token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "port": 8080,
            },
            "public": "ok",
        }
        result = redact_dict(data)
        assert "eyJhbGci" not in result["config"]["token"]
        assert "***REDACTED" in result["config"]["token"]
        assert result["config"]["port"] == 8080
        assert result["public"] == "ok"

    def test_list_of_strings(self):
        data = {"items": ["Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "normal"]}
        result = redact_dict(data)
        assert "eyJhbGci" not in result["items"][0]
        assert result["items"][1] == "normal"

    def test_list_of_dicts(self):
        data = {"events": [{"api_key": "sk-abc123def456ghi789jkl012"}, {"name": "ok"}]}
        result = redact_dict(data)
        assert "sk-abc123" not in result["events"][0]["api_key"]
        assert "***REDACTED" in result["events"][0]["api_key"]
        assert result["events"][1]["name"] == "ok"

    def test_non_dict_input(self):
        assert redact_dict("not a dict") == "not a dict"  # type: ignore[arg-type]


class TestDefaultPatterns:
    """Sanity checks on the default pattern list."""

    def test_patterns_are_compiled(self):
        for pattern, repl in DEFAULT_PATTERNS:
            assert hasattr(pattern, "sub")
            assert isinstance(repl, str)
