# Restaurant Order Bot API

FastAPI backend for the restaurant customer menu and admin order dashboard. The API uses the Supabase Postgres tables `menu_items`, `menu_options`, `orders`, `order_items`, and `order_item_options`.

## Run locally

1. Set `DATABASE_URL` and `DIRECT_URL` in `.env`. Keep `.env` private; it is excluded by `.gitignore`.
2. Set a private `ADMIN_API_KEY` in `.env` (see `.env.example`) before using the admin menu endpoints. Do not expose this key in public client code.
3. Set `LINE_CHANNEL_ACCESS_TOKEN` and `LINE_CHANNEL_SECRET` in `.env` using the credentials from your LINE Messaging API channel.
4. Create the tables in Supabase using the supplied SQL schema.
5. Install dependencies and start the API:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn backend.main:app --reload
   ```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

In a second terminal, serve the frontend:

```powershell
python -m http.server 5500 --directory frontend
```

Open `http://localhost:5500/customer/` to place a delivery order. After the order is accepted, the confirmation shows a ready-to-copy LINE message containing the order number and checkout phone number; send it to the restaurant's LINE account to link the order and receive status updates.

Open `http://localhost:5500/admin/` for the order dashboard. Enter the API URL and the same `ADMIN_API_KEY` configured in the backend `.env`. Use the dashboard to review orders, update their status, and compare completed sales by day, month, or year; choose any two dates to compare (the selected month or year is used for monthly/yearly summaries). Open **จัดการเมนู** to edit the catalog.

For an existing database, apply `backend/migrations/20260929_order_dashboard.sql` and `backend/migrations/20260930_line_order_tracking.sql` once before deploying the updated API. The first migration maps legacy `new`/`accepted` statuses to `pending` and `ready` to `cooking`; the second adds LINE customer linking to orders.

## Endpoints

- `GET /menu` returns available menu items and their options.
- `POST /orders` accepts customer details and menu/option IDs. Prices are read from the database and calculated by the server.
- `GET /orders?status=pending` returns orders, optionally filtered by status (`pending`, `cooking`, `completed`, or `cancelled`).
- `PATCH /orders/{id}/status` accepts a JSON body such as `{"status":"cooking"}`.
- `GET /admin/dashboard/stats?days=7` returns order counts, completed-order revenue, today's completed-order revenue, and daily completed sales for 1–90 days.
- `GET /admin/dashboard/sales-summary?period=monthly&anchor_date=2026-04-01` returns completed sales grouped by day for the month containing `anchor_date`; `period` can be `daily`, `monthly`, or `yearly`.
- `GET /admin/menu` lists all menu items, including items that are not currently available.
- `POST /admin/menu` creates a menu item and its options.
- `PUT /admin/menu/{id}` replaces a menu item and its options.
- `DELETE /admin/menu/{id}` archives the item by setting `available` to `false`, preserving order history.

Order listing/status updates, dashboard statistics, and menu management require the `X-Admin-Api-Key` header. The dashboard is `frontend/admin/dashboard.html`; serve the frontend from an allowed `FRONTEND_ORIGINS` origin, open the page, and enter the API URL and admin key. The key is kept in browser session storage, not in source files.

Set `FRONTEND_ORIGINS` to a comma-separated list of allowed frontend origins when deploying.
Sales summaries use the `BUSINESS_TIMEZONE` environment variable (default `Asia/Bangkok`) to define day, month, and year boundaries.

## Connect a LINE Messaging API channel

The webhook endpoint is `POST /api/line/webhook` (`POST /webhooks/line` is also supported). For local development, expose the running API on a public HTTPS URL (for example, with ngrok), then set the LINE Developers Console **Webhook URL** to the complete URL `https://<public-host>/api/line/webhook` and enable **Use webhook**. Do not use only the host or `/`; requests to `/` are not a webhook endpoint. Click **Verify** in the console; an empty `events` array is accepted. The endpoint validates `X-Line-Signature` against the raw request body and shows **ติดตามสถานะออเดอร์** and **เช็กสถานะ** quick-reply buttons.

Customers can link an existing order in the LINE chat by tapping **ติดตามสถานะออเดอร์** and sending the order number and the phone number used at checkout (for example, `#123 0812345678`). Tapping **เช็กสถานะ** shows linked orders. Once linked, changing an order's status in the restaurant dashboard sends a LINE message with its status and, while active, its position in the queue. The dashboard separates waiting, cooking, completed, and cancelled orders; use **ส่งสถานะทาง LINE** to resend the current status. Orders are linked only after the order number and checkout phone match.

To check that the channel access token works, call `GET /line/bot-info` with the `X-Admin-Api-Key` header:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/line/bot-info -Headers @{ "X-Admin-Api-Key" = "<ADMIN_API_KEY>" }
```

A successful response includes the bot's display name and basic ID. Never put either LINE credential or the admin key in frontend code or share them in logs.
