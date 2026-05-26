import json
from unittest import TestCase

from infrastructure.product_caller_sync_client import (
    ProductCallerConfigSyncClient,
    ProductCallerConfigSyncError,
)


class ProductCallerConfigSyncClientTests(TestCase):
    """Tests the push-center product caller config sync HTTP client."""

    def test_sync_posts_expected_payload_and_returns_response(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "code": 200,
                    "data_id": 2605231622,
                    "synced": 2,
                    "created": 2,
                    "updated": 0,
                    "skipped": 0,
                }
            )

        client = ProductCallerConfigSyncClient(
            api_url="https://push-center.example.test/sync",
            timeout_seconds=9,
            urlopen=fake_urlopen,
        )

        response = client.sync(
            data_id=2605231622,
            data=[
                {
                    "goods_name": "三只松鼠核桃",
                    "group_name": "三只松鼠对接群",
                    "user_id": "owner001",
                },
                {
                    "goods_name": "雪中飞衣服",
                    "group_name": "雪中飞产品对接群",
                    "user_id": "owner002",
                },
            ],
        )

        self.assertEqual(captured["url"], "https://push-center.example.test/sync")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], 9)
        self.assertEqual(captured["headers"]["Content-type"], "application/json")
        self.assertEqual(
            json.loads(captured["body"]),
            {
                "data_id": 2605231622,
                "count": 2,
                "data": [
                    {
                        "goods_name": "三只松鼠核桃",
                        "group_name": "三只松鼠对接群",
                        "user_id": "owner001",
                    },
                    {
                        "goods_name": "雪中飞衣服",
                        "group_name": "雪中飞产品对接群",
                        "user_id": "owner002",
                    },
                ],
            },
        )
        self.assertEqual(response["synced"], 2)

    def test_sync_rejects_non_success_code(self) -> None:
        client = ProductCallerConfigSyncClient(
            api_url="https://push-center.example.test/sync",
            urlopen=lambda _request, timeout: _FakeResponse({"code": 500, "message": "failed"}),
        )

        with self.assertRaisesRegex(ProductCallerConfigSyncError, "code=500"):
            client.sync(data_id=2605231622, data=[])


class _FakeResponse:
    """Minimal urlopen response double for product caller sync tests."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def close(self) -> None:
        return None
