ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS line_user_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS ix_orders_line_user_id
    ON orders (line_user_id)
    WHERE line_user_id IS NOT NULL;
