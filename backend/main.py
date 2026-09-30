import json
import os
import re
import secrets
import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from .database import get_db
from .line import (
    TRACKING_PROMPT,
    get_line_bot_info,
    push_line_message,
    reply_to_line_message,
    verify_line_signature,
)
from .models import MenuItem, MenuOption, Order, OrderItem, OrderItemOption
from .schemas import (
    DashboardStats,
    DailySalesRead,
    MenuItemRead,
    MenuItemWrite,
    OrderCreate,
    OrderRead,
    OrderStatus,
    OrderStatusUpdate,
    SalesBucket,
    SalesPeriod,
    SalesPeriodSummary,
)

app = FastAPI(title="Restaurant Order API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Api-Key"],
)

Database = Annotated[Session, Depends(get_db)]


def require_admin(
    api_key: Annotated[str | None, Header(alias="X-Admin-Api-Key")] = None,
) -> None:
    expected_key = os.getenv("ADMIN_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured. Set ADMIN_API_KEY in the server environment.",
        )
    if api_key is None or not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid admin API key is required.",
        )


AdminAccess = Annotated[None, Depends(require_admin)]
BUSINESS_TIMEZONE = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "Asia/Bangkok"))

LEGACY_ORDER_STATUSES = {
    "new": OrderStatus.pending.value,
    "accepted": OrderStatus.pending.value,
    "ready": OrderStatus.cooking.value,
}


def normalize_order_status(value: str) -> str:
    return LEGACY_ORDER_STATUSES.get(value, value)


ACTIVE_ORDER_STATUSES = (OrderStatus.pending.value, OrderStatus.cooking.value)
LINE_ORDER_REFERENCE = re.compile(r"^#?(\d{1,10})\s+(\+?[\d\s().-]{6,25})$")


def order_queue_position(db: Session, order: Order) -> tuple[int | None, int]:
    queue_ids = list(
        db.scalars(
            select(Order.id)
            .where(Order.status.in_(ACTIVE_ORDER_STATUSES))
            .order_by(Order.created_at, Order.id)
        ).all()
    )
    try:
        return queue_ids.index(order.id) + 1, len(queue_ids)
    except ValueError:
        return None, len(queue_ids)


def order_status_message(db: Session, order: Order) -> str:
    order_status = normalize_order_status(order.status)
    labels = {
        OrderStatus.pending.value: "รอทำ",
        OrderStatus.cooking.value: "กำลังทำ",
        OrderStatus.completed.value: "เสร็จแล้ว",
        OrderStatus.cancelled.value: "ยกเลิก",
    }
    message = f"ออเดอร์ #{order.id}: {labels[order_status]}"
    if order_status in ACTIVE_ORDER_STATUSES:
        position, queue_size = order_queue_position(db, order)
        if position is not None:
            message += f"\nคิวที่ {position} จาก {queue_size}"
    return message


def send_order_status_notification(db: Session, order: Order) -> None:
    if not order.line_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ลูกค้ายังไม่ได้ผูกออเดอร์กับ LINE",
        )
    push_line_message(order.line_user_id, order_status_message(db, order))


@app.get("/menu", response_model=list[MenuItemRead])
def get_menu(db: Database) -> list[MenuItem]:
    statement = (
        select(MenuItem)
        .where(MenuItem.available.is_(True))
        .options(selectinload(MenuItem.options))
        .order_by(MenuItem.category, MenuItem.id)
    )
    return list(db.scalars(statement).all())


@app.get("/admin/menu", response_model=list[MenuItemRead], dependencies=[Depends(require_admin)])
def get_admin_menu(db: Database) -> list[MenuItem]:
    statement = (
        select(MenuItem)
        .options(selectinload(MenuItem.options))
        .order_by(MenuItem.category, MenuItem.id)
    )
    return list(db.scalars(statement).all())


