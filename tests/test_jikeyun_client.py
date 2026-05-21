import hashlib
import json
import urllib.parse
from datetime import datetime
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


def make_client(transport) -> JikeyunClient:
    """Builds a deterministic JackYun client for tests."""

    return JikeyunClient(
        credentials=JikeyunCredentials(app_key="APPKEY", app_secret="SECRET"),
        transport=transport,
        page_size=2,
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
