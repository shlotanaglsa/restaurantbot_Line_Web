from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MenuOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal | None


class MenuItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price: Decimal
    category: str
    available: bool
    options: list[MenuOptionRead]


class MenuOptionWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)


class MenuItemWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    category: str = Field(min_length=1, max_length=100)
    available: bool = True
    options: list[MenuOptionWrite] = Field(default_factory=list, max_length=50)


class OrderItemCreate(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)
    option_ids: list[int] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=50)
    address: str = Field(min_length=1, max_length=10000)
    note: str | None = Field(default=None, max_length=2000)
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)


class OrderItemOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    option_name: str
    option_price: Decimal


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    quantity: int
    unit_price: Decimal
    note: str | None
    subtotal: Decimal
    options: list[OrderItemOptionRead]


class OrderStatus(str, Enum):
    pending = "pending"
    cooking = "cooking"
    completed = "completed"
    cancelled = "cancelled"


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_name: str
    phone: str
    address: str
    note: str | None
    line_linked: bool = False
    total_price: Decimal
    status: OrderStatus
    created_at: datetime
    items: list[OrderItemRead]


class DailySalesRead(BaseModel):
    date: date
    total_sales: Decimal
    order_count: int


class DashboardStats(BaseModel):
    total_orders: int
    pending_orders: int
    cooking_orders: int
    completed_orders: int
    total_sales: Decimal
    today_sales: Decimal
    daily_sales: list[DailySalesRead]


class SalesPeriod(str, Enum):
    daily = "daily"
    monthly = "monthly"
    yearly = "yearly"


class SalesBucket(BaseModel):
    label: str
    total_sales: Decimal
    order_count: int


class SalesPeriodSummary(BaseModel):
    period: SalesPeriod
    start_date: date
    end_date: date
    total_sales: Decimal
    order_count: int
    buckets: list[SalesBucket]
