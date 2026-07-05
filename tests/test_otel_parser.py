import pytest
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as trace_pb
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as logs_pb
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as metrics_pb
from opentelemetry.proto.common.v1 import common_pb2 as common_pb

from tracea.server.otel.parser import parse_traces, parse_logs, parse_metrics


def test_parse_traces_proto():
    req = trace_pb.ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    
    # resource attributes
    kv = rs.resource.attributes.add()
    kv.key = "service.name"
    kv.value.string_value = "my-service"
    
    ss = rs.scope_spans.add()
    ss.scope.name = "my-scope"
    
    span = ss.spans.add()
    span.trace_id = bytes.fromhex("abcdef0123456789abcdef0123456789")
    span.span_id = bytes.fromhex("1234567890abcdef")
    span.parent_span_id = bytes.fromhex("0987654321fedcba")
    span.name = "test-span"
    span.kind = 1
    span.start_time_unix_nano = 1000
    span.end_time_unix_nano = 2000
    
    # span attributes
    span_kv = span.attributes.add()
    span_kv.key = "http.status_code"
    span_kv.value.int_value = 200
    
    body = req.SerializeToString()
    spans = parse_traces(body, "application/x-protobuf")
    
    assert len(spans) == 1
    assert spans[0]["trace_id"] == "abcdef0123456789abcdef0123456789"
    assert spans[0]["span_id"] == "1234567890abcdef"
    assert spans[0]["parent_span_id"] == "0987654321fedcba"
    assert spans[0]["name"] == "test-span"
    assert spans[0]["kind"] == 1
    assert spans[0]["start_time_unix_nano"] == 1000
    assert spans[0]["end_time_unix_nano"] == 2000
    assert spans[0]["resource_attrs"] == {"service.name": "my-service"}
    assert spans[0]["scope_name"] == "my-scope"
    assert spans[0]["span_attrs"] == {"http.status_code": 200}


