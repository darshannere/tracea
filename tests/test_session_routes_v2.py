import json
import pytest
from fastapi.testclient import TestClient
from tracea.server.main import app
from tracea.server.db import get_db

@pytest.mark.asyncio
async def test_session_spans_and_metrics_routes(fresh_db):
    client = TestClient(app)
    db = get_db()

    # 1. Insert dummy data for spans
    await db.execute("""
        INSERT INTO spans (trace_id, span_id, parent_span_id, session_id, name, kind, start_time, end_time, attributes)
        VALUES ('t1', 's_root', '', 'sess_test', 'root_span', '1', '2024-01-01T00:00:00Z', '2024-01-01T00:00:05Z', '{}')
    """)
    await db.execute("""
        INSERT INTO spans (trace_id, span_id, parent_span_id, session_id, name, kind, start_time, end_time, attributes)
        VALUES ('t1', 's_child', 's_root', 'sess_test', 'child_span', '3', '2024-01-01T00:00:01Z', '2024-01-01T00:00:04Z', '{}')
    """)

    # 2. Insert dummy data for metrics
    await db.execute("""
        INSERT INTO metrics (metric_id, session_id, name, value, attributes, timestamp)
        VALUES ('m1', 'sess_test', 'claude_code.cost.usage', 0.05, '{}', '2024-01-01T00:00:02Z')
    """)
    await db.commit()

    # Get spans tree
    resp_spans = client.get("/api/v1/sessions/sess_test/spans")
    assert resp_spans.status_code == 200
    data_spans = resp_spans.json()
    assert data_spans["flat_count"] == 2
    assert len(data_spans["spans"]) == 1
    assert data_spans["spans"][0]["span_id"] == "s_root"
    assert len(data_spans["spans"][0]["children"]) == 1
    assert data_spans["spans"][0]["children"][0]["span_id"] == "s_child"

    # Get metrics grouped by name
    resp_metrics = client.get("/api/v1/sessions/sess_test/metrics")
    assert resp_metrics.status_code == 200
    data_metrics = resp_metrics.json()
    assert data_metrics["total_points"] == 1
    assert "claude_code.cost.usage" in data_metrics["metrics"]
    assert data_metrics["metrics"]["claude_code.cost.usage"][0]["value"] == 0.05
