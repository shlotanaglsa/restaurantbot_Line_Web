import base64
import hashlib
import hmac
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

LINE_API_URL = "https://api.line.me/v2/bot"
TRACKING_PROMPT = (
    "หากต้องการผูกออเดอร์กับ LINE กรุณาส่งเลขออเดอร์และเบอร์โทรที่ใช้สั่ง "
    "ตัวอย่าง: #123 0812345678"
)
QUICK_REPLIES = [
    {
        "type": "action",
        "action": {"type": "message", "label": "ติดตามสถานะออเดอร์", "text": "ติดตามสถานะออเดอร์"},
    },
    {
        "type": "action",
        "action": {"type": "message", "label": "เช็กสถานะ", "text": "เช็กสถานะ"},
    },
]


def verify_line_signature(body: bytes, signature: str | None) -> bool:
    channel_secret = os.getenv("LINE_CHANNEL_SECRET")
    if not channel_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE webhook is not configured. Set LINE_CHANNEL_SECRET.",
        )
    if signature is None:
        return False

    expected_signature = base64.b64encode(
        hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(signature, expected_signature)


def _line_api_request(path: str, payload: dict | None = None) -> dict:
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE Messaging API is not configured. Set LINE_CHANNEL_ACCESS_TOKEN.",
        )

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{LINE_API_URL}/{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LINE Messaging API returned HTTP {exc.code}.",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not connect to the LINE Messaging API.",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LINE Messaging API request timed out.",
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LINE Messaging API returned an invalid response.",
        ) from exc


def reply_to_line_message(reply_token: str, text: str) -> None:
    _line_api_request(
        "message/reply",
        {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                    "quickReply": {"items": QUICK_REPLIES},
                }
            ],
        },
    )


def push_line_message(user_id: str, text: str) -> None:
    _line_api_request(
        "message/push",
        {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        },
    )


def get_line_bot_info() -> dict:
    bot_info = _line_api_request("info")
    return {
        "connected": True,
        "display_name": bot_info.get("displayName"),
        "basic_id": bot_info.get("basicId"),
    }