def test_parse_traces_json():
    # Test JSON structure containing hex IDs
    body = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "my-service"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "my-scope"},
                        "spans": [
                            {
                                "traceId": "abcdef0123456789abcdef0123456789",
                                "spanId": "1234567890abcdef",
                                "parentSpanId": "0987654321fedcba",
                                "name": "test-span",
                                "kind": 1,
                                "startTimeUnixNano": 1000,
                                "endTimeUnixNano": 2000,
                                "attributes": [
                                    {"key": "http.status_code", "value": {"intValue": 200}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    spans = parse_traces(body, "application/json")
    
    assert len(spans) == 1
    assert spans[0]["trace_id"] == "abcdef0123456789abcdef0123456789"
    assert spans[0]["span_id"] == "1234567890abcdef"
    assert spans[0]["parent_span_id"] == "0987654321fedcba"
    assert spans[0]["name"] == "test-span"
    assert spans[0]["kind"] == 1
    assert spans[0]["start_time_unix_nano"] == 1000
    assert spans[0]["end_time_unix_nano"] == 2000
    assert spans[0]["resource_attrs"] == {"service.name": "my-service"}
    assert spans[0]["scope_name"] == "my-scope"
    assert spans[0]["span_attrs"] == {"http.status_code": 200}


def test_parse_logs_proto():
    req = logs_pb.ExportLogsServiceRequest()
    rl = req.resource_logs.add()
    
    # resource attributes
    kv = rl.resource.attributes.add()
    kv.key = "service.name"
    kv.value.string_value = "my-service"
    
    sl = rl.scope_logs.add()
    sl.scope.name = "my-scope"
    
    rec = sl.log_records.add()
    rec.trace_id = bytes.fromhex("abcdef0123456789abcdef0123456789")
    rec.span_id = bytes.fromhex("1234567890abcdef")
    rec.time_unix_nano = 5000
    rec.severity_number = 9 # INFO
    rec.severity_text = "INFORMATION"
    rec.body.string_value = "hello log"
    
    log_kv = rec.attributes.add()
    log_kv.key = "log.type"
    log_kv.value.string_value = "stdout"
    
    body = req.SerializeToString()
    logs = parse_logs(body, "application/x-protobuf")
    
    assert len(logs) == 1
    assert logs[0]["trace_id"] == "abcdef0123456789abcdef0123456789"
    assert logs[0]["span_id"] == "1234567890abcdef"
    assert logs[0]["timestamp_unix_nano"] == 5000
    assert logs[0]["severity"] == "INFORMATION"
    assert logs[0]["body"] == "hello log"
    assert logs[0]["resource_attrs"] == {"service.name": "my-service"}
    assert logs[0]["scope_name"] == "my-scope"
    assert logs[0]["log_attrs"] == {"log.type": "stdout"}


def test_parse_logs_json():
    body = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "my-service"}}
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "my-scope"},
                        "logRecords": [
                            {
                                "traceId": "abcdef0123456789abcdef0123456789",
                                "spanId": "1234567890abcdef",
                                "timeUnixNano": 5000,
                                "severityNumber": 9,
                                "severityText": "INFORMATION",
                                "body": {"stringValue": "hello log"},
                                "attributes": [
                                    {"key": "log.type", "value": {"stringValue": "stdout"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    logs = parse_logs(body, "application/json")
    
    assert len(logs) == 1
    assert logs[0]["trace_id"] == "abcdef0123456789abcdef0123456789"
    assert logs[0]["span_id"] == "1234567890abcdef"
    assert logs[0]["timestamp_unix_nano"] == 5000
    assert logs[0]["severity"] == "INFORMATION"
    assert logs[0]["body"] == "hello log"
    assert logs[0]["resource_attrs"] == {"service.name": "my-service"}
    assert logs[0]["scope_name"] == "my-scope"
    assert logs[0]["log_attrs"] == {"log.type": "stdout"}


def test_parse_metrics_proto():
    req = metrics_pb.ExportMetricsServiceRequest()
    rm = req.resource_metrics.add()
    rm.resource.attributes.add(key="env", value=common_pb.AnyValue(string_value="prod"))
    
    sm = rm.scope_metrics.add()
    
    # 1. Gauge
    m_gauge = sm.metrics.add()
    m_gauge.name = "my_gauge"
    dp_gauge = m_gauge.gauge.data_points.add()
    dp_gauge.as_double = 1.23
    dp_gauge.time_unix_nano = 10000
    dp_gauge.attributes.add(key="unit", value=common_pb.AnyValue(string_value="seconds"))
    
    # 2. Sum
    m_sum = sm.metrics.add()
    m_sum.name = "my_sum"
    dp_sum = m_sum.sum.data_points.add()
    dp_sum.as_int = 42
    dp_sum.time_unix_nano = 20000
    
    # 3. Histogram (v1 flattens to sum)
    m_hist = sm.metrics.add()
    m_hist.name = "my_hist"
    dp_hist = m_hist.histogram.data_points.add()
    dp_hist.sum = 99.5
    dp_hist.time_unix_nano = 30000
    
    body = req.SerializeToString()
    metrics = parse_metrics(body, "application/x-protobuf")
    
    assert len(metrics) == 3
    
    # Check gauge
    gauge_m = next(m for m in metrics if m["name"] == "my_gauge")
    assert gauge_m["value"] == 1.23
    assert gauge_m["timestamp_unix_nano"] == 10000
    assert gauge_m["attributes"] == {"unit": "seconds"}
    assert gauge_m["resource_attrs"] == {"env": "prod"}
    
    # Check sum
    sum_m = next(m for m in metrics if m["name"] == "my_sum")
    assert sum_m["value"] == 42
    assert sum_m["timestamp_unix_nano"] == 20000
    
    # Check histogram
    hist_m = next(m for m in metrics if m["name"] == "my_hist")
    assert hist_m["value"] == 99.5
    assert hist_m["timestamp_unix_nano"] == 30000
