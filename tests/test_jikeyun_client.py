import hashlib
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from unittest import TestCase

from infrastructure.jikeyun_client import (
    JIKEYUN_ORDER_QUERY_METHOD,
    JikeyunClient,
    JikeyunCredentials,
    # === MODIFIED START ===
    # 原因：覆盖真实吉客云 HTTP transport 的 form 组装和响应解析。
    # 影响范围：吉客云客户端测试。
    JikeyunHttpTransport,
    # === MODIFIED END ===
    JikeyunPageRequest,
    JikeyunPageResult,
)


class JikeyunClientTests(TestCase):
    """Tests JackYun request signing, pagination, and raw order mapping."""

    def test_build_page_request_uses_method_page_window_and_signature(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))

        request = client.build_page_request(
            page_no=2,
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        # === MODIFIED START ===
        # 原因：吉客云请求已改为公共参数 + bizcontent 形式签名。
        # 影响范围：签名断言。
        biz_content = {
            "pageIndex": 2,
            "pageSize": 2,
            "startModifyTime": "2026-04-30 08:00:00",
            "endModifyTime": "2026-04-30 12:00:00",
            "orderStatusList": [0, 1, 3, 4, 5, 6, 15],
        }
        sign_params = {
            "method": JIKEYUN_ORDER_QUERY_METHOD,
            "appkey": "APPKEY",
            "version": "v1.0",
            "contenttype": "JSON",
            "timestamp": "2026-04-30 12:00:00",
            "bizcontent": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        canonical = "".join(f"{key}{value}" for key, value in sorted(sign_params.items()))
        expected_sign = hashlib.md5(f"SECRET{canonical}SECRET".lower().encode("utf-8")).hexdigest()
        # === MODIFIED END ===

        self.assertIsInstance(request, JikeyunPageRequest)
        self.assertEqual(request.method, JIKEYUN_ORDER_QUERY_METHOD)
        self.assertEqual(request.app_key, "APPKEY")
        self.assertEqual(request.page_no, 2)
        self.assertEqual(request.page_size, 2)
        self.assertEqual(request.version, "v1.0")
        self.assertEqual(request.content_type, "JSON")
        self.assertEqual(request.biz_content, biz_content)
        self.assertEqual(request.sign, expected_sign)

    def test_fetch_orders_paginates_and_maps_pipeline_orders(self) -> None:
        requests: list[JikeyunPageRequest] = []

        def transport(request: JikeyunPageRequest) -> JikeyunPageResult:
            requests.append(request)
            if request.page_no == 0:
                return JikeyunPageResult(
                    items=(make_raw_order(order_no="SO-001", sku_code="SKU-001"),),
                    has_next=True,
                )
            return JikeyunPageResult(
                items=(make_raw_order(order_no="SO-002", sku_code="SKU-002"),),
                has_next=False,
            )

        client = make_client(transport=transport)

        orders = client.fetch_orders(
            trace_id="TRACE-001",
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual([request.page_no for request in requests], [0, 1])
        self.assertEqual([order.rule_context.order_no for order in orders], ["SO-001", "SO-002"])
        self.assertEqual([order.rule_context.trace_id for order in orders], ["TRACE-001", "TRACE-001"])
        self.assertEqual(orders[0].rule_context.sku_codes, ("SKU-001",))
        self.assertEqual(orders[0].order_lines[0].goods_summary, "Goods SKU-001")

    def test_fetch_orders_runs_injected_rpa_exporter_before_mapping(self) -> None:
        calls: list[tuple[str, Path, datetime, datetime]] = []

        def exporter(
            trace_id: str,
            xlsx_path: Path,
            start_time: datetime,
            end_time: datetime,
        ) -> None:
            calls.append((trace_id, xlsx_path, start_time, end_time))

        client = make_client(
            transport=lambda request: JikeyunPageResult(
                items=(make_raw_order(order_no="SO-RPA", sku_code="SKU-RPA"),),
                has_next=False,
            ),
            rpa_exporter=exporter,
        )

        orders = client.fetch_orders(
            trace_id="TRACE-RPA",
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual(
            calls,
            [
                (
                    "TRACE-RPA",
                    Path("tmp/test_jikeyun_missing.xlsx"),
                    datetime(2026, 4, 30, 8, 0, 0),
                    datetime(2026, 4, 30, 12, 0, 0),
                )
            ],
        )
        self.assertEqual([order.rule_context.order_no for order in orders], ["SO-RPA"])

    def test_fetch_orders_propagates_rpa_exporter_failure(self) -> None:
        errors: list[tuple[str, dict[str, object]]] = []

        def failing_exporter(
            trace_id: str,
            xlsx_path: Path,
            start_time: datetime,
            end_time: datetime,
        ) -> None:
            _ = (trace_id, xlsx_path, start_time, end_time)
            raise RuntimeError("desktop unavailable")

        client = make_client(
            transport=lambda request: JikeyunPageResult(
                items=(make_raw_order(order_no="SO-RPA-FAIL", sku_code="SKU-RPA"),),
                has_next=False,
            ),
            rpa_exporter=failing_exporter,
            log_error=lambda event, payload: errors.append((event, payload)),
        )

        with self.assertRaises(RuntimeError):
            client.fetch_orders(
                trace_id="TRACE-RPA",
                start_time=datetime(2026, 4, 30, 8, 0, 0),
                end_time=datetime(2026, 4, 30, 12, 0, 0),
            )

        self.assertEqual(errors[0][0], "jikeyun_rpa_export_failed")
        self.assertEqual(errors[0][1]["trace_id"], "TRACE-RPA")
        self.assertEqual(errors[0][1]["xlsx_path"], "tmp\\test_jikeyun_missing.xlsx")

    def test_fetch_orders_logs_rpa_export_lifecycle_and_xlsx_lookup_path(self) -> None:
        infos: list[tuple[str, dict[str, object]]] = []
        exporter_calls: list[tuple[str, Path, datetime, datetime]] = []

        def exporter(
            trace_id: str,
            xlsx_path: Path,
            start_time: datetime,
            end_time: datetime,
        ) -> None:
            exporter_calls.append((trace_id, xlsx_path, start_time, end_time))

        client = make_client(
            transport=lambda request: JikeyunPageResult(
                items=(make_raw_order(order_no="SO-RPA-LOG", sku_code="SKU-RPA"),),
                has_next=False,
            ),
            rpa_exporter=exporter,
            log_info=lambda event, payload: infos.append((event, payload)),
            xlsx_path="tmp/test_jikeyun_rpa_log.xlsx",
        )

        orders = client.fetch_orders(
            trace_id="TRACE-RPA-LOG",
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        self.assertEqual(
            exporter_calls,
            [
                (
                    "TRACE-RPA-LOG",
                    Path("tmp/test_jikeyun_rpa_log.xlsx"),
                    datetime(2026, 4, 30, 8, 0, 0),
                    datetime(2026, 4, 30, 12, 0, 0),
                )
            ],
        )
        self.assertEqual([order.rule_context.order_no for order in orders], ["SO-RPA-LOG"])
        self.assertEqual(
            [event for event, _ in infos],
            [
                "jikeyun_fetch_orders_start",
                "jikeyun_page_fetched",
                "jikeyun_rpa_export_start",
                "jikeyun_rpa_export_succeeded",
                "jikeyun_xlsx_lookup_loaded",
                "jikeyun_contact_fields_resolved",
                "jikeyun_fetch_orders_complete",
            ],
        )
        self.assertEqual(infos[2][1]["xlsx_path"], "tmp\\test_jikeyun_rpa_log.xlsx")
        self.assertEqual(infos[4][1]["record_count"], 0)
        self.assertEqual(infos[5][1]["receiver_name_source"], "api")
        self.assertEqual(infos[6][1]["raw_order_count"], 1)
        self.assertEqual(infos[6][1]["order_count"], 1)

    def test_fetch_orders_logs_rpa_export_skipped_when_not_configured(self) -> None:
        infos: list[tuple[str, dict[str, object]]] = []

        client = make_client(
            transport=lambda request: JikeyunPageResult(
                items=(make_raw_order(order_no="SO-RPA-SKIP", sku_code="SKU-RPA"),),
                has_next=False,
            ),
            log_info=lambda event, payload: infos.append((event, payload)),
        )

        client.fetch_orders(
            trace_id="TRACE-RPA-SKIP",
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        skipped_payload = next(
            payload for event, payload in infos if event == "jikeyun_rpa_export_skipped"
        )
        self.assertEqual(skipped_payload["trace_id"], "TRACE-RPA-SKIP")
        self.assertEqual(skipped_payload["xlsx_path"], "tmp\\test_jikeyun_missing.xlsx")
        self.assertEqual(skipped_payload["start_time"], "2026-04-30T08:00:00")
        self.assertEqual(skipped_payload["end_time"], "2026-04-30T12:00:00")

    def test_map_order_logs_contact_field_sources_from_xlsx(self) -> None:
        infos: list[tuple[str, dict[str, object]]] = []
        client = make_client(
            transport=lambda request: JikeyunPageResult(items=(), has_next=False),
            log_info=lambda event, payload: infos.append((event, payload)),
        )
        raw_order = {
            "orderNo": "JY-XLSX-001",
            "deliveryOrderNo": "S-XLSX-001",
            "goodsDetail": [{"goodsName": "Goods 001", "sellCount": 1}],
            "receiverName": "",
            "address": "",
            "phone": "",
        }

        order = client.map_order(
            raw_order=raw_order,
            trace_id="TRACE-SOURCE",
            xlsx_lookup={
                "JY-XLSX-001": make_xlsx_info(
                    receiver_name="Receiver XLSX",
                    address="Address XLSX",
                    phone="13900000000",
                )
            },
        )

        self.assertEqual(order.order_lines[0].receiver_name, "Receiver XLSX")
        self.assertEqual(
            infos[-1],
            (
                "jikeyun_contact_fields_resolved",
                {
                    "trace_id": "TRACE-SOURCE",
                    "order_no": "JY-XLSX-001",
                    "delivery_order_no": "S-XLSX-001",
                    "receiver_name_source": "xlsx",
                    "address_source": "xlsx",
                    "phone_source": "xlsx",
                },
            ),
        )

    def test_map_order_logs_contact_field_sources_from_default(self) -> None:
        infos: list[tuple[str, dict[str, object]]] = []
        client = make_client(
            transport=lambda request: JikeyunPageResult(items=(), has_next=False),
            log_info=lambda event, payload: infos.append((event, payload)),
        )
        raw_order = {
            "orderNo": "JY-DEFAULT-001",
            "deliveryOrderNo": "S-DEFAULT-001",
            "goodsDetail": [{"goodsName": "Goods 001", "sellCount": 1}],
            "receiverName": "",
            "address": "",
            "phone": "",
        }

        order = client.map_order(raw_order=raw_order, trace_id="TRACE-SOURCE")

        self.assertEqual(order.order_lines[0].receiver_name, "未提供")
        self.assertEqual(
            infos[-1],
            (
                "jikeyun_contact_fields_resolved",
                {
                    "trace_id": "TRACE-SOURCE",
                    "order_no": "JY-DEFAULT-001",
                    "delivery_order_no": "S-DEFAULT-001",
                    "receiver_name_source": "default",
                    "address_source": "default",
                    "phone_source": "default",
                },
            ),
        )

    def test_missing_required_field_is_rejected(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))
        raw_order = make_raw_order(order_no="SO-001", sku_code="SKU-001")
        raw_order["goods_summary"] = ""

        with self.assertRaisesRegex(ValueError, "goods_summary"):
            client.map_order(raw_order=raw_order, trace_id="TRACE-001")

    def test_invalid_page_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "page_size"):
            JikeyunClient(
                credentials=JikeyunCredentials(app_key="APPKEY", app_secret="SECRET"),
                transport=lambda request: JikeyunPageResult(items=(), has_next=False),
                page_size=0,
            )

    # === MODIFIED START ===
    # 原因：真实吉客云 transport 需要覆盖 form 参数和分页响应解析。
    # 影响范围：JikeyunHttpTransport。
    def test_http_transport_posts_form_and_parses_page_response(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = request.data.decode("utf-8")
            return FakeResponse(
                json.dumps(
                    {
                        "code": "0",
                        "data": {
                            "items": [make_raw_order(order_no="SO-001", sku_code="SKU-001")],
                            "hasNext": True,
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )

        transport = JikeyunHttpTransport(
            api_url="https://example.test/openapi",
            timeout_seconds=5,
            urlopen=fake_urlopen,
        )
        request = make_client(transport=lambda item: JikeyunPageResult(items=(), has_next=False)).build_page_request(
            page_no=1,
            start_time=datetime(2026, 4, 30, 8, 0, 0),
            end_time=datetime(2026, 4, 30, 12, 0, 0),
        )

        result = transport(request)

        form = urllib.parse.parse_qs(captured["body"])
        self.assertEqual(captured["url"], "https://example.test/openapi")
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(form["method"], [JIKEYUN_ORDER_QUERY_METHOD])
        self.assertEqual(form["appkey"], ["APPKEY"])
        self.assertEqual(form["version"], ["v1.0"])
        self.assertEqual(form["contenttype"], ["JSON"])
        self.assertIn("bizcontent", form)
        self.assertIn("sign", form)
        self.assertEqual(result.has_next, True)
        self.assertEqual(result.items[0]["order_no"], "SO-001")

    def test_map_order_supports_camel_case_and_multiple_goods_lines(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))
        raw_order = {
            "orderNo": "SO-CAMEL",
            "deliveryOrderNo": "DO-CAMEL",
            "warehouseCode": "WH-001",
            "warehouseName": "Warehouse",
            "receiverProvince": "浙江省",
            "receiverCity": "杭州市",
            "receiverDistrict": "西湖区",
            "receiverName": "Receiver",
            "receiverAddress": "Address",
            "receiverMobile": "13800000000",
            "logisticsCompany": "SF",
            "logisticsNo": "SF001",
            "goodsDetail": [
                {
                    "skuCode": "SKU-001",
                    "goodsName": "Goods 001",
                    "goodsCount": "2",
                },
                {
                    "skuCode": "SKU-002",
                    "goodsName": "Goods 002",
                    "goodsCount": 3,
                },
            ],
        }

        order = client.map_order(raw_order=raw_order, trace_id="TRACE-001")

        self.assertEqual(order.rule_context.order_no, "SO-CAMEL")
        # === MODIFIED START ===
        # 原因：规则里的 SKU 已明确为订单明细“商品名称”，不是 skuCode/goodsNo。
        # 影响范围：吉客云订单映射测试。
        self.assertEqual(order.rule_context.sku_codes, ("Goods 001", "Goods 002"))
        self.assertEqual(order.order_lines[0].sku_code, "Goods 001")
        # === MODIFIED END ===
        self.assertEqual(order.order_lines[0].delivery_order_no, "DO-CAMEL")
        self.assertEqual(order.order_lines[0].quantity, 2)
        self.assertEqual(order.order_lines[1].goods_summary, "Goods 002")

    def test_map_order_supports_real_jikeyun_delivery_fields(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))
        raw_order = {
            "orderNo": "S2026050510387",
            "erporderNo": "JY2026042926026-MULTI2809604",
            "warehouseName": "元昇堂店",
            "province": "广东省",
            "city": "深圳市",
            "district": "南山区",
            "receiverName": "张三",
            "address": "科技园",
            "mobile": "13800000000",
            "logisticName": "顺丰",
            "logisticNo": "SF001",
            "goodsDetail": [
                {
                    "goodsNo": "6921385588300",
                    "skuBarcode": "6921385588300",
                    "goodsName": "圣琪酵母粉/5g",
                    "sellCount": 20,
                }
            ],
        }

        order = client.map_order(raw_order=raw_order, trace_id="TRACE-001")

        self.assertEqual(order.rule_context.order_no, "JY2026042926026-MULTI2809604")
        self.assertEqual(order.rule_context.warehouse_name, "元昇堂店")
        self.assertEqual(order.rule_context.receiver_province, "广东省")
        # === MODIFIED START ===
        # 原因：真实吉客云订单的 SKU 配置口径改为 goodsName 商品名称。
        # 影响范围：真实吉客云字段映射测试。
        self.assertEqual(order.rule_context.sku_codes, ("圣琪酵母粉/5g",))
        self.assertEqual(order.order_lines[0].sku_code, "圣琪酵母粉/5g")
        self.assertEqual(order.order_lines[0].warehouse_name, "元昇堂店")
        # === MODIFIED END ===
        self.assertEqual(order.order_lines[0].order_no, "JY2026042926026-MULTI2809604")
        self.assertEqual(order.order_lines[0].delivery_order_no, "S2026050510387")
        self.assertEqual(order.order_lines[0].goods_summary, "圣琪酵母粉/5g")
        self.assertEqual(order.order_lines[0].quantity, 20)
        self.assertEqual(order.order_lines[0].logistics_company, "顺丰")

    def test_map_order_keeps_receiver_unprovided_when_real_receiver_fields_are_empty(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))
        raw_order = {
            "orderNo": "S2026050510387",
            "erporderNo": "JY2026042926026-MULTI2809604",
            "receiverName": None,
            "customerName": "元昇堂店",
            "address": None,
            "phone": None,
            "goodsDetail": [
                {
                    "goodsNo": "6921385588300",
                    "goodsName": "圣琪酵母粉/5g",
                    "sellCount": 20,
                }
            ],
        }

        order = client.map_order(raw_order=raw_order, trace_id="TRACE-001")

        # === MODIFIED START ===
        # 原因：customerName 表示门店/客户名称，不能兜底写入收件人字段。
        # 影响范围：吉客云订单映射到推送文件的收件人展示。
        self.assertEqual(order.order_lines[0].receiver_name, "未提供")
        # === MODIFIED END ===
        self.assertEqual(order.order_lines[0].address, "未提供")
        self.assertEqual(order.order_lines[0].phone, "未提供")

    def test_map_order_supports_chinese_warehouse_field(self) -> None:
        client = make_client(transport=lambda request: JikeyunPageResult(items=(), has_next=False))
        raw_order = {
            **make_raw_order(order_no="SO-001", sku_code="SKU-001"),
            "warehouse_name": "",
            "仓库": "华南仓",
            "goodsDetail": [
                {
                    "商品名称": "维生素C片",
                    "goodsCount": 1,
                }
            ],
        }

        order = client.map_order(raw_order=raw_order, trace_id="TRACE-001")

        self.assertEqual(order.rule_context.warehouse_name, "华南仓")
        self.assertEqual(order.rule_context.sku_codes, ("维生素C片",))
        self.assertEqual(order.order_lines[0].warehouse_name, "华南仓")
    # === MODIFIED END ===


def make_client(transport, rpa_exporter=None, log_info=None, log_error=None, xlsx_path="tmp/test_jikeyun_missing.xlsx") -> JikeyunClient:
    """Builds a deterministic JackYun client for tests."""

    return JikeyunClient(
        credentials=JikeyunCredentials(app_key="APPKEY", app_secret="SECRET"),
        transport=transport,
        page_size=2,
        rpa_exporter=rpa_exporter,
        xlsx_path=xlsx_path,
        log_info=log_info,
        log_error=log_error,
        clock=lambda: datetime(2026, 4, 30, 12, 0, 0),
    )


def make_raw_order(order_no: str, sku_code: str) -> dict[str, object]:
    """Builds one canonical raw JackYun order fixture."""

    return {
        "order_no": order_no,
        "delivery_order_no": f"DO-{order_no}",
        "sku_code": sku_code,
        "goods_summary": f"Goods {sku_code}",
        "quantity": 1,
        "receiver_name": "Receiver",
        "address": "Address",
        "phone": "13800000000",
        "logistics_company": "SF",
        "logistics_no": "SF001",
        "warehouse_code": "WH-001",
        "warehouse_name": "Warehouse",
        "receiver_province": "浙江省",
        "receiver_city": "杭州市",
        "receiver_district": "西湖区",
    }


def make_xlsx_info(receiver_name: str, address: str, phone: str):
    """Builds one xlsx fallback fixture."""

    from application.xlsx_reader import OrderAddressInfo

    return OrderAddressInfo(
        receiver_name=receiver_name,
        address=address,
        phone=phone,
    )


# === MODIFIED START ===
# 原因：JikeyunHttpTransport 测试需要一个最小 HTTP 响应对象。
# 影响范围：吉客云 transport 测试。
class FakeResponse:
    """Minimal urllib-like response used by transport tests."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        """Returns the fake response body."""

        return self.body

    def close(self) -> None:
        """Closes the fake response."""

        return None
# === MODIFIED END ===
