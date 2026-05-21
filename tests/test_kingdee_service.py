import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from application.file_generator import GeneratedFile
from application.order_splitter import GroupOrderBatch
from application.pipeline import PipelineBatchDelivery
from application.task_service import TaskService
from domain.supplier import MissingSupplierError, SupplierInfo
from infrastructure.kingdee_service import (
    KingdeeHttpTransport,
    KingdeePurchaseRequest,
    KingdeeService,
    KingdeeSubmitResult,
    purchase_request_to_dict,
)
from infrastructure.message_adapter import MessageSendResult
from tests.test_order_splitter import make_order_line


class KingdeeServiceTests(TestCase):
    """Tests Kingdee purchase request payload construction and submission."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _supplier_mapping_path(self, sku_supplier_map: dict[str, SupplierInfo]) -> str:
        """Writes supplier mappings to a temp JSON file and returns the path."""
        path = Path(self.tmpdir) / "suppliers.json"
        path.write_text(
            json.dumps(
                {
                    "items": [
                        {"sku_code": info.sku_code, "supplier_name": info.supplier_name}
                        for info in sku_supplier_map.values()
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return str(path)

    def test_build_purchase_request_from_deliveries(self) -> None:
        task = make_task()
        service = KingdeeService(
            transport=lambda request: KingdeeSubmitResult("KD-001"),
            supplier_mapping_path=self._supplier_mapping_path({"SKU-001": make_supplier()}),
        )

        request = service.build_purchase_request(
            task_context=task,
            deliveries=(make_delivery(group_name="GROUP-A", order_no="SO-001"),),
        )

        self.assertIsInstance(request, KingdeePurchaseRequest)
        self.assertEqual(request.trace_id, "TRACE-001")
        self.assertEqual(request.task_id, "TRACE-001")
        self.assertEqual(request.task_name, "daily-direct-order")
        self.assertEqual(request.window_start, "2026-04-30T08:00:00")
        self.assertEqual(request.window_end, "2026-04-30T12:00:00")
        self.assertEqual(len(request.lines), 1)
        self.assertEqual(request.lines[0].order_no, "SO-001")
        self.assertEqual(request.lines[0].delivery_order_no, "DO-SO-001")
        # === MODIFIED START ===
        # 原因：验证采购行附带 SKU 和供应商字段。
        # 影响范围：金蝶请求字段断言。
        self.assertEqual(request.lines[0].sku_code, "SKU-001")
        self.assertEqual(request.lines[0].supplier_name, "Supplier A")
        # === MODIFIED END ===
        self.assertEqual(request.lines[0].goods_summary, "Goods SKU-001")
        self.assertEqual(request.lines[0].quantity, 1)
        self.assertEqual(request.lines[0].group_id, "GROUP-A")

    def test_submit_purchase_request_returns_tracking_id(self) -> None:
        submitted_requests: list[KingdeePurchaseRequest] = []

        def transport(request: KingdeePurchaseRequest) -> KingdeeSubmitResult:
            submitted_requests.append(request)
            return KingdeeSubmitResult(tracking_id="KD-001")

        service = KingdeeService(
            transport=transport,
            supplier_mapping_path=self._supplier_mapping_path({"SKU-001": make_supplier()}),
        )

        tracking_id = service.submit_purchase_request(
            task_context=make_task(),
            deliveries=(make_delivery(group_name="GROUP-A", order_no="SO-001"),),
        )

        self.assertEqual(tracking_id, "KD-001")
        self.assertEqual(len(submitted_requests), 1)

    def test_empty_deliveries_build_empty_lines(self) -> None:
        service = KingdeeService(transport=lambda request: KingdeeSubmitResult("KD-001"))

        request = service.build_purchase_request(
            task_context=make_task(),
            deliveries=(),
        )

        self.assertEqual(request.lines, ())

    # === MODIFIED START ===
    # 原因：金蝶 HTTP transport 需要稳定序列化采购申请和提取追踪号。
    # 影响范围：金蝶 HTTP 提交通道。
    def test_purchase_request_to_dict_serializes_lines(self) -> None:
        service = KingdeeService(
            transport=lambda request: KingdeeSubmitResult("KD-001"),
            supplier_mapping_path=self._supplier_mapping_path({"SKU-001": make_supplier()}),
        )
        request = service.build_purchase_request(
            task_context=make_task(),
            deliveries=(make_delivery(group_name="GROUP-A", order_no="SO-001"),),
        )

        payload = purchase_request_to_dict(request)

        self.assertEqual(payload["trace_id"], "TRACE-001")
        self.assertEqual(payload["lines"][0]["supplier_name"], "Supplier A")
        self.assertNotIn("supplier_code", payload["lines"][0])
        self.assertEqual(payload["lines"][0]["quantity"], 1)

    def test_http_transport_posts_json_and_returns_tracking_id(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                json.dumps(
                    {
                        "code": "0",
                        "data": {
                            "billNo": "KD-BILL-001",
                        },
                    }
                ).encode("utf-8")
            )

        transport = KingdeeHttpTransport(
            api_url="https://kingdee.example.test/purchase",
            token="TOKEN-001",
            timeout_seconds=5,
            tracking_id_fields=("billNo",),
            extra_headers={"X-App": "direct-order"},
            urlopen=fake_urlopen,
        )

        result = transport(
            KingdeeService(
                transport=lambda request: KingdeeSubmitResult("KD-001"),
                supplier_mapping_path=self._supplier_mapping_path({"SKU-001": make_supplier()}),
            ).build_purchase_request(
                task_context=make_task(),
                deliveries=(make_delivery(group_name="GROUP-A", order_no="SO-001"),),
            )
        )

        self.assertEqual(result.tracking_id, "KD-BILL-001")
        self.assertEqual(captured["url"], "https://kingdee.example.test/purchase")
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer TOKEN-001")
        self.assertEqual(captured["headers"]["X-app"], "direct-order")
        self.assertEqual(captured["body"]["trace_id"], "TRACE-001")
        self.assertNotIn("TOKEN-001", json.dumps(captured["body"], ensure_ascii=False))

    def test_http_transport_rejects_error_response(self) -> None:
        def fake_urlopen(_request, timeout):
            _ = timeout
            return FakeResponse(json.dumps({"code": "500", "message": "failed"}).encode("utf-8"))

        transport = KingdeeHttpTransport(
            api_url="https://kingdee.example.test/purchase",
            urlopen=fake_urlopen,
        )

        with self.assertRaisesRegex(ValueError, "Kingdee API returned error"):
            transport(
                KingdeeService(transport=lambda request: KingdeeSubmitResult("KD-001")).build_purchase_request(
                    task_context=make_task(),
                    deliveries=(),
                )
            )
    # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：供应商缺失不再阻断外部群推送，但必须阻断金蝶采购申请提交。
    # 影响范围：金蝶采购申请资料校验。
    def test_missing_supplier_rejects_purchase_request_before_transport(self) -> None:
        submitted_requests: list[KingdeePurchaseRequest] = []

        def transport(request: KingdeePurchaseRequest) -> KingdeeSubmitResult:
            submitted_requests.append(request)
            return KingdeeSubmitResult(tracking_id="KD-001")

        service = KingdeeService(
            transport=transport,
            supplier_mapping_path=str(Path(self.tmpdir) / "empty_suppliers.json"),
            # File won't exist → load_map() returns {}
        )

        with self.assertRaisesRegex(MissingSupplierError, "未配置供应商") as context:
            service.submit_purchase_request(
                task_context=make_task(),
                deliveries=(make_delivery(group_name="GROUP-A", order_no="SO-001"),),
            )

        self.assertEqual(context.exception.missing_skus, ("SKU-001",))
        self.assertEqual(submitted_requests, [])
    # === MODIFIED END ===


def make_task():
    """Builds a deterministic task context for Kingdee tests."""

    return TaskService(
        trace_id_generator=lambda: "TRACE-001",
        clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
    ).create_task(
        task_name="daily-direct-order",
        window_start=datetime(2026, 4, 30, 8, 0, 0),
        window_end=datetime(2026, 4, 30, 12, 0, 0),
    )


def make_delivery(group_name: str, order_no: str) -> PipelineBatchDelivery:
    """Builds one successful delivery for Kingdee tests."""

    return PipelineBatchDelivery(
        batch=GroupOrderBatch(
            group_name=group_name,
            owner_mobile="",
            user_id="",
            order_lines=(make_order_line(order_no=order_no, sku_code="SKU-001"),),
        ),
        generated_file=GeneratedFile(
            group_name=group_name,
            file_path=Path("outputs") / f"{group_name}.csv",
            row_count=1,
        ),
        message_result=MessageSendResult(
            trace_id="TRACE-001",
            group_name=group_name,
            tracking_id=f"MSG-{group_name}",
            attempts=1,
        ),
    )


def make_supplier() -> SupplierInfo:
    """Builds one supplier mapping for Kingdee tests."""

    return SupplierInfo(
        sku_code="SKU-001",
        supplier_name="Supplier A",
    )


# === MODIFIED START ===
# 原因：KingdeeHttpTransport 测试需要一个最小 HTTP 响应对象。
# 影响范围：金蝶 HTTP transport 测试。
class FakeResponse:
    """Minimal urllib-like response used by Kingdee transport tests."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        """Returns the fake response body."""

        return self.body

    def close(self) -> None:
        """Closes the fake response."""

        return None
# === MODIFIED END ===
