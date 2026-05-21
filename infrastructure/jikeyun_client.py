from __future__ import annotations

import hashlib
import json
from time import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from application.order_splitter import OrderLineForSplit
from application.pipeline import PipelineOrder
from application.xlsx_reader import OrderAddressInfo, load_order_address_lookup
from domain.rules.base import RuleContext
from infrastructure.db_to_xlsx import export_orders_to_xlsx


JIKEYUN_ORDER_QUERY_METHOD = "wms.order.query-info.page.v2"


@dataclass(frozen=True, slots=True)
class JikeyunCredentials:
    """Credentials for JackYun open platform requests."""

    app_key: str
    app_secret: str


@dataclass(frozen=True, slots=True)
class JikeyunPageRequest:
    """One paginated JackYun order query request."""

    method: str
    app_key: str
    # === MODIFIED START ===
    # 原因：真实吉客云 OpenAPI 请求需要公共参数和 bizcontent 业务参数。
    # 影响范围：HTTP transport 请求组装。
    version: str
    content_type: str
    biz_content: dict[str, object]
    # === MODIFIED END ===
    timestamp: str
    page_no: int
    page_size: int
    start_time: datetime
    end_time: datetime
    sign: str


@dataclass(frozen=True, slots=True)
class JikeyunPageResult:
    """One paginated JackYun order query response."""

    items: tuple[dict[str, Any], ...]
    has_next: bool


Transport = Callable[[JikeyunPageRequest], JikeyunPageResult]
Clock = Callable[[], datetime]


