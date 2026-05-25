import json
from pathlib import Path
from unittest import TestCase

from infrastructure.message_adapter import MessagePayload
from infrastructure.qixin_client import (
    QixinClient,
    make_link_content_builder,
    make_upload_content_builder,
)


class FakeQixinResponse:
    """Provides a minimal urlopen response for Qixin client tests."""

    def read(self) -> bytes:
        """Returns a successful Qixin response body."""

        return json.dumps(
            {
                "code": 200,
                "message": "操作成功",
                "data": {"messageId": "MSG-001"},
            },
            ensure_ascii=False,
        ).encode("utf-8")

    def close(self) -> None:
        """Closes the fake response."""


class QixinClientTests(TestCase):
    """Tests Qixin signed message request construction."""

    # === MODIFIED START ===
    # 原因：文件直推模式必须调用祺信 sendFileToGroup 接口，而不是发送文本下载链接。
    # 影响范围：QixinClient 文件消息请求。
    def test_send_file_to_group_posts_file_message_body(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return FakeQixinResponse()

        client = QixinClient(
            api_base_url="https://state.renruikeji.cn/api/marketengine",
            caller_id="10002",
            secret_key="secret",
            timeout_seconds=12,
            urlopen=fake_urlopen,
        )

        message_id = client.send_file_to_group(
            group_name="12121",
            file_url="https://example.com/orders.xlsx",
            file_name="orders.xlsx",
            user_id="15176152071",
        )

        self.assertEqual(message_id, "MSG-001")
        self.assertEqual(
            captured["url"],
            "https://state.renruikeji.cn/api/marketengine/agent/auth/message/sendFileToGroup",
        )
        self.assertEqual(captured["timeout"], 12)
        self.assertEqual(
            json.loads(captured["body"]),
            {
                "userId": "15176152071",
                "groupName": "12121",
                "fileUrl": "https://example.com/orders.xlsx",
                "fileName": "orders.xlsx",
            },
        )
        self.assertEqual(captured["headers"]["Callerid"], "10002")
        self.assertIn("Sign", captured["headers"])

    def test_content_builders_default_to_xlsx_file_name(self) -> None:
        payload = MessagePayload(
            trace_id="TRACE-001",
            group_name="12121",
            owner_mobile="",
            user_id="",
            file_path=None,
            file_url="https://example.com/orders.xlsx",
        )

        link_content = make_link_content_builder(
            base_url="https://download.example.test",
            secret_key="secret",
        )(payload)
        upload_content = make_upload_content_builder()(payload)

        self.assertIn("orders.xlsx", link_content)
        self.assertIn("orders.xlsx", upload_content)

    def test_content_builders_keep_xlsx_payload_file_name(self) -> None:
        payload = MessagePayload(
            trace_id="TRACE-001",
            group_name="12121",
            owner_mobile="",
            user_id="",
            file_path=Path("outputs/order_files/GROUP-A_20260430110000.xlsx"),
            file_url="https://example.com/GROUP-A_20260430110000.xlsx",
        )

        content = make_upload_content_builder()(payload)

        self.assertIn("GROUP-A_20260430110000.xlsx", content)
    # === MODIFIED END ===
