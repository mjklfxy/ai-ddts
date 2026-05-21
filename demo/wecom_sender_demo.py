"""
调用企业微信群文件推送接口的示例。

接口约定：
  POST /api/v1/wecom/groups/push-file
  Content-Type: multipart/form-data

  请求字段：
    group_name  - 企业微信群名称
    owner_mobile - 群主手机号（服务端通过 /get_userid_by_mobile 转 userid）
    file        - 文件（csv / xlsx）
"""

import requests  # pip install requests
from pathlib import Path


def push_file_to_wecom_group(
    api_base_url: str,
    group_name: str,
    owner_mobile: str,
    file_path: str | Path,
    timeout: float = 10,
) -> dict:
    """
    推送文件到企业微信群。

    Args:
        api_base_url: 对方服务地址，如 "http://10.0.0.5:8080"
        group_name:   群名称，用于匹配目标群聊
        owner_mobile: 群主手机号，用于定位群主 userid
        file_path:    待推送文件路径（csv / xlsx）
        timeout:      请求超时时间（秒），涉及多次企微 API 调用，建议 ≥ 10s

    Returns:
        {"code": 0, "data": {"trace_id": "...", "chatid": "...", "file_name": "..."}}

    Raises:
        requests.HTTPError: 服务端返回非 200 时抛出
    """
    url = f"{api_base_url.rstrip('/')}/api/v1/wecom/groups/push-file"
    file_path = Path(file_path)

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            data={
                "group_name": group_name,
                "owner_mobile": owner_mobile,
            },
            files={
                "file": (file_path.name, f, "application/octet-stream"),
            },
            timeout=timeout,
        )

    response.raise_for_status()
    body = response.json()

    if body.get("code") != 0:
        raise requests.HTTPError(
            f"Push failed: code={body.get('code')}, message={body.get('message', 'unknown')}"
        )

    return body


# === 本地演示用 main ===
if __name__ == "__main__":
    import sys

    # 用法: python demo/wecom_sender_demo.py <file_path> <group_name> <owner_mobile>
    if len(sys.argv) < 4:
        print(
            "Usage: python demo/wecom_sender_demo.py <file_path> <group_name> <owner_mobile>"
        )
        print(
            "Example: python demo/wecom_sender_demo.py ./outputs/order_files/测试群_20260513153901.csv '正大食品供应群' 13800001111"
        )
        sys.exit(1)

    file_path = sys.argv[1]
    group_name = sys.argv[2]
    owner_mobile = sys.argv[3]

    result = push_file_to_wecom_group(
        # 换成对方实际的服务地址
        api_base_url="http://10.0.0.5:8080",
        group_name=group_name,
        owner_mobile=owner_mobile,
        file_path=file_path,
    )

    data = result["data"]
    print("推送成功")
    print(f"  trace_id:  {data['trace_id']}")
    print(f"  chatid:    {data['chatid']}")
    print(f"  file_name: {data['file_name']}")
