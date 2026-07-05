from __future__ import annotations
import json
import base64
from typing import Any

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as trace_pb
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as logs_pb
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as metrics_pb
from opentelemetry.proto.common.v1 import common_pb2
from google.protobuf.json_format import ParseDict
from google.protobuf.json_format import MessageToDict


def _is_proto(content_type: str) -> bool:
    return "protobuf" in (content_type or "").lower()


def _attrs_to_dict(kvs) -> dict:
    """Convert a repeated KeyValue (proto) or list-of-dicts (already-decoded JSON) to a flat dict."""
    out: dict[str, Any] = {}
    if kvs is None:
        return out
    for kv in kvs:
        # proto path: kv has .key and .value (AnyValue)
        if hasattr(kv, "key"):
            out[kv.key] = _anyvalue_to_python(kv.value)
        # dict path (from MessageToDict, camelCase keys: "key", "value")
        elif isinstance(kv, dict):
            out[kv.get("key", "")] = _anyvalue_to_python(kv.get("value", {}))
    return out


def _anyvalue_to_python(av: Any) -> Any:
    """Convert an OTel AnyValue (proto or decoded-dict) to a Python native."""
    # proto path: AnyValue message with oneof
    if hasattr(av, "WhichOneof"):
        kind = av.WhichOneof("value")
        if kind == "string_value":
            return av.string_value
        if kind == "bool_value":
            return av.bool_value
        if kind == "int_value":
            return av.int_value
        if kind == "double_value":
            return av.double_value
        if kind == "bytes_value":
            return av.bytes_value.hex()
        if kind == "array_value":
            return [_anyvalue_to_python(v) for v in av.array_value.values]
        if kind == "kvlist_value":
            return _attrs_to_dict(av.kvlist_value.values)
        return None
    # dict path (decoded JSON): {"stringValue": "..."}, {"intValue": "..."}, etc.
    if isinstance(av, dict):
        if "stringValue" in av:
            return av["stringValue"]
        if "boolValue" in av:
            return av["boolValue"]
        if "intValue" in av:
            return int(av["intValue"])
        if "doubleValue" in av:
            return float(av["doubleValue"])
        if "bytesValue" in av:
            return av["bytesValue"]
        if "arrayValue" in av:
            return [_anyvalue_to_python(v) for v in av["arrayValue"].get("values", [])]
        if "kvlistValue" in av:
            return _attrs_to_dict(av["kvlistValue"].get("values", []))
    return None


def _bytes_to_hex(b) -> str:
    """Bytes (proto) → hex string. Already-string (JSON base64) → return as-is."""
    if isinstance(b, (bytes, bytearray)):
        return b.hex()
    return b or ""


# ---------- traces ----------

def parse_traces(body: bytes | str | dict, content_type: str) -> list[dict]:
    req = trace_pb.ExportTraceServiceRequest()
    _populate(req, body, content_type)
    spans: list[dict] = []
    for rs in req.resource_spans:
        resource_attrs = _attrs_to_dict(rs.resource.attributes)
        for ss in rs.scope_spans:
            scope_name = ss.scope.name if ss.scope else ""
            for span in ss.spans:
                spans.append({
                    "trace_id": _bytes_to_hex(span.trace_id),
                    "span_id": _bytes_to_hex(span.span_id),
                    "parent_span_id": _bytes_to_hex(span.parent_span_id),
                    "name": span.name,
                    "kind": span.kind,
                    "start_time_unix_nano": span.start_time_unix_nano,
                    "end_time_unix_nano": span.end_time_unix_nano,
                    "resource_attrs": resource_attrs,
                    "scope_name": scope_name,
                    "span_attrs": _attrs_to_dict(span.attributes),
                })
    return spans


# ---------- logs ----------

def parse_logs(body: bytes | str | dict, content_type: str) -> list[dict]:
    req = logs_pb.ExportLogsServiceRequest()
    _populate(req, body, content_type)
    logs: list[dict] = []
    for rl in req.resource_logs:
        resource_attrs = _attrs_to_dict(rl.resource.attributes)
        for sl in rl.scope_logs:
            scope_name = sl.scope.name if sl.scope else ""
            for rec in sl.log_records:
                logs.append({
                    "trace_id": _bytes_to_hex(rec.trace_id) if rec.trace_id else None,
                    "span_id": _bytes_to_hex(rec.span_id) if rec.span_id else None,
                    "timestamp_unix_nano": rec.time_unix_nano,
                    "severity": rec.severity_text or _severity_name(rec.severity_number),
                    "body": _anyvalue_to_python(rec.body),
                    "resource_attrs": resource_attrs,
                    "scope_name": scope_name,
                    "log_attrs": _attrs_to_dict(rec.attributes),
                })
    return logs


# ---------- metrics ----------

def parse_metrics(body: bytes | str | dict, content_type: str) -> list[dict]:
    req = metrics_pb.ExportMetricsServiceRequest()
    _populate(req, body, content_type)
    out: list[dict] = []
    for rm in req.resource_metrics:
        resource_attrs = _attrs_to_dict(rm.resource.attributes)
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                name = metric.name
                data_kind = metric.WhichOneof("data")
                if data_kind == "gauge":
                    for dp in metric.gauge.data_points:
                        out.append(_metric_dp(name, dp, resource_attrs, "gauge"))
                elif data_kind == "sum":
                    for dp in metric.sum.data_points:
                        out.append(_metric_dp(name, dp, resource_attrs, "sum"))
                elif data_kind == "histogram":
                    for dp in metric.histogram.data_points:
                        out.append({
                            "name": name,
                            "value": dp.sum,
                            "attributes": _attrs_to_dict(dp.attributes),
                            "timestamp_unix_nano": dp.time_unix_nano,
                            "resource_attrs": resource_attrs,
                        })
    return out


def _metric_dp(name, dp, resource_attrs, kind):
    val = dp.as_double if dp.HasField("as_double") else dp.as_int
    return {
        "name": name,
        "value": val,
        "attributes": _attrs_to_dict(dp.attributes),
        "timestamp_unix_nano": dp.time_unix_nano,
        "resource_attrs": resource_attrs,
    }


# ---------- helpers ----------

_SEVERITY_NAMES = {
    0: "UNSPECIFIED", 1: "TRACE", 5: "DEBUG", 9: "INFO",
    13: "WARN", 17: "ERROR", 21: "FATAL",
}


def _severity_name(n: int) -> str:
    return _SEVERITY_NAMES.get(n, str(n))


def _populate(req_msg, body, content_type: str) -> None:
    """Decode body into the passed-in proto message based on Content-Type."""
    if _is_proto(content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        req_msg.ParseFromString(body)
    else:
        # JSON path
        if isinstance(body, (bytes, bytearray)):
            body = json.loads(body.decode("utf-8"))
        elif isinstance(body, str):
            body = json.loads(body)
        _hex_ids_to_base64(body)
        ParseDict(body, req_msg, ignore_unknown_fields=True)


_ID_KEYS = {"traceId", "spanId", "parentSpanId"}


def _hex_ids_to_base64(node: Any) -> None:
    """OTLP/JSON deviates from proto3 JSON mapping: trace/span IDs are HEX
    strings on the wire, but ParseDict expects base64 for bytes fields.
    Re-encode them in place before ParseDict."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _ID_KEYS and isinstance(v, str) and v:
                try:
                    node[k] = base64.b64encode(bytes.fromhex(v)).decode()
                except ValueError:
                    pass
            else:
                _hex_ids_to_base64(v)
    elif isinstance(node, list):
        for item in node:
            _hex_ids_to_base64(item)
