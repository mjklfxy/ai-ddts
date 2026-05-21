from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pathlib import Path

from application.pipeline import PipelineBatchDelivery
from application.task_service import TaskContext
from domain.supplier import MissingSupplierError
from application.supplier_mapping_store import SupplierMappingStore


@dataclass(frozen=True, slots=True)
class KingdeePurchaseLine:
    """One purchase request line submitted to Kingdee."""

    order_no: str
    delivery_order_no: str
    # === MODIFIED START ===
    # 原因：采购需求汇总需要保留 SKU 和供应商对照信息，便于金蝶侧生成采购申请。
    # 影响范围：金蝶采购申请行字段。
    sku_code: str
    supplier_name: str | None
    # === MODIFIED END ===
    goods_summary: str
    quantity: int
    group_id: str


@dataclass(frozen=True, slots=True)
class KingdeePurchaseRequest:
    """Purchase request payload submitted to Kingdee."""

    trace_id: str
    task_id: str
    task_name: str
    window_start: str
    window_end: str
    lines: tuple[KingdeePurchaseLine, ...]


@dataclass(frozen=True, slots=True)
class KingdeeSubmitResult:
    """Result returned by Kingdee purchase request submission."""

    tracking_id: str


KingdeeTransport = Callable[[KingdeePurchaseRequest], KingdeeSubmitResult]


# === MODIFIED START ===
# 原因：金蝶采购申请需要预留真实 HTTP 提交通道。
# 影响范围：金蝶基础设施适配层。
class KingdeeHttpTransport:
    """Posts purchase request payloads to a configured Kingdee HTTP endpoint."""

    def __init__(
        self,
        api_url: str,
        token: str | None = None,
        timeout_seconds: float = 30,
        tracking_id_fields: tuple[str, ...] = ("tracking_id", "trackingId", "id"),
        extra_headers: dict[str, str] | None = None,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("api_url must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if not tracking_id_fields:
            raise ValueError("tracking_id_fields must not be empty")

        self.api_url = api_url.strip()
        self.token = token.strip() if isinstance(token, str) and token.strip() else None
        self.timeout_seconds = timeout_seconds
        self.tracking_id_fields = tracking_id_fields
        self.extra_headers = dict(extra_headers or {})
        self.urlopen = urlopen or urllib.request.urlopen

    def __call__(self, request: KingdeePurchaseRequest) -> KingdeeSubmitResult:
        """Sends one purchase request and returns a Kingdee tracking id."""

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            **self.extra_headers,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        http_request = urllib.request.Request(
            self.api_url,
            data=json.dumps(
                purchase_request_to_dict(request),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            response = self.urlopen(http_request, timeout=self.timeout_seconds)
            try:
                raw_body = response.read()
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except urllib.error.URLError as exc:
            raise ValueError(
                f"Kingdee request failed: {exc.__class__.__name__}"
            ) from exc

        payload = _decode_response(raw_body)
        _raise_for_kingdee_error(payload)
        return KingdeeSubmitResult(
            tracking_id=_tracking_id_from_payload(payload, self.tracking_id_fields)
        )


# === MODIFIED END ===


class KingdeeService:
    """Submits purchase request summaries to Kingdee."""

    def __init__(
        self,
        transport: KingdeeTransport,
        supplier_mapping_path: Path | str = Path("outputs")
        / "sku_supplier_mappings.json",
    ) -> None:
        self.transport = transport
        self.supplier_mapping_path = Path(supplier_mapping_path)

    def submit_purchase_request(
        self,
        task_context: TaskContext,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> str:
        request = self.build_purchase_request(
            task_context=task_context,
            deliveries=deliveries,
        )
        result = self.transport(request)
        return result.tracking_id

    def build_purchase_request(
        self,
        task_context: TaskContext,
        deliveries: tuple[PipelineBatchDelivery, ...],
    ) -> KingdeePurchaseRequest:
        lines: list[KingdeePurchaseLine] = []
        missing_skus: list[str] = []

        supplier_map = SupplierMappingStore(self.supplier_mapping_path).load_map()

        for delivery in deliveries:
            for order_line in delivery.batch.order_lines:
                sku_code = order_line.sku_code.strip()
                supplier = supplier_map.get(sku_code)
                if supplier is None:
                    missing_skus.append(sku_code)
                    continue
                lines.append(
                    KingdeePurchaseLine(
                        order_no=order_line.order_no,
                        delivery_order_no=order_line.delivery_order_no,
                        sku_code=order_line.sku_code,
                        supplier_name=supplier.supplier_name,
                        goods_summary=order_line.goods_summary,
                        quantity=order_line.quantity,
                        group_id=delivery.batch.group_name,
                    )
                )
                # === MODIFIED END ===

        # === MODIFIED START ===
        # 原因：缺供应商属于金蝶资料异常，外部群已推送后在金蝶阶段失败并返回明确原因。
        # 影响范围：金蝶采购申请提交。
        if missing_skus:
            raise MissingSupplierError(tuple(missing_skus))
        # === MODIFIED END ===

        return KingdeePurchaseRequest(
            trace_id=task_context.trace_id,
            task_id=task_context.task_id,
            task_name=task_context.task_name,
            window_start=task_context.window_start.isoformat(),
            window_end=task_context.window_end.isoformat(),
            lines=tuple(lines),
        )


# === MODIFIED START ===
# 原因：HTTP transport 需要稳定、可测试的金蝶采购申请 JSON 结构。
# 影响范围：金蝶基础设施序列化。
def purchase_request_to_dict(request: KingdeePurchaseRequest) -> dict[str, object]:
    """Converts a Kingdee purchase request into JSON-compatible data."""

    return {
        "trace_id": request.trace_id,
        "task_id": request.task_id,
        "task_name": request.task_name,
        "window_start": request.window_start,
        "window_end": request.window_end,
        "lines": [
            {
                "order_no": line.order_no,
                "delivery_order_no": line.delivery_order_no,
                "sku_code": line.sku_code,
                "supplier_name": line.supplier_name,
                "goods_summary": line.goods_summary,
                "quantity": line.quantity,
                "group_id": line.group_id,
            }
            for line in request.lines
        ],
    }


def _decode_response(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Kingdee response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kingdee response must be a JSON object")
    return payload


def _raise_for_kingdee_error(payload: dict[str, Any]) -> None:
    success = payload.get("success")
    if success is False:
        raise ValueError(f"Kingdee API returned error: {_safe_error_message(payload)}")

    code = payload.get("code")
    if code is None:
        code = payload.get("errCode")
    if code is None:
        return

    normalized_code = str(code).strip().lower()
    if normalized_code not in {"0", "200", "success", "true"}:
        raise ValueError(f"Kingdee API returned error: {_safe_error_message(payload)}")


def _tracking_id_from_payload(
    payload: dict[str, Any], tracking_id_fields: tuple[str, ...]
) -> str:
    for field_name in tracking_id_fields:
        value = _deep_get(payload, field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    raise ValueError("Kingdee response does not contain a tracking id")


def _deep_get(payload: dict[str, Any], field_name: str) -> Any:
    for container in (
        payload,
        _nested_dict(payload, "data"),
        _nested_dict(payload, "result"),
    ):
        if container is not None and field_name in container:
            return container[field_name]
    return None


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return None


def _safe_error_message(payload: dict[str, Any]) -> str:
    for key in ("message", "msg", "errorMsg"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    code = payload.get("code") or payload.get("errCode") or "unknown"
    return f"code={code}"


# === MODIFIED END ===
