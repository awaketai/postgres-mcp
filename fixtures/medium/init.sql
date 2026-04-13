-- =============================================================================
-- Fixture: ecommerce (medium)
-- Database: pg_mcp_test_medium
-- Description: A mid-size e-commerce platform.
--   12 tables, 4 views, 1 materialized view, 4 ENUM types, 1 composite type,
--   many indexes & foreign keys.
-- Data: seeded via seed.py (~500 rows)
-- =============================================================================

CREATE TYPE order_status AS ENUM (
    'pending', 'paid', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded'
);

CREATE TYPE payment_method AS ENUM (
    'credit_card', 'debit_card', 'alipay', 'wechat_pay', 'bank_transfer', 'cash_on_delivery'
);

CREATE TYPE user_role AS ENUM (
    'customer', 'admin', 'vendor'
);

CREATE TYPE product_status AS ENUM (
    'active', 'inactive', 'out_of_stock', 'discontinued'
);

CREATE TYPE money_value AS (
    amount   NUMERIC(12,2),
    currency VARCHAR(3)
);
COMMENT ON TYPE money_value IS '复合货币类型';

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(200) NOT NULL UNIQUE,
    role          user_role    NOT NULL DEFAULT 'customer',
    phone         VARCHAR(20),
    is_active     BOOLEAN      NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
COMMENT ON TABLE users IS '平台用户';

CREATE TABLE addresses (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    province    VARCHAR(50) NOT NULL,
    city        VARCHAR(50) NOT NULL,
    district    VARCHAR(50),
    street      VARCHAR(200) NOT NULL,
    postal_code VARCHAR(10),
    is_default  BOOLEAN NOT NULL DEFAULT false
);
COMMENT ON TABLE addresses IS '用户收货地址';

CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id   INT REFERENCES categories(id) ON DELETE SET NULL
);
COMMENT ON TABLE categories IS '商品分类（支持层级）';

