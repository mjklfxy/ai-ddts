import json
from unittest import TestCase

from infrastructure.qixin_client import QixinClient


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
            file_url="https://example.com/orders.csv",
            file_name="orders.csv",
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
                "fileUrl": "https://example.com/orders.csv",
                "fileName": "orders.csv",
            },
        )
        self.assertEqual(captured["headers"]["Callerid"], "10002")
        self.assertIn("Sign", captured["headers"])
    # === MODIFIED END ===