@app.post(
    "/admin/menu",
    response_model=MenuItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_menu_item(payload: MenuItemWrite, db: Database, _: AdminAccess) -> MenuItem:
    menu_item = MenuItem(
        name=payload.name,
        description=payload.description,
        price=payload.price,
        category=payload.category,
        available=payload.available,
        options=[MenuOption(name=option.name, price=option.price) for option in payload.options],
    )
    db.add(menu_item)
    db.commit()
    return db.scalar(
        select(MenuItem)
        .where(MenuItem.id == menu_item.id)
        .options(selectinload(MenuItem.options))
    )


@app.put("/admin/menu/{menu_item_id}", response_model=MenuItemRead)
def update_menu_item(
    menu_item_id: int,
    payload: MenuItemWrite,
    db: Database,
    _: AdminAccess,
) -> MenuItem:
    menu_item = db.scalar(
        select(MenuItem)
        .where(MenuItem.id == menu_item_id)
        .options(selectinload(MenuItem.options))
    )
    if menu_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")

    menu_item.name = payload.name
    menu_item.description = payload.description
    menu_item.price = payload.price
    menu_item.category = payload.category
    menu_item.available = payload.available
    menu_item.options[:] = [
        MenuOption(name=option.name, price=option.price)
        for option in payload.options
    ]
    db.commit()
    return db.scalar(
        select(MenuItem)
        .where(MenuItem.id == menu_item_id)
        .options(selectinload(MenuItem.options))
    )


@app.delete("/admin/menu/{menu_item_id}", response_model=MenuItemRead)
def archive_menu_item(menu_item_id: int, db: Database, _: AdminAccess) -> MenuItem:
    menu_item = db.scalar(
        select(MenuItem)
        .where(MenuItem.id == menu_item_id)
        .options(selectinload(MenuItem.options))
    )
    if menu_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")

    menu_item.available = False
    db.commit()
    return menu_item


@app.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Database) -> Order:
    menu_item_ids = {item.menu_item_id for item in payload.items}
    menu_items = db.scalars(
        select(MenuItem)
        .where(MenuItem.id.in_(menu_item_ids))
        .options(selectinload(MenuItem.options))
    ).all()
    menu_by_id = {item.id: item for item in menu_items}

    missing_ids = menu_item_ids - menu_by_id.keys()
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item(s) not found: {', '.join(map(str, sorted(missing_ids)))}",
        )

    if any(not menu_by_id[item_id].available for item_id in menu_item_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more menu items are currently unavailable.",
        )

    order = Order(
        customer_name=payload.customer_name,
        phone=payload.phone,
        address=payload.address,
        note=payload.note,
        total_price=Decimal("0.00"),
        status=OrderStatus.pending.value,
    )

    total = Decimal("0.00")
    for requested_item in payload.items:
        menu_item = menu_by_id[requested_item.menu_item_id]
        options_by_id = {option.id: option for option in menu_item.options}
        if len(requested_item.option_ids) != len(set(requested_item.option_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An option cannot be selected more than once for the same item.",
            )

        selected_options: list[MenuOption] = []
        for option_id in requested_item.option_ids:
            option = options_by_id.get(option_id)
            if option is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Option {option_id} does not belong to menu item {menu_item.id}.",
                )
            selected_options.append(option)

        option_total = sum(
            (option.price or Decimal("0.00") for option in selected_options),
            start=Decimal("0.00"),
        )
        unit_price = menu_item.price + option_total
        subtotal = unit_price * requested_item.quantity
        total += subtotal

        order_item = OrderItem(
            menu_item_id=menu_item.id,
            quantity=requested_item.quantity,
            unit_price=unit_price,
            note=requested_item.note,
            subtotal=subtotal,
            options=[
                OrderItemOption(
                    option_name=option.name,
                    option_price=option.price or Decimal("0.00"),
                )
                for option in selected_options
            ],
        )
        order.items.append(order_item)

    order.total_price = total
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders", response_model=list[OrderRead])
def get_orders(
    db: Database,
    _: AdminAccess,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
) -> list[Order]:
    statement = (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.options))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if order_status is not None:
        accepted_statuses = [
            order_status.value,
            *(
                legacy_status
                for legacy_status, current_status in LEGACY_ORDER_STATUSES.items()
                if current_status == order_status.value
            ),
        ]
        statement = statement.where(Order.status.in_(accepted_statuses))
    orders = list(db.scalars(statement).all())
    for order in orders:
        order.status = normalize_order_status(order.status)
    return orders


@app.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Database,
    _: AdminAccess,
) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.options))
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    previous_status = normalize_order_status(order.status)
    order.status = payload.status.value
    db.commit()
    db.refresh(order)
    if previous_status != payload.status.value and order.line_user_id:
        try:
            send_order_status_notification(db, order)
        except HTTPException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"อัปเดตสถานะออเดอร์แล้ว แต่ส่ง LINE ไม่สำเร็จ "
                    f"(HTTP {exc.status_code}); กดส่งสถานะทาง LINE เพื่อลองอีกครั้ง"
                ),
            ) from exc
    return order


@app.post("/admin/orders/{order_id}/notify", dependencies=[Depends(require_admin)])
def notify_order_status(order_id: int, db: Database) -> dict[str, bool]:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    send_order_status_notification(db, order)
    return {"sent": True}