# === MODIFIED START ===
# 原因：任务运行需要支持从真实吉客云 OpenAPI 拉取分页订单。
# 影响范围：吉客云基础设施适配层。
class JikeyunHttpTransport:
    """Posts signed JackYun OpenAPI requests and normalizes paginated responses."""

    def __init__(
        self,
        api_url: str,
        timeout_seconds: float = 30,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        if not api_url.strip():
            raise ValueError("api_url must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        self.api_url = api_url.strip()
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or urllib.request.urlopen

    def __call__(self, request: JikeyunPageRequest) -> JikeyunPageResult:
        """Sends one request and converts the response into a page result."""

        form = _request_to_form(request)
        body = urllib.parse.urlencode(form).encode("utf-8")
        http_request = urllib.request.Request(
            self.api_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"
            },
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
                f"JackYun request failed: {exc.__class__.__name__}"
            ) from exc

        payload = _decode_response(raw_body)
        _raise_for_api_error(payload)
        return _page_result_from_payload(payload, page_size=request.page_size)


# === MODIFIED END ===


class JikeyunClient:
    """Queries JackYun orders and maps raw records into pipeline orders."""

    def __init__(
        self,
        credentials: JikeyunCredentials,
        transport: Transport,
        page_size: int = 100,
        # === MODIFIED START ===
        # 原因：吉客云订单查询参数尚需联调确认，时间字段、状态字段和额外参数需可配置。
        # 影响范围：吉客云请求业务参数组装。
        version: str = "v1.0",
        content_type: str = "JSON",
        start_time_field: str = "startModifyTime",
        end_time_field: str = "endModifyTime",
        status_field: str = "orderStatusList",
        status_values: tuple[int | str, ...] = (0, 1, 3, 4, 5, 6, 15),
        extra_params: dict[str, object] | None = None,
        page_index_base: int = 0,
        # === MODIFIED END ===
        clock: Clock | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be greater than or equal to 1")
        # === MODIFIED START ===
        # 原因：避免生成不可调用的吉客云请求参数。
        # 影响范围：吉客云客户端初始化校验。
        for field_name, value in {
            "version": version,
            "content_type": content_type,
            "start_time_field": start_time_field,
            "end_time_field": end_time_field,
            "status_field": status_field,
        }.items():
            if not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if page_index_base < 0:
            raise ValueError("page_index_base must be a non-negative integer")
        # === MODIFIED END ===

        self.credentials = credentials
        self.transport = transport
        self.page_size = page_size
        # === MODIFIED START ===
        # 原因：保存吉客云可配置请求参数。
        # 影响范围：build_page_request。
        self.version = version.strip()
        self.content_type = content_type.strip()
        self.start_time_field = start_time_field.strip()
        self.end_time_field = end_time_field.strip()
        self.status_field = status_field.strip()
        # === MODIFIED START ===
        # 原因：真实吉客云接口的 orderStatusList 需要 JSON 数组，状态值可能是整数。
        # 影响范围：吉客云 bizcontent 构造。
        self.status_values = tuple(
            _normalized_status_value(value) for value in status_values
        )
        # === MODIFIED END ===
        self.extra_params = dict(extra_params or {})
        self.page_index_base = page_index_base
        # === MODIFIED END ===
        self.clock = clock or datetime.now

    def fetch_orders(
        self,
        trace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[PipelineOrder, ...]:
        # === MODIFIED START ===
        # 原因：wms.order.query-info.page.v2 的 pageIndex 从 0 开始。
        # 影响范围：真实吉客云分页拉单。
        page_no = self.page_index_base
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：先拉取全部原始订单，再刷新 xlsx，最后统一映射，确保 xlsx 包含最新数据。
        # 影响范围：fetch_orders 调用方。
        raw_items: list[dict[str, Any]] = []

        while True:
            request = self.build_page_request(
                page_no=page_no,
                start_time=start_time,
                end_time=end_time,
            )
            page_result = self.transport(request)
            raw_items.extend(page_result.items)

            if not page_result.has_next:
                break
            page_no += 1
            # time.sleep(1)

        try:
            # export_orders_to_xlsx()
            pass
        except Exception:
            pass
        xlsx_lookup = load_order_address_lookup("input/销售单查询.xlsx")

        orders = [
            self.map_order(
                raw_order=raw_order, trace_id=trace_id, xlsx_lookup=xlsx_lookup
            )
            for raw_order in raw_items
        ]
        return tuple(orders)
        # === MODIFIED END ===

    def build_page_request(
        self,
        page_no: int,
        start_time: datetime,
        end_time: datetime,
    ) -> JikeyunPageRequest:
        timestamp = self.clock().strftime("%Y-%m-%d %H:%M:%S")
        # === MODIFIED START ===
        # 原因：真实吉客云请求需要把分页、时间窗和可配置查询条件放入 bizcontent。
        # 影响范围：吉客云分页请求构造。
        biz_content = self._build_biz_content(
            page_no=page_no,
            start_time=start_time,
            end_time=end_time,
        )
        biz_content_text = _json_dumps(biz_content)
        sign = self.sign(
            {
                "method": JIKEYUN_ORDER_QUERY_METHOD,
                "appkey": self.credentials.app_key,
                "version": self.version,
                "contenttype": self.content_type,
                "timestamp": timestamp,
                "bizcontent": biz_content_text,
            }
        )
        # === MODIFIED END ===
        return JikeyunPageRequest(
            method=JIKEYUN_ORDER_QUERY_METHOD,
            app_key=self.credentials.app_key,
            # === MODIFIED START ===
            # 原因：向 HTTP transport 传递完整公共参数和业务参数。
            # 影响范围：JikeyunHttpTransport。
            version=self.version,
            content_type=self.content_type,
            biz_content=biz_content,
            # === MODIFIED END ===
            timestamp=timestamp,
            page_no=page_no,
            page_size=self.page_size,
            start_time=start_time,
            end_time=end_time,
            sign=sign,
        )

    def sign(self, params: dict[str, object]) -> str:
        # === MODIFIED START ===
        # 原因：吉客云开放平台签名按参数名排序后拼接 key/value，不能记录或外泄 app_secret。
        # 影响范围：吉客云请求签名。
        canonical = "".join(
            f"{key}{_sign_value(value)}"
            for key, value in sorted(params.items(), key=lambda item: item[0])
            if value is not None
        )
        raw = f"{self.credentials.app_secret}{canonical}{self.credentials.app_secret}"
        # === MODIFIED END ===
        # === MODIFIED START ===
        # 原因：吉客云官方签名工具会将签名前原串整体转小写，并返回小写 MD5；
        # 真实接口按此规则验签，原大小写拼接会报“签名错误”。
        # 影响范围：吉客云真实 HTTP 请求签名。
        return hashlib.md5(raw.lower().encode("utf-8")).hexdigest()
        # === MODIFIED END ===

    def map_order(
        self,
        raw_order: dict[str, Any],
        trace_id: str,
        xlsx_lookup: dict[str, OrderAddressInfo] | None = None,
    ) -> PipelineOrder:
        # === MODIFIED START ===
        # 原因：吉客云原始字段可能是 snake_case、camelCase 或多商品明细结构，需要在基础设施层适配。
        # 影响范围：吉客云原始订单到 pipeline 订单的映射。
        order_no = _required_string_any(raw_order, ORDER_NO_ALIASES, "order_no")
        line_sources = _line_sources(raw_order)
        order_lines: list[OrderLineForSplit] = []
        sku_codes: list[str] = []
        # === MODIFIED START ===
        # 原因：排除库房规则和订单明细导出都需要携带吉客云订单里的仓库字段。
        # 影响范围：RuleContext 和 OrderLineForSplit 仓库字段映射。
        order_warehouse_code = (
            _optional_string_any(raw_order, WAREHOUSE_CODE_ALIASES) or ""
        )
        order_warehouse_name = (
            _optional_string_any(raw_order, WAREHOUSE_NAME_ALIASES) or ""
        )
        # === MODIFIED END ===
        for line_source in line_sources:
            merged_source = {**raw_order, **line_source}
            # === MODIFIED START ===
            # 原因：业务配置中的 SKU 口径明确为吉客云订单明细“商品名称”，不是商品编码/条码。
            # 影响范围：排除 SKU、限发区域、群配置、供应商对照等所有 SKU 规则输入。
            sku_code = _required_string_any(merged_source, SKU_CODE_ALIASES, "sku_code")
            # === MODIFIED END ===
            sku_codes.append(sku_code)
            line_warehouse_code = (
                _optional_string_any(merged_source, WAREHOUSE_CODE_ALIASES) or ""
            )
            line_warehouse_name = (
                _optional_string_any(merged_source, WAREHOUSE_NAME_ALIASES) or ""
            )
            if line_warehouse_code and not order_warehouse_code:
                order_warehouse_code = line_warehouse_code
            if line_warehouse_name and not order_warehouse_name:
                order_warehouse_name = line_warehouse_name
            delivery_order_no = (
                _optional_string_any(merged_source, DELIVERY_ORDER_NO_ALIASES)
                or order_no
            )
            # === MODIFIED START ===
            # 原因：真实吉客云未完成发货单可能尚无收件人/地址/电话，优先取 API 字段，
            # 缺失时通过 order_no（erporderNo，JY 格式）从本地 xlsx 订单编号列兜底。
            # delivery_order_no 是 S 格式的 WMS 内部发货单号，xlsx 中没有对应。
            # 影响范围：真实吉客云订单映射到推送文件/异常订单字段。
            xlsx_info = xlsx_lookup.get(order_no) if xlsx_lookup else None

            api_receiver = _optional_string_any(merged_source, RECEIVER_NAME_ALIASES)
            receiver_name = (
                api_receiver
                or (
                    xlsx_info.receiver_name
                    if xlsx_info and xlsx_info.receiver_name
                    else ""
                )
                or "未提供"
            )

            api_address = _optional_string_any(merged_source, ADDRESS_ALIASES)
            address = (
                api_address
                or (xlsx_info.address if xlsx_info and xlsx_info.address else "")
                or "未提供"
            )

            api_phone = _optional_string_any(merged_source, PHONE_ALIASES)
            phone = (
                api_phone
                or (xlsx_info.phone if xlsx_info and xlsx_info.phone else "")
                or "未提供"
            )
            # === MODIFIED END ===
            order_lines.append(
                OrderLineForSplit(
                    order_no=order_no,
                    sku_code=sku_code,
                    delivery_order_no=delivery_order_no,
                    goods_summary=_required_string_any(
                        merged_source,
                        GOODS_SUMMARY_ALIASES,
                        "goods_summary",
                    ),
                    quantity=_required_int_any(
                        merged_source, QUANTITY_ALIASES, "quantity"
                    ),
                    receiver_name=receiver_name,
                    address=address,
                    phone=phone,
                    logistics_company=_optional_string_any(
                        merged_source,
                        LOGISTICS_COMPANY_ALIASES,
                    )
                    or "",
                    logistics_no=_optional_string_any(
                        merged_source, LOGISTICS_NO_ALIASES
                    )
                    or "",
                    # === MODIFIED START ===
                    # 原因：抓取的订单明细需要保留仓库字段，供异常订单查询和导出查看。
                    # 影响范围：订单行数据模型。
                    warehouse_code=line_warehouse_code,
                    warehouse_name=line_warehouse_name,
                    # === MODIFIED END ===
                    # === MODIFIED START ===
                    # 原因：群信息和供应商由 application 层后续填充，基础设施层只给空值占位。
                    # 影响范围：OrderLineForSplit 构造。
                    group_name="",
                    owner_mobile="",
                    supplier_name="",
                    # === MODIFIED END ===
                )
            )

        return PipelineOrder(
            rule_context=RuleContext(
                order_no=order_no,
                trace_id=trace_id,
                warehouse_code=order_warehouse_code or None,
                warehouse_name=order_warehouse_name or None,
                sku_codes=tuple(dict.fromkeys(sku_codes)),
                receiver_province=_optional_string_any(
                    raw_order, RECEIVER_PROVINCE_ALIASES
                ),
                receiver_city=_optional_string_any(raw_order, RECEIVER_CITY_ALIASES),
                receiver_district=_optional_string_any(
                    raw_order, RECEIVER_DISTRICT_ALIASES
                ),
            ),
            order_lines=tuple(order_lines),
        )
        # === MODIFIED END ===

    # === MODIFIED START ===
    # 原因：集中构造吉客云 bizcontent，避免任务编排层写接口字段逻辑。
    # 影响范围：build_page_request。
    def _build_biz_content(
        self,
        page_no: int,
        start_time: datetime,
        end_time: datetime,
    ) -> dict[str, object]:
        """Builds JackYun business query parameters for one page."""

        biz_content: dict[str, object] = {
            # === MODIFIED START ===
            # 原因：真实接口 wms.order.query-info.page.v2 使用 pageIndex，且 0 为第一页。
            # 影响范围：吉客云订单分页请求。
            "pageIndex": page_no,
            # === MODIFIED END ===
            "pageSize": self.page_size,
            self.start_time_field: start_time.strftime("%Y-%m-%d %H:%M:%S"),
            self.end_time_field: end_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.status_values:
            # === MODIFIED START ===
            # 原因：orderStatusList 必须传 JSON 数组；传字符串会触发服务端 parseInt error。
            # 影响范围：吉客云订单状态过滤。
            biz_content[self.status_field] = list(self.status_values)
            # === MODIFIED END ===
        biz_content.update(self.extra_params)
        return biz_content

    # === MODIFIED END ===


# === MODIFIED START ===
# 原因：吉客云原始字段存在多种命名，需要集中维护别名，避免业务层感知外部字段。
# 影响范围：map_order 字段适配。
ORDER_NO_ALIASES = (
    "order_no",
    "erporderNo",
    "erpOrderNo",
    "tradeNo",
    "sourceOrderNo",
    "soNo",
    "platOrderNo",
    "orderNo",
)
DELIVERY_ORDER_NO_ALIASES = (
    "delivery_order_no",
    "deliveryOrderNo",
    "orderNo",
    "wmsOrderNo",
    "stockoutNo",
    "sendOrderNo",
    # === MODIFIED START ===
    # 原因：吉客云 API 可能直接返回中文列名"关联单号"。
    # 影响范围：delivery_order_no 字段映射。
    "关联单号",
    # === MODIFIED END ===
)
# === MODIFIED START ===
# 原因：项目配置里的“SKU”口径由用户确认等同于订单明细的“商品名称”。
# 影响范围：所有基于 sku_codes 的规则和拆分映射。
SKU_CODE_ALIASES = (
    "goodsName",
    "goods_name",
    "productName",
    "product_name",
    "商品名称",
    "sku_code",
    "skuCode",
    "goodsNo",
    "goodsCode",
    "goodsSku",
    "skuBarcode",
    "outSkuCode",
    "barcode",
)
# === MODIFIED END ===
GOODS_SUMMARY_ALIASES = (
    "goods_summary",
    "goodsSummary",
    "goodsName",
    "goods_name",
    "productName",
)
QUANTITY_ALIASES = (
    "quantity",
    "qty",
    "num",
    "goodsCount",
    "sellCount",
    "actualCount",
    "needProcessCount",
)
RECEIVER_NAME_ALIASES = (
    "receiver_name",
    "receiverName",
    "consignee",
    "receiver",
)
ADDRESS_ALIASES = ("address", "receiverAddress", "addr", "detailAddress", "street")
PHONE_ALIASES = ("phone", "receiverMobile", "receiverPhone", "mobile", "tel")
LOGISTICS_COMPANY_ALIASES = (
    "logistics_company",
    "logisticName",
    "logisticsCompany",
    "logisticsName",
    "expressName",
)
LOGISTICS_NO_ALIASES = (
    "logistics_no",
    "logisticNo",
    "logisticsNo",
    "postid",
    "mainPostid",
    "expressNo",
)
# === MODIFIED START ===
# 原因：吉客云抓单需要增加并保留“仓库”字段，实际字段名可能是编码、名称或中文列名。
# 影响范围：仓库筛选规则、异常订单查询和导出。
WAREHOUSE_CODE_ALIASES = (
    "warehouse_code",
    "warehouseCode",
    "warehouseNo",
    "wmsWarehouseCode",
    "wmsWarehouseNo",
    "warehouseId",
    "wmsWarehouseId",
    "stockId",
)
WAREHOUSE_NAME_ALIASES = (
    "warehouse_name",
    "warehouseName",
    "wmsWarehouseName",
    "warehouse",
    "stockName",
    "storeName",
    "shopName",
    "仓库",
    "库房",
)
# === MODIFIED END ===
RECEIVER_PROVINCE_ALIASES = (
    "receiver_province",
    "receiverProvince",
    "province",
    "state",
)
RECEIVER_CITY_ALIASES = ("receiver_city", "receiverCity", "city")
RECEIVER_DISTRICT_ALIASES = (
    "receiver_district",
    "receiverDistrict",
    "district",
    "area",
)
LINE_LIST_ALIASES = (
    "order_lines",
    "goods_details",
    "goodsDetail",
    "goodsList",
    "details",
    "items",
)


def _request_to_form(request: JikeyunPageRequest) -> dict[str, str]:
    """Converts one page request into JackYun form parameters."""

    return {
        "method": request.method,
        "appkey": request.app_key,
        "version": request.version,
        "contenttype": request.content_type,
        "timestamp": request.timestamp,
        "bizcontent": _json_dumps(request.biz_content),
        "sign": request.sign,
    }


def _decode_response(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("JackYun response must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("JackYun response must be a JSON object")
    return payload


def _raise_for_api_error(payload: dict[str, Any]) -> None:
    success = payload.get("success")
    if success is False:
        raise ValueError(f"JackYun API returned error: {_safe_error_message(payload)}")

    code = payload.get("code")
    if code is None:
        code = payload.get("errCode")
    if code is None:
        code = payload.get("errorCode")
    if code is None:
        return

    normalized_code = str(code).strip().lower()
    if normalized_code not in {"0", "200", "success", "true"}:
        raise ValueError(f"JackYun API returned error: {_safe_error_message(payload)}")


def _safe_error_message(payload: dict[str, Any]) -> str:
    for key in ("msg", "message", "subMsg", "errorMsg"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    code = (
        payload.get("code")
        or payload.get("errCode")
        or payload.get("errorCode")
        or "unknown"
    )
    return f"code={code}"


def _page_result_from_payload(
    payload: dict[str, Any], page_size: int | None = None
) -> JikeyunPageResult:
    container = _response_data_container(payload)
    items = _extract_items(container)
    if not items and container is not payload:
        items = _extract_items(payload)
    has_next = _extract_has_next(container)
    if has_next is None and container is not payload:
        has_next = _extract_has_next(payload)
    # === MODIFIED START ===
    # 原因：真实分页响应只返回 result.data 数组，不提供 total/hasNext；
    # 本页满 pageSize 时继续探下一页，直到返回不足一页。
    # 影响范围：吉客云真实分页拉单完整性。
    if has_next is None and page_size is not None:
        has_next = len(items) >= page_size
    # === MODIFIED END ===
    return JikeyunPageResult(items=tuple(items), has_next=bool(has_next))


def _response_data_container(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "result", "bizcontent", "bizContent"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        if isinstance(value, dict):
            return value
    return payload


def _extract_items(container: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "list", "rows", "records", "data"):
        value = container.get(key)
        if isinstance(value, list):
            return [_dict_item(item, key) for item in value]
        if isinstance(value, dict):
            nested_items = _extract_items(value)
            if nested_items:
                return nested_items
    return []


def _dict_item(item: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"JackYun response {field_name} items must be objects")
    return item


def _extract_has_next(container: dict[str, Any]) -> bool | None:
    for key in ("hasNext", "has_next", "hasMore", "has_more"):
        value = container.get(key)
        if isinstance(value, bool):
            return value

    page_no = _optional_int_any(
        container, ("pageNo", "page_no", "pageIndex", "page_index")
    )
    page_size = _optional_int_any(container, ("pageSize", "page_size", "limit"))
    total = _optional_int_any(
        container, ("total", "totalCount", "total_count", "count")
    )
    if page_no is None or page_size is None or total is None:
        return None
    return page_no * page_size < total


def _line_sources(raw_order: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    for key in LINE_LIST_ALIASES:
        value = raw_order.get(key)
        if isinstance(value, list) and value:
            return tuple(_dict_item(item, key) for item in value)
    return (raw_order,)


def _required_string_any(
    data: dict[str, Any],
    aliases: tuple[str, ...],
    field_name: str,
) -> str:
    value = _first_value(data, aliases)
    result = _string_value(value)
    if result is None:
        raise ValueError(f"JackYun field {field_name} must be a non-empty string")
    return result


def _optional_string_any(data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    return _string_value(_first_value(data, aliases))


def _required_int_any(
    data: dict[str, Any],
    aliases: tuple[str, ...],
    field_name: str,
) -> int:
    value = _first_value(data, aliases)
    result = _int_value(value)
    if result is None:
        raise ValueError(f"JackYun field {field_name} must be an integer")
    return result


def _optional_int_any(data: dict[str, Any], aliases: tuple[str, ...]) -> int | None:
    return _int_value(_first_value(data, aliases))


def _first_value(data: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in data:
            value = data[alias]
            # === MODIFIED START ===
            # 原因：真实吉客云响应常包含字段但值为空；应继续尝试后续别名。
            # 影响范围：外部字段别名解析。
            if isinstance(value, str) and not value.strip():
                continue
            if value is not None:
                return value
            # === MODIFIED END ===
    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _sign_value(value: object) -> str:
    if isinstance(value, dict):
        return _json_dumps(value)
    if isinstance(value, list | tuple):
        return _json_dumps(list(value))
    return str(value)


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：吉客云状态过滤既可能是整数状态码，也可能由配置保留为字符串。
# 影响范围：JikeyunClient 初始化参数归一化。
def _normalized_status_value(value: int | str) -> int | str:
    """Normalizes configured JackYun order status values."""

    if isinstance(value, bool):
        raise ValueError("status_values must not contain booleans")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("status_values must contain integers or non-empty strings")


# === MODIFIED END ===
