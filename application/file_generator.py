from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub

from openpyxl import Workbook

from application.order_splitter import GroupOrderBatch, OrderLineForSplit
from domain.exception_order import ExceptionOrder


# === MODIFIED START ===
# 原因：推送/上传文件统一改为 Excel，表头继续沿用原订单文件字段。
# 影响范围：订单文件生成、上传文件名、祺信推送文件名。
ORDER_FILE_HEADERS: tuple[str, ...] = (
    "关联单号",
    "发货单号",
    "货品摘要",
    "数量",
    "收件人",
    "地址",
    "电话",
    "物流公司",
    "物流单号",
    "渠道分类",
)

ORDER_ERROR_HEADERS: tuple[str, ...] = ORDER_FILE_HEADERS + ("异常原因",)
# === MODIFIED END ===


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    """Generated order file metadata."""

    group_name: str
    file_path: Path
    row_count: int
    # === MODIFIED START ===
    # 原因：祺信文件直推模式需要知道文件的公网下载地址。
    # 影响范围：GeneratedFile、Pipeline 推送阶段、QixinSender._send_file_message。
    file_url: str | None = None
    # === MODIFIED END ===


# === MODIFIED START ===
# 原因：推送/上传文件统一改为 Excel，替换原 CSV 生成实现。
# 影响范围：正常订单文件、异常订单文件、Pipeline 上传和推送文件路径。
class ExcelFileGenerator:
    """Generates Excel order files for already-split group batches."""

    def __init__(
        self,
        output_dir: str | Path = "outputs/order_files",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.clock = clock or datetime.now

    def generate(self, batch: GroupOrderBatch) -> GeneratedFile:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.output_dir / self._build_file_name(batch.group_name)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "orders"
        worksheet.append(ORDER_FILE_HEADERS)
        for order_line in batch.order_lines:
            worksheet.append(self._to_row(order_line))
        workbook.save(file_path)
        workbook.close()

        return GeneratedFile(
            group_name=batch.group_name,
            file_path=file_path,
            row_count=len(batch.order_lines),
            # === MODIFIED START ===
            # 原因：祺信文件直推模式需要知道文件的公网下载地址，由调用方在生成文件后注入。
            # 影响范围：ExcelFileGenerator.generate 返回值、Pipeline 推送阶段。
            file_url=None,
            # === MODIFIED END ===
        )

    def generate_error(
        self,
        group_name: str,
        exception_orders: tuple[ExceptionOrder, ...] | list[ExceptionOrder],
    ) -> GeneratedFile:
        error_dir = self.output_dir / "error"
        error_dir.mkdir(parents=True, exist_ok=True)
        safe_group_name = sub(r'[<>:"/\\|?*]+', "_", group_name).strip(". ")
        if not safe_group_name:
            safe_group_name = "group"
        timestamp = self.clock().strftime("%Y%m%d%H%M%S")
        file_path = error_dir / f"{safe_group_name}_{timestamp}_error.xlsx"

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "errors"
        worksheet.append(ORDER_ERROR_HEADERS)
        for order in exception_orders:
            worksheet.append(
                (
                    order.order_no,
                    order.delivery_order_no,
                    order.goods_summary,
                    order.quantity,
                    order.receiver_name,
                    order.address,
                    order.phone,
                    order.logistics_company,
                    order.logistics_no,
                    order.reason,
                )
            )
        workbook.save(file_path)
        workbook.close()

        return GeneratedFile(
            group_name=group_name,
            file_path=file_path,
            row_count=len(exception_orders),
            file_url=None,
        )

    def _build_file_name(self, group_name: str) -> str:
        # 只过滤 Windows 文件名不允许的字符: < > : " / \ | ? *
        safe_group_name = sub(r'[<>:"/\\|?*]+', "_", group_name).strip(". ")
        if not safe_group_name:
            safe_group_name = "group"
        timestamp = self.clock().strftime("%Y%m%d%H%M%S")
        return f"{safe_group_name}_{timestamp}.xlsx"

    @staticmethod
    def _to_row(
        order_line: OrderLineForSplit,
    ) -> tuple[str, str, str, int, str, str, str, str, str, str]:
        return (
            order_line.order_no,
            order_line.delivery_order_no,
            order_line.goods_summary,
            order_line.quantity,
            order_line.receiver_name,
            order_line.address,
            order_line.phone,
            order_line.logistics_company,
            order_line.logistics_no,
            order_line.channel_classification,
        )


# === MODIFIED END ===


# === MODIFIED START ===
# 原因：保留旧类名兼容现有 pipeline 组装点，实际生成格式已统一为 Excel。
# 影响范围：既有 CsvFileGenerator 引用。
class CsvFileGenerator(ExcelFileGenerator):
    """Backward-compatible generator name that now writes Excel files."""


# 旧常量名仅供历史测试/调用兼容，内容与 Excel 表头一致。
CSV_HEADERS = ORDER_FILE_HEADERS
CSV_ERROR_HEADERS = ORDER_ERROR_HEADERS
# === MODIFIED END ===
