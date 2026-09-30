import base64
import hashlib
import hmac
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from backend.main import app, line_webhook, order_status_message, update_order_status
from backend.line import push_line_message, verify_line_signature
from backend.schemas import OrderRead, OrderStatus, OrderStatusUpdate


class LineWebhookTests(unittest.IsolatedAsyncioTestCase):
    def test_webhook_routes_include_configured_path(self) -> None:
        paths = {route.path for route in app.routes}

        self.assertIn("/api/line/webhook", paths)
        self.assertIn("/webhooks/line", paths)

    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {"LINE_CHANNEL_SECRET": "test-secret"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @staticmethod
    def signature(body: bytes) -> str:
        digest = hmac.new(b"test-secret", body, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    async def test_valid_text_event_replies(self) -> None:
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "reply-token",
                        "message": {"type": "text", "text": "สวัสดี"},
                    }
                ]
            }
        ).encode("utf-8")
        request = SimpleNamespace(body=lambda: self.async_body(body))

        with patch("backend.main.reply_to_line_message") as reply:
            result = await line_webhook(request, MagicMock(), self.signature(body))

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(reply.call_args.args[0], "reply-token")
        self.assertIn("เลขออเดอร์", reply.call_args.args[1])

    async def test_tracking_button_links_order_using_checkout_phone(self) -> None:
        body = json.dumps(
            {
                "events": [
                    {
                        "replyToken": "reply-token",
                        "source": {"userId": "Ucustomer"},
                        "message": {"type": "text", "text": "#42 0812345678"},
                    }
                ]
            }
        ).encode("utf-8")
        request = SimpleNamespace(body=lambda: self.async_body(body))
        order = SimpleNamespace(
            id=42,
            phone="081-234-5678",
            line_user_id=None,
            status="pending",
        )
        db = MagicMock()
        db.get.return_value = order
        db.scalars.return_value.all.return_value = [42]

        with patch("backend.main.reply_to_line_message") as reply:
            await line_webhook(request, db, self.signature(body))

        self.assertEqual(order.line_user_id, "Ucustomer")
        db.commit.assert_called_once()
        self.assertIn("ผูกออเดอร์กับ LINE สำเร็จ", reply.call_args.args[1])
        self.assertIn("คิวที่ 1 จาก 1", reply.call_args.args[1])

    async def test_invalid_signature_is_rejected(self) -> None:
        body = b'{"events":[]}'
        request = SimpleNamespace(body=lambda: self.async_body(body))

        with self.assertRaises(HTTPException) as error:
            await line_webhook(request, MagicMock(), "invalid")

        self.assertEqual(error.exception.status_code, 401)

    async def test_empty_events_are_accepted(self) -> None:
        body = b'{"events":[]}'
        request = SimpleNamespace(body=lambda: self.async_body(body))

        self.assertEqual(
            await line_webhook(request, MagicMock(), self.signature(body)),
            {"status": "ok"},
        )

    async def test_malformed_json_is_rejected(self) -> None:
        body = b"{"
        request = SimpleNamespace(body=lambda: self.async_body(body))

        with self.assertRaises(HTTPException) as error:
            await line_webhook(request, MagicMock(), self.signature(body))

        self.assertEqual(error.exception.status_code, 400)

    @staticmethod
    async def async_body(body: bytes) -> bytes:
        return body


class LineSignatureTests(unittest.TestCase):
    def test_order_response_exposes_line_linked_without_user_id(self) -> None:
        order = SimpleNamespace(
            id=42,
            customer_name="Customer",
            phone="0812345678",
            address="Test address",
            note=None,
            line_linked=True,
            total_price=100,
            status="pending",
            created_at=datetime.now(timezone.utc),
            items=[],
        )

        response = OrderRead.model_validate(order)

        self.assertTrue(response.line_linked)
        self.assertFalse(hasattr(response, "line_user_id"))

    def test_missing_channel_secret_is_a_configuration_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as error:
                verify_line_signature(b"{}", "signature")

        self.assertEqual(error.exception.status_code, 503)

    def test_active_order_status_includes_queue_position(self) -> None:
        order = SimpleNamespace(id=2, status="cooking")
        db = MagicMock()
        db.scalars.return_value.all.return_value = [1, 2, 3]

        self.assertEqual(order_status_message(db, order), "ออเดอร์ #2: กำลังทำ\nคิวที่ 2 จาก 3")

    def test_completed_order_status_does_not_include_queue_position(self) -> None:
        order = SimpleNamespace(id=2, status="completed")

        self.assertEqual(order_status_message(MagicMock(), order), "ออเดอร์ #2: เสร็จแล้ว")

    def test_push_message_uses_line_push_endpoint(self) -> None:
        with (
            patch.dict(os.environ, {"LINE_CHANNEL_ACCESS_TOKEN": "test-token"}),
            patch("backend.line._line_api_request") as api_request,
        ):
            push_line_message("Ucustomer", "ออเดอร์ #42: กำลังทำ")

        api_request.assert_called_once_with(
            "message/push",
            {
                "to": "Ucustomer",
                "messages": [{"type": "text", "text": "ออเดอร์ #42: กำลังทำ"}],
            },
        )

    def test_status_change_sends_notification_for_linked_order(self) -> None:
        order = SimpleNamespace(id=42, status="pending", line_user_id="Ucustomer")
        db = MagicMock()
        db.scalar.return_value = order

        with patch("backend.main.send_order_status_notification") as notify:
            update_order_status(
                42,
                OrderStatusUpdate(status=OrderStatus.cooking),
                db,
                None,
            )

        self.assertEqual(order.status, "cooking")
        notify.assert_called_once_with(db, order)
        db.commit.assert_called_once()

    def test_unchanged_status_does_not_send_duplicate_notification(self) -> None:
        order = SimpleNamespace(id=42, status="cooking", line_user_id="Ucustomer")
        db = MagicMock()
        db.scalar.return_value = order

        with patch("backend.main.send_order_status_notification") as notify:
            update_order_status(
                42,
                OrderStatusUpdate(status=OrderStatus.cooking),
                db,
                None,
            )

        notify.assert_not_called()
