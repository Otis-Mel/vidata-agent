-- ViDataAgent: schema thương mại điện tử Việt Nam (dữ liệu giả lập)
-- Tiền tệ: VND (BIGINT). Mọi TIMESTAMP lưu theo UTC (giờ VN = UTC+7).

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name_vi     VARCHAR NOT NULL,
    parent_id   INTEGER               -- NULL = danh mục gốc
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name   VARCHAR NOT NULL,
    email       VARCHAR,
    province    VARCHAR,              -- BẪY: nhiều cách viết (HCM, TP.HCM, Sài Gòn...)
    signup_date DATE NOT NULL
);

CREATE TABLE sellers (
    seller_id   INTEGER PRIMARY KEY,
    shop_name   VARCHAR NOT NULL,
    province    VARCHAR,
    is_mall     BOOLEAN NOT NULL,     -- shop chính hãng/Mall
    joined_date DATE NOT NULL
);

CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY,
    seller_id   INTEGER NOT NULL REFERENCES sellers(seller_id),
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    name        VARCHAR NOT NULL,
    price       BIGINT NOT NULL,      -- giá niêm yết hiện tại
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE vouchers (
    voucher_id        INTEGER PRIMARY KEY,
    code              VARCHAR NOT NULL,
    discount_type     VARCHAR NOT NULL,   -- 'percent' | 'fixed'
    value             BIGINT NOT NULL,    -- % hoặc số tiền VND
    min_order_value   BIGINT NOT NULL,
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL
);

CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    order_ts     TIMESTAMP NOT NULL,      -- UTC
    status       VARCHAR NOT NULL,        -- completed | cancelled | returned | delivering
    voucher_id   INTEGER REFERENCES vouchers(voucher_id),
    shipping_fee BIGINT NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    BIGINT NOT NULL         -- giá tại thời điểm mua (có thể khác products.price)
);

-- BẪY: 1 đơn có thể có NHIỀU dòng payments (vd: ví + COD) -> join nhân dòng
CREATE TABLE payments (
    payment_id BIGINT PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(order_id),
    method     VARCHAR NOT NULL,          -- COD | momo | vnpay | card
    amount     BIGINT NOT NULL,
    paid_ts    TIMESTAMP,                 -- NULL nếu chưa thu (COD chưa giao / đơn hủy)
    status     VARCHAR NOT NULL           -- paid | pending | refunded
);

CREATE TABLE shipments (
    shipment_id  BIGINT PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(order_id),
    carrier      VARCHAR NOT NULL,        -- GHN | GHTK | ViettelPost | JT
    shipped_ts   TIMESTAMP,
    delivered_ts TIMESTAMP,               -- NULL nếu chưa giao thành công
    status       VARCHAR NOT NULL         -- delivered | in_transit | failed | returned
);

CREATE TABLE reviews (
    review_id     BIGINT PRIMARY KEY,
    order_item_id BIGINT NOT NULL REFERENCES order_items(order_item_id),
    rating        INTEGER NOT NULL,       -- 1..5
    created_at    TIMESTAMP NOT NULL
);
