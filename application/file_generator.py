from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub

from application.order_splitter import GroupOrderBatch, OrderLineForSplit
from domain.exception_order import ExceptionOrder


CSV_HEADERS: tuple[str, ...] = (
    "关联单号",
    "发货单号",
    "货品摘要",
    "数量",
    "收件人",
    "地址",
    "电话",
    "物流公司",
    "物流单号",
)

CSV_ERROR_HEADERS: tuple[str, ...] = CSV_HEADERS + ("异常原因",)


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


class CsvFileGenerator:
    """Generates CSV order files for already-split group batches."""

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

        with file_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADERS)
            for order_line in batch.order_lines:
                writer.writerow(self._to_row(order_line))

        return GeneratedFile(
            group_name=batch.group_name,
            file_path=file_path,
            row_count=len(batch.order_lines),
            # === MODIFIED START ===
            # 原因：祺信文件直推模式需要知道文件的公网下载地址，由调用方在生成文件后注入。
            # 影响范围：CsvFileGenerator.generate 返回值、Pipeline 推送阶段。
            file_url=None,
            # === MODIFIED END ===
        )

    def generate_error(
        self, group_name: str, exception_orders: tuple[ExceptionOrder, ...] | list[ExceptionOrder],
    ) -> GeneratedFile:
        error_dir = self.output_dir / "error"
        error_dir.mkdir(parents=True, exist_ok=True)
        safe_group_name = sub(r'[<>:"/\\|?*]+', "_", group_name).strip(". ")
        if not safe_group_name:
            safe_group_name = "group"
        timestamp = self.clock().strftime("%Y%m%d%H%M%S")
        file_path = error_dir / f"{safe_group_name}_{timestamp}_error.csv"

        with file_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_ERROR_HEADERS)
            for order in exception_orders:
                writer.writerow((
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
                ))

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
        return f"{safe_group_name}_{timestamp}.csv"

    @staticmethod
    def _to_row(
        order_line: OrderLineForSplit,
    ) -> tuple[str, str, str, int, str, str, str, str, str]:
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
        )
