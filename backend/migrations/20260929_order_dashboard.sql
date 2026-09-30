UPDATE orders
SET status = CASE
    WHEN status IN ('new', 'accepted') THEN 'pending'
    WHEN status = 'ready' THEN 'cooking'
    ELSE status
END
WHERE status IN ('new', 'accepted', 'ready');

UPDATE orders SET status = 'pending' WHERE status IS NULL;

ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;

ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status;
ALTER TABLE orders
    ADD CONSTRAINT ck_orders_status
    CHECK (status IN ('pending', 'cooking', 'completed', 'cancelled'));
