from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from openpyxl import Workbook

from infrastructure.xlsx_region_parser import load_restricted_regions_from_xlsx
from infrastructure.xlsx_sku_group_parser import load_sku_groups_from_xlsx


class XlsxConfigParserTests(TestCase):
    def test_sku_group_parser_expands_merged_product_block_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sku_groups.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["产品名称", "厂家群名", "群主手机号"])
            ws["A2"] = (
                "蚕丝丝光罩宽肩带内衣/月光白/XL(115-140)"
                "        "
                "男士抗菌棉质内裤(4条装)/颜色随机4XL(175-200)\n"
                "云感棉朵蚕丝内裤(高腰4条装)/颜色随机  L(105-125)"
            )
            ws["B2"] = "婷美&袜子+内衣沟通群"
            ws["C2"] = "18231132648"
            ws.merge_cells("A2:A4")
            ws.merge_cells("B2:B4")
            ws.merge_cells("C2:C4")
            wb.save(path)

            parsed = load_sku_groups_from_xlsx(path)

        self.assertEqual(
            parsed,
            [
                {
                    "sku_code": "蚕丝丝光罩宽肩带内衣/月光白/XL(115-140)",
                    "group_name": "婷美&袜子+内衣沟通群",
                    "owner_mobile": "18231132648",
                },
                {
                    "sku_code": "男士抗菌棉质内裤(4条装)/颜色随机4XL(175-200)",
                    "group_name": "婷美&袜子+内衣沟通群",
                    "owner_mobile": "18231132648",
                },
                {
                    "sku_code": "云感棉朵蚕丝内裤(高腰4条装)/颜色随机  L(105-125)",
                    "group_name": "婷美&袜子+内衣沟通群",
                    "owner_mobile": "18231132648",
                },
            ],
        )

    def test_region_parser_expands_merged_products_against_region_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "regions.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["产品名称", "限发省份", "市区"])
            ws["A2"] = "SKU-A\nSKU-B"
            ws["B2"] = "新疆"
            ws["C2"] = "新增"
            ws["B3"] = "西藏"
            ws["C3"] = ""
            ws.merge_cells("A2:A3")
            wb.save(path)

            parsed = load_restricted_regions_from_xlsx(path)

        self.assertEqual(
            parsed,
            [
                {"sku_code": "SKU-A", "province": "新疆", "city": None},
                {"sku_code": "SKU-A", "province": "西藏", "city": None},
                {"sku_code": "SKU-B", "province": "新疆", "city": None},
                {"sku_code": "SKU-B", "province": "西藏", "city": None},
            ],
        )