@app.get(
    "/admin/dashboard/stats",
    response_model=DashboardStats,
    dependencies=[Depends(require_admin)],
)
def get_dashboard_stats(
    db: Database,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> DashboardStats:
    now = datetime.now(BUSINESS_TIMEZONE)
    today_start = datetime.combine(now.date(), time.min, tzinfo=BUSINESS_TIMEZONE)
    range_start = today_start - timedelta(days=days - 1)

    stored_order_counts = db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    ).all()
    order_counts: dict[str, int] = {}
    for stored_status, count in stored_order_counts:
        current_status = normalize_order_status(stored_status)
        order_counts[current_status] = order_counts.get(current_status, 0) + count
    total_orders = sum(count for _, count in stored_order_counts)
    completed_sales = db.scalar(
        select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.status == OrderStatus.completed.value
        )
    )
    today_sales = db.scalar(
        select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.status == OrderStatus.completed.value,
            Order.created_at >= today_start.astimezone(timezone.utc),
            Order.created_at < (today_start + timedelta(days=1)).astimezone(timezone.utc),
        )
    )

    sale_date = cast(
        func.timezone(BUSINESS_TIMEZONE.key, Order.created_at),
        Date,
    ).label("sale_date")
    sales_rows = db.execute(
        select(
            sale_date,
            func.coalesce(func.sum(Order.total_price), 0).label("total_sales"),
            func.count(Order.id).label("order_count"),
        )
        .where(
            Order.status == OrderStatus.completed.value,
            Order.created_at >= range_start.astimezone(timezone.utc),
            Order.created_at < (today_start + timedelta(days=1)).astimezone(timezone.utc),
        )
        .group_by(sale_date)
        .order_by(sale_date)
    ).all()
    sales_by_date = {
        row.sale_date: (Decimal(row.total_sales), row.order_count)
        for row in sales_rows
    }
    daily_sales = []
    for offset in range(days):
        sale_day = (range_start + timedelta(days=offset)).date()
        total_sales, order_count = sales_by_date.get(sale_day, (Decimal("0.00"), 0))
        daily_sales.append(
            DailySalesRead(
                date=sale_day,
                total_sales=total_sales,
                order_count=order_count,
            )
        )
    return DashboardStats(
        total_orders=total_orders,
        pending_orders=order_counts.get(OrderStatus.pending.value, 0),
        cooking_orders=order_counts.get(OrderStatus.cooking.value, 0),
        completed_orders=order_counts.get(OrderStatus.completed.value, 0),
        total_sales=Decimal(completed_sales),
        today_sales=Decimal(today_sales),
        daily_sales=daily_sales,
    )


@app.get(
    "/admin/dashboard/sales-summary",
    response_model=SalesPeriodSummary,
    dependencies=[Depends(require_admin)],
)
def get_sales_summary(
    db: Database,
    period: SalesPeriod,
    anchor_date: date,
) -> SalesPeriodSummary:
    if period is SalesPeriod.daily:
        start_day = anchor_date
        next_day = start_day + timedelta(days=1)
        bucket_unit = "hour"
        bucket_count = 24
        labels = [f"{hour:02d}:00" for hour in range(bucket_count)]
    elif period is SalesPeriod.monthly:
        start_day = anchor_date.replace(day=1)
        next_day = (
            date(start_day.year + (start_day.month == 12), start_day.month % 12 + 1, 1)
        )
        bucket_unit = "day"
        bucket_count = calendar.monthrange(start_day.year, start_day.month)[1]
        labels = [str(day) for day in range(1, bucket_count + 1)]
    else:
        start_day = date(anchor_date.year, 1, 1)
        next_day = date(anchor_date.year + 1, 1, 1)
        bucket_unit = "month"
        bucket_count = 12
        labels = [f"{month:02d}" for month in range(1, bucket_count + 1)]

    period_start = datetime.combine(start_day, time.min, tzinfo=BUSINESS_TIMEZONE)
    period_end = datetime.combine(next_day, time.min, tzinfo=BUSINESS_TIMEZONE)
    bucket_expression = func.date_trunc(
        bucket_unit,
        func.timezone(BUSINESS_TIMEZONE.key, Order.created_at),
    )
    rows = db.execute(
        select(
            bucket_expression.label("bucket_start"),
            func.coalesce(func.sum(Order.total_price), 0).label("total_sales"),
            func.count(Order.id).label("order_count"),
        )
        .where(
            Order.status == OrderStatus.completed.value,
            Order.created_at >= period_start.astimezone(timezone.utc),
            Order.created_at < period_end.astimezone(timezone.utc),
        )
        .group_by(bucket_expression)
        .order_by(bucket_expression)
    ).all()

    bucket_values: dict[int, tuple[Decimal, int]] = {}
    for row in rows:
        bucket_start = row.bucket_start
        index = (
            bucket_start.hour
            if period is SalesPeriod.daily
            else bucket_start.day - 1
            if period is SalesPeriod.monthly
            else bucket_start.month - 1
        )
        bucket_values[index] = (Decimal(row.total_sales), row.order_count)

    buckets = []
    for index, label in enumerate(labels):
        total_sales, order_count = bucket_values.get(index, (Decimal("0.00"), 0))
        if period is SalesPeriod.monthly:
            label = f"{index + 1:02d}"
        buckets.append(
            SalesBucket(
                label=label,
                total_sales=total_sales,
                order_count=order_count,
            )
        )

    return SalesPeriodSummary(
        period=period,
        start_date=start_day,
        end_date=next_day - timedelta(days=1),
        total_sales=sum((bucket.total_sales for bucket in buckets), Decimal("0.00")),
        order_count=sum(bucket.order_count for bucket in buckets),
        buckets=buckets,
    )


