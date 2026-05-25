from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from infrastructure.file_upload_client import FileUploadClient


class FileUploadClientTests(TestCase):
    """Tests generated file upload request construction."""

    def test_upload_posts_xlsx_with_excel_content_type(self) -> None:
        upload_path = Path("tmp") / "test_file_upload_client" / "orders.xlsx"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"xlsx-bytes")
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"url": "https://example.com/orders.xlsx"}

        with patch("infrastructure.file_upload_client.requests.post", return_value=response) as post:
            url = FileUploadClient("https://upload.example.test").upload(upload_path)

        self.assertEqual(url, "https://example.com/orders.xlsx")
        files = post.call_args.kwargs["files"]
        file_name, file_obj, content_type = files["file"]
        self.assertEqual(file_name, "orders.xlsx")
        self.assertEqual(
            content_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(file_obj.closed)
