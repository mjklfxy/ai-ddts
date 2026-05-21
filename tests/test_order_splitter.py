from unittest import TestCase

from application.order_splitter import GroupOrderBatch, OrderLineForSplit, OrderSplitter
from domain.sku_group_info import SkuGroupInfo


def make_order_line(order_no: str, sku_code: str) -> OrderLineForSplit:
    """Builds a validated order line for splitter tests."""

    return OrderLineForSplit(
        order_no=order_no,
        sku_code=sku_code,
        delivery_order_no=f"DO-{order_no}",
        goods_summary=f"Goods {sku_code}",
        quantity=1,
        receiver_name="Receiver",
        address="Address",
        phone="13800000000",
    )


class OrderSplitterTests(TestCase):
    """Tests group-based order splitting without business rule checks."""

    def test_same_group_skus_are_merged_into_one_batch(self) -> None:
        splitter = OrderSplitter(
            sku_group_map={
                "SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
                "SKU-002": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
            }
        )

        batches = splitter.split(
            [
                make_order_line(order_no="SO-001", sku_code="SKU-001"),
                make_order_line(order_no="SO-002", sku_code="SKU-002"),
            ]
        )

        self.assertEqual(len(batches), 1)
        self.assertIsInstance(batches[0], GroupOrderBatch)
        self.assertEqual(batches[0].group_name, "GROUP-A")
        self.assertEqual([line.order_no for line in batches[0].order_lines], ["SO-001", "SO-002"])

    def test_different_groups_are_split_into_separate_batches(self) -> None:
        splitter = OrderSplitter(
            sku_group_map={
                "SKU-001": SkuGroupInfo(group_name="GROUP-B", owner_mobile=""),
                "SKU-002": SkuGroupInfo(group_name="GROUP-A", owner_mobile=""),
            }
        )

        batches = splitter.split(
            (
                make_order_line(order_no="SO-001", sku_code="SKU-001"),
                make_order_line(order_no="SO-002", sku_code="SKU-002"),
            )
        )

        self.assertEqual([batch.group_name for batch in batches], ["GROUP-A", "GROUP-B"])
        self.assertEqual([line.order_no for line in batches[0].order_lines], ["SO-002"])
        self.assertEqual([line.order_no for line in batches[1].order_lines], ["SO-001"])

    # === MODIFIED START ===
    # 原因：排查手机号配置不生效时，需要确认 group/owner_mobile/user_id 都从 SKU 映射传到推送批次。
    # 影响范围：OrderSplitter 到 Pipeline MessagePayload 的配置传递。
    def test_group_identity_fields_are_preserved_in_batch(self) -> None:
        splitter = OrderSplitter(
            sku_group_map={
                "SKU-001": SkuGroupInfo(
                    group_name="12121",
                    owner_mobile="15176152071",
                    user_id="USER-12121",
                )
            }
        )

        batches = splitter.split([make_order_line(order_no="SO-001", sku_code="SKU-001")])

        self.assertEqual(batches[0].group_name, "12121")
        self.assertEqual(batches[0].owner_mobile, "15176152071")
        self.assertEqual(batches[0].user_id, "USER-12121")
    # === MODIFIED END ===

    def test_empty_order_lines_return_no_batches(self) -> None:
        splitter = OrderSplitter(sku_group_map={"SKU-001": SkuGroupInfo(group_name="GROUP-A", owner_mobile="")})

        batches = splitter.split([])

        self.assertEqual(batches, ())

    def test_missing_group_mapping_is_not_swallowed_by_splitter(self) -> None:
        splitter = OrderSplitter(sku_group_map={})

        with self.assertRaisesRegex(ValueError, "未配置推送群"):
            splitter.split([make_order_line(order_no="SO-001", sku_code="SKU-001")])