@app.get("/health", status_code=status.HTTP_204_NO_CONTENT)
def health_check() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/line/webhook")
@app.post("/webhooks/line", include_in_schema=False)
async def line_webhook(
    request: Request,
    db: Database,
    x_line_signature: Annotated[str | None, Header(alias="X-Line-Signature")] = None,
) -> dict[str, str]:
    body = await request.body()
    if not verify_line_signature(body, x_line_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid LINE webhook signature.",
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in LINE webhook request.",
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LINE webhook request must contain an events array.",
        )

    for event in payload["events"]:
        if not isinstance(event, dict):
            continue
        reply_token = event.get("replyToken")
        if event.get("type") == "follow" and isinstance(reply_token, str) and reply_token:
            await run_in_threadpool(
                reply_to_line_message,
                reply_token,
                f"ยินดีต้อนรับค่ะ เลือกเมนูด้านล่างเพื่อติดตามออเดอร์\n{TRACKING_PROMPT}",
            )
            continue

        message = event.get("message")
        if (
            isinstance(message, dict)
            and message.get("type") == "text"
            and isinstance(reply_token, str)
            and reply_token
        ):
            text = message.get("text")
            source = event.get("source")
            user_id = source.get("userId") if isinstance(source, dict) else None
            if not isinstance(text, str):
                continue
            if text.strip() == "ติดตามสถานะออเดอร์":
                response_text = TRACKING_PROMPT
            elif text.strip() == "เช็กสถานะ":
                if not isinstance(user_id, str) or not user_id:
                    response_text = "ไม่พบ LINE User ID กรุณาเปิดแชตส่วนตัวกับบัญชีร้านแล้วลองใหม่"
                else:
                    linked_orders = list(
                        db.scalars(
                            select(Order)
                            .where(Order.line_user_id == user_id)
                            .order_by(Order.created_at.desc(), Order.id.desc())
                            .limit(5)
                        ).all()
                    )
                    if not linked_orders:
                        response_text = f"ยังไม่มีออเดอร์ที่ผูกกับ LINE นี้\n{TRACKING_PROMPT}"
                    else:
                        response_text = "\n\n".join(
                            order_status_message(db, order) for order in linked_orders
                        )
            else:
                reference = LINE_ORDER_REFERENCE.fullmatch(text.strip())
                if reference is None:
                    response_text = (
                        "สวัสดีค่ะ เลือกเมนูด้านล่างเพื่อติดตามออเดอร์ "
                        "หรือพิมพ์เลขออเดอร์พร้อมเบอร์โทรที่ใช้สั่ง\n"
                        "ตัวอย่าง: #123 0812345678"
                    )
                elif not isinstance(user_id, str) or not user_id:
                    response_text = "ไม่พบ LINE User ID กรุณาเปิดแชตส่วนตัวกับบัญชีร้านแล้วลองใหม่"
                else:
                    order = db.get(Order, int(reference.group(1)))
                    submitted_phone = "".join(filter(str.isdigit, reference.group(2)))
                    stored_phone = (
                        "".join(filter(str.isdigit, order.phone)) if order is not None else ""
                    )
                    if order is None or not secrets.compare_digest(submitted_phone, stored_phone):
                        response_text = "ไม่พบออเดอร์หรือเบอร์โทรไม่ตรงกับข้อมูลที่สั่ง กรุณาตรวจสอบแล้วลองใหม่"
                    elif order.line_user_id and not secrets.compare_digest(order.line_user_id, user_id):
                        response_text = "ออเดอร์นี้ผูกกับ LINE บัญชีอื่นแล้ว กรุณาติดต่อทางร้าน"
                    else:
                        order.line_user_id = user_id
                        db.commit()
                        response_text = (
                            "ผูกออเดอร์กับ LINE สำเร็จ\n"
                            f"{order_status_message(db, order)}\n"
                            "เมื่อร้านเปลี่ยนสถานะ ระบบจะแจ้งให้ทราบทาง LINE"
                        )
            await run_in_threadpool(reply_to_line_message, reply_token, response_text)

    return {"status": "ok"}


@app.get("/line/bot-info", dependencies=[Depends(require_admin)])
def line_bot_info() -> dict[str, str | bool | None]:
    return get_line_bot_info()