CREATE TABLE vendors (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    contact_email VARCHAR(200),
    rating        NUMERIC(3,2) DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE vendors IS '供应商';

CREATE TABLE products (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(300) NOT NULL,
    vendor_id      INT REFERENCES vendors(id) ON DELETE SET NULL,
    category_id    INT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    price          NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    original_price NUMERIC(12,2) CHECK (original_price >= 0),
    status         product_status NOT NULL DEFAULT 'active',
    description    TEXT,
    weight_kg      NUMERIC(6,2),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);
COMMENT ON TABLE products IS '商品信息';
COMMENT ON COLUMN products.price IS '当前售价';
COMMENT ON COLUMN products.original_price IS '原价（划线价）';

CREATE TABLE product_tags (
    id         SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tag        VARCHAR(50) NOT NULL,
    UNIQUE (product_id, tag)
);
COMMENT ON TABLE product_tags IS '商品标签';

CREATE TABLE inventory (
    id         SERIAL PRIMARY KEY,
    product_id INT NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
    quantity   INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reserved   INT NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    warehouse  VARCHAR(100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE inventory IS '库存信息';

CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    address_id   INT NOT NULL REFERENCES addresses(id),
    status       order_status NOT NULL DEFAULT 'pending',
    total_amount money_value NOT NULL,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at      TIMESTAMPTZ,
    shipped_at   TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);
COMMENT ON TABLE orders IS '订单主表';

CREATE TABLE order_items (
    id           SERIAL PRIMARY KEY,
    order_id     INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id   INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    product_name VARCHAR(300) NOT NULL,
    unit_price   NUMERIC(12,2) NOT NULL,
    quantity     INT NOT NULL CHECK (quantity > 0),
    subtotal     NUMERIC(12,2) NOT NULL
);
COMMENT ON TABLE order_items IS '订单明细';

CREATE TABLE payments (
    id             SERIAL PRIMARY KEY,
    order_id       INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    method         payment_method NOT NULL,
    amount         money_value NOT NULL,
    transaction_id VARCHAR(100),
    status         VARCHAR(20) NOT NULL DEFAULT 'pending',
    paid_at        TIMESTAMPTZ
);
COMMENT ON TABLE payments IS '支付记录';

CREATE TABLE reviews (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title       VARCHAR(200),
    content     TEXT,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE reviews IS '商品评论';

-- Indexes
CREATE INDEX idx_users_email       ON users(email);
CREATE INDEX idx_users_role        ON users(role);
CREATE INDEX idx_users_created_at  ON users(created_at);
CREATE INDEX idx_addresses_user_id ON addresses(user_id);
CREATE INDEX idx_categories_parent ON categories(parent_id);
CREATE INDEX idx_products_vendor   ON products(vendor_id);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_status   ON products(status);
CREATE INDEX idx_products_price    ON products(price);
CREATE INDEX idx_products_created  ON products(created_at);
CREATE INDEX idx_product_tags_prod ON product_tags(product_id);
CREATE INDEX idx_product_tags_tag  ON product_tags(tag);
CREATE INDEX idx_orders_user       ON orders(user_id);
CREATE INDEX idx_orders_status     ON orders(status);
CREATE INDEX idx_orders_created    ON orders(created_at);
CREATE INDEX idx_orders_paid_at    ON orders(paid_at);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_prod  ON order_items(product_id);
CREATE INDEX idx_payments_order    ON payments(order_id);
CREATE INDEX idx_payments_status   ON payments(status);
CREATE INDEX idx_reviews_product   ON reviews(product_id);
CREATE INDEX idx_reviews_user      ON reviews(user_id);
CREATE INDEX idx_reviews_rating    ON reviews(rating);

-- Views
CREATE VIEW product_catalog AS
SELECT
    p.id,
    p.name,
    c.name AS category_name,
    v.name AS vendor_name,
    p.price,
    p.original_price,
    ROUND((1 - p.price / NULLIF(p.original_price, 0)) * 100, 1) AS discount_pct,
    p.status,
    COALESCE(i.quantity - i.reserved, 0) AS available_stock,
    COALESCE(ra.avg_rating, 0) AS avg_rating,
    COALESCE(ra.review_count, 0) AS review_count,
    STRING_AGG(DISTINCT pt.tag, ', ' ORDER BY pt.tag) AS tags
FROM products p
JOIN categories c ON p.category_id = c.id
LEFT JOIN vendors v ON p.vendor_id = v.id
LEFT JOIN inventory i ON p.id = i.product_id
LEFT JOIN (
    SELECT product_id, ROUND(AVG(rating), 1) AS avg_rating, COUNT(*) AS review_count
    FROM reviews GROUP BY product_id
) ra ON ra.product_id = p.id
LEFT JOIN product_tags pt ON pt.product_id = p.id
WHERE p.status = 'active'
GROUP BY p.id, p.name, c.name, v.name, p.price, p.original_price,
         p.status, i.quantity, i.reserved, ra.avg_rating, ra.review_count;
COMMENT ON VIEW product_catalog IS '商品目录视图';

CREATE VIEW order_summary AS
SELECT
    o.id AS order_id,
    o.user_id,
    u.username,
    o.status,
    o.total_amount,
    (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.id) AS item_count,
    (SELECT COALESCE(SUM(oi.quantity), 0) FROM order_items oi WHERE oi.order_id = o.id) AS total_quantity,
    o.created_at, o.paid_at, o.shipped_at, o.delivered_at,
    EXTRACT(EPOCH FROM (o.delivered_at - o.created_at)) / 3600 AS delivery_hours
FROM orders o
JOIN users u ON o.user_id = u.id;
COMMENT ON VIEW order_summary IS '订单摘要视图';

CREATE VIEW customer_stats AS
SELECT
    u.id AS user_id, u.username, u.email,
    COUNT(DISTINCT o.id) AS order_count,
    COALESCE(SUM((oi.subtotal)), 0) AS total_spent,
    COALESCE(AVG((oi.subtotal)), 0) AS avg_order_value,
    MIN(o.created_at) AS first_order,
    MAX(o.created_at) AS last_order,
    COUNT(DISTINCT r.id) AS reviews_written
FROM users u
LEFT JOIN orders o ON o.user_id = u.id AND o.status NOT IN ('cancelled', 'refunded')
LEFT JOIN order_items oi ON oi.order_id = o.id
LEFT JOIN reviews r ON r.user_id = u.id
GROUP BY u.id, u.username, u.email;
COMMENT ON VIEW customer_stats IS '客户统计视图';

CREATE VIEW vendor_performance AS
SELECT
    v.id AS vendor_id, v.name AS vendor_name,
    COUNT(DISTINCT p.id) AS product_count,
    COUNT(DISTINCT CASE WHEN p.status = 'active' THEN p.id END) AS active_products,
    COALESCE(AVG(p.price), 0) AS avg_product_price
FROM vendors v
LEFT JOIN products p ON p.vendor_id = v.id
GROUP BY v.id, v.name;
COMMENT ON VIEW vendor_performance IS '供应商表现视图';

-- Materialized view
CREATE MATERIALIZED VIEW daily_sales AS
SELECT
    DATE(o.created_at) AS sale_date,
    COUNT(DISTINCT o.id) AS order_count,
    COUNT(DISTINCT o.user_id) AS unique_customers,
    SUM(oi.quantity) AS items_sold,
    SUM(oi.subtotal) AS total_revenue,
    AVG(oi.subtotal) AS avg_item_price
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status NOT IN ('cancelled', 'refunded')
GROUP BY DATE(o.created_at)
ORDER BY sale_date DESC;
COMMENT ON MATERIALIZED VIEW daily_sales IS '每日销售汇总';
