import pytest
import os
import hashlib
import asyncio
from fastapi.testclient import TestClient
from tracea.server.main import app
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as trace_pb
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as logs_pb
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as metrics_pb


@pytest.fixture
def client():
    return TestClient(app)


class TestOtlpRoutesDisabledAuth:
    """Tests the OTLP/HTTP endpoints when authentication is disabled."""

    @pytest.fixture(autouse=True)
    def disable_auth(self, monkeypatch):
        monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")
        monkeypatch.delenv("TRACEA_DEV_MODE", raising=False)

    def test_empty_json_traces(self, client):
        resp = client.post("/v1/traces", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        assert resp.json() == {}

    def test_empty_json_logs(self, client):
        resp = client.post("/v1/logs", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        assert resp.json() == {}

    def test_empty_json_metrics(self, client):
        resp = client.post("/v1/metrics", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        assert resp.json() == {}

    def test_proto_traces(self, client):
        req = trace_pb.ExportTraceServiceRequest()
        body = req.SerializeToString()
        resp = client.post(
            "/v1/traces",
            content=body,
            headers={"Content-Type": "application/x-protobuf"}
        )
        assert resp.status_code == 200
        assert "protobuf" in resp.headers.get("content-type", "")
        # Verify it parses correctly into empty ExportTraceServiceResponse
        resp_pb = trace_pb.ExportTraceServiceResponse()
        resp_pb.ParseFromString(resp.content)

    def test_proto_logs(self, client):
        req = logs_pb.ExportLogsServiceRequest()
        body = req.SerializeToString()
        resp = client.post(
            "/v1/logs",
            content=body,
            headers={"Content-Type": "application/x-protobuf"}
        )
        assert resp.status_code == 200
        assert "protobuf" in resp.headers.get("content-type", "")
        resp_pb = logs_pb.ExportLogsServiceResponse()
        resp_pb.ParseFromString(resp.content)

    def test_proto_metrics(self, client):
        req = metrics_pb.ExportMetricsServiceRequest()
        body = req.SerializeToString()
        resp = client.post(
            "/v1/metrics",
            content=body,
            headers={"Content-Type": "application/x-protobuf"}
        )
        assert resp.status_code == 200
        assert "protobuf" in resp.headers.get("content-type", "")
        resp_pb = metrics_pb.ExportMetricsServiceResponse()
        resp_pb.ParseFromString(resp.content)


class TestOtlpRoutesApiKeyAuth:
    """Tests the OTLP/HTTP endpoints when API key authentication is enabled."""

    @pytest.fixture(autouse=True)
    def enable_api_key_mode(self, monkeypatch):
        monkeypatch.setenv("TRACEA_AUTH_MODE", "api_key")
        monkeypatch.delenv("TRACEA_DEV_MODE", raising=False)
        yield
        monkeypatch.setenv("TRACEA_AUTH_MODE", "disabled")

    @pytest.fixture
    def setup_user_and_key(self):
        async def _setup():
            from tracea.server.db import get_db
            db = get_db()
            await db.execute("DELETE FROM users WHERE user_id = ?", ("otlp-user",))
            await db.execute("DELETE FROM api_keys WHERE user_id = ?", ("otlp-user",))
            await db.execute(
                "INSERT INTO users (user_id, name, email) VALUES (?, ?, ?)",
                ("otlp-user", "OTLP User", "otlp@example.com"),
            )
            key_hash = hashlib.sha256(b"otlp-secret-key").hexdigest()
            await db.execute(
                "INSERT INTO api_keys (key_hash, user_id, name) VALUES (?, ?, ?)",
                (key_hash, "otlp-user", "otlp key"),
            )
            await db.commit()
        asyncio.run(_setup())

    def test_missing_token_returns_401(self, client):
        resp = client.post("/v1/traces", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.post(
            "/v1/traces",
            json={},
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer bad-otlp-key"
            }
        )
        assert resp.status_code == 401

    @pytest.mark.usefixtures("setup_user_and_key")
    def test_valid_token_succeeds(self, client):
        resp = client.post(
            "/v1/traces",
            json={},
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer otlp-secret-key"
            }
        )
        assert resp.status_code == 200

    def test_dev_mode_bypass(self, client, monkeypatch):
        monkeypatch.setenv("TRACEA_DEV_MODE", "1")
        resp = client.post("/v1/traces", json={}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
