-- =============================================================================
-- Fixture: enterprise (large)
-- Database: pg_mcp_test_large
-- Description: Enterprise data warehouse spanning HR, sales, marketing, finance.
--   2 schemas (public, reporting), 28 tables, 10 views, 3 materialized views,
--   7 ENUM types, 2 composite types, many indexes & foreign keys.
-- Data: seeded via seed.py (~5000 rows)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS reporting;

-- ---------------------------------------------------------------------------
-- Custom types
-- ---------------------------------------------------------------------------
CREATE TYPE employee_status AS ENUM ('active', 'on_leave', 'resigned', 'terminated');
CREATE TYPE department_type AS ENUM ('engineering', 'sales', 'marketing', 'finance', 'hr', 'operations', 'legal', 'executive');
CREATE TYPE order_channel AS ENUM ('online', 'offline', 'phone', 'partner', 'enterprise');
CREATE TYPE campaign_status AS ENUM ('draft', 'active', 'paused', 'completed', 'cancelled');
CREATE TYPE invoice_status AS ENUM ('draft', 'sent', 'paid', 'overdue', 'cancelled');
CREATE TYPE expense_category AS ENUM ('travel', 'office', 'software', 'hardware', 'marketing', 'training', 'meals', 'other');
CREATE TYPE lead_source AS ENUM ('website', 'referral', 'advertisement', 'social_media', 'trade_show', 'cold_call', 'partner');
CREATE TYPE priority_level AS ENUM ('low', 'medium', 'high', 'critical');

CREATE TYPE contact_info AS (
    email VARCHAR(200),
    phone VARCHAR(30)
);
COMMENT ON TYPE contact_info IS '联系信息复合类型';

CREATE TYPE money_type AS (
    amount   NUMERIC(14,2),
    currency VARCHAR(3)
);
COMMENT ON TYPE money_type IS '金额复合类型';

-- ===================================================================
-- PUBLIC SCHEMA
-- ===================================================================

-- ---------------------------------------------------------------------------
-- HR Domain
-- ---------------------------------------------------------------------------
CREATE TABLE departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    type        department_type NOT NULL,
    budget      money_type NOT NULL,
    manager_id  INT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE departments IS '部门';

CREATE TABLE employees (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(200) NOT NULL UNIQUE,
    contact       contact_info,
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    manager_id    INT REFERENCES employees(id) ON DELETE SET NULL,
    hire_date     DATE NOT NULL,
    status        employee_status NOT NULL DEFAULT 'active',
    salary        NUMERIC(10,2) NOT NULL CHECK (salary > 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE employees IS '员工';
COMMENT ON COLUMN employees.salary IS '月薪（税前）';

CREATE TABLE salaries (
    id          SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    amount      NUMERIC(10,2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    reason      VARCHAR(200)
);
COMMENT ON TABLE salaries IS '薪资调整记录';

CREATE TABLE attendance (
    id          SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    work_date   DATE NOT NULL,
    hours_worked NUMERIC(4,2) DEFAULT 8.00,
    is_overtime BOOLEAN NOT NULL DEFAULT false,
    note        VARCHAR(200),
    UNIQUE (employee_id, work_date)
);
COMMENT ON TABLE attendance IS '考勤记录';

-- ---------------------------------------------------------------------------
-- Customer Domain
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    id           SERIAL PRIMARY KEY,
    company_name VARCHAR(200),
    contact_name VARCHAR(100) NOT NULL,
    contact      contact_info,
    industry     VARCHAR(100),
    source       lead_source NOT NULL DEFAULT 'website',
    tier         VARCHAR(20) NOT NULL DEFAULT 'standard',
    assigned_to  INT REFERENCES employees(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ
);
COMMENT ON TABLE customers IS '企业客户';

CREATE TABLE customer_contacts (
    id          SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    role        VARCHAR(100),
    contact     contact_info,
    is_primary  BOOLEAN NOT NULL DEFAULT false
);
COMMENT ON TABLE customer_contacts IS '客户联系人';

-- ---------------------------------------------------------------------------
-- Product Domain
-- ---------------------------------------------------------------------------
CREATE TABLE product_categories (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    parent_id INT REFERENCES product_categories(id) ON DELETE SET NULL
);
COMMENT ON TABLE product_categories IS '产品分类';

CREATE TABLE suppliers (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    contact        contact_info,
    rating         NUMERIC(3,2) DEFAULT 0,
    contract_start DATE,
    contract_end   DATE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE suppliers IS '供应商';

CREATE TABLE products (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(300) NOT NULL,
    sku              VARCHAR(50) NOT NULL UNIQUE,
    category_id      INT NOT NULL REFERENCES product_categories(id) ON DELETE RESTRICT,
    supplier_id      INT REFERENCES suppliers(id) ON DELETE SET NULL,
    unit_price       NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    cost_price       NUMERIC(12,2) CHECK (cost_price >= 0),
    is_active        BOOLEAN NOT NULL DEFAULT true,
    min_order_qty    INT DEFAULT 1,
    unit             VARCHAR(20) DEFAULT '个',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE products IS '产品';
COMMENT ON COLUMN products.unit_price IS '销售单价';
COMMENT ON COLUMN products.cost_price IS '成本单价';

CREATE TABLE inventory (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
    quantity    INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reserved    INT NOT NULL DEFAULT 0,
    warehouse   VARCHAR(100),
    last_restock TIMESTAMPTZ
);
COMMENT ON TABLE inventory IS '库存';

CREATE TABLE purchase_orders (
    id          SERIAL PRIMARY KEY,
    supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    status      invoice_status NOT NULL DEFAULT 'draft',
    total       money_type NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ
);
COMMENT ON TABLE purchase_orders IS '采购订单';

CREATE TABLE purchase_order_items (
    id               SERIAL PRIMARY KEY,
    purchase_order_id INT NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id       INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity         INT NOT NULL CHECK (quantity > 0),
    unit_cost        NUMERIC(12,2) NOT NULL
);
COMMENT ON TABLE purchase_order_items IS '采购订单明细';

-- ---------------------------------------------------------------------------
-- Sales Domain
-- ---------------------------------------------------------------------------
CREATE TABLE sales_orders (
    id            SERIAL PRIMARY KEY,
    customer_id   INT REFERENCES customers(id) ON DELETE SET NULL,
    channel       order_channel NOT NULL,
    status        invoice_status NOT NULL DEFAULT 'draft',
    assigned_to   INT REFERENCES employees(id) ON DELETE SET NULL,
    total_amount  money_type NOT NULL,
    discount_pct  NUMERIC(5,2) DEFAULT 0,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at  TIMESTAMPTZ,
    delivered_at  TIMESTAMPTZ,
    invoiced_at   TIMESTAMPTZ
);
COMMENT ON TABLE sales_orders IS '销售订单';

CREATE TABLE sales_order_items (
    id            SERIAL PRIMARY KEY,
    sales_order_id INT NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
    product_id    INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12,2) NOT NULL,
    discount      NUMERIC(5,2) DEFAULT 0,
    subtotal      NUMERIC(12,2) NOT NULL
);
COMMENT ON TABLE sales_order_items IS '销售订单明细';

-- ---------------------------------------------------------------------------
-- Marketing Domain
-- ---------------------------------------------------------------------------
CREATE TABLE campaigns (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    status       campaign_status NOT NULL DEFAULT 'draft',
    channel      VARCHAR(50) NOT NULL,
    budget       money_type NOT NULL,
    start_date   DATE,
    end_date     DATE,
    target_audience VARCHAR(200),
    created_by   INT REFERENCES employees(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE campaigns IS '营销活动';

CREATE TABLE leads (
    id          SERIAL PRIMARY KEY,
    campaign_id INT REFERENCES campaigns(id) ON DELETE SET NULL,
    customer_id INT REFERENCES customers(id) ON DELETE SET NULL,
    source      lead_source NOT NULL,
    priority    priority_level NOT NULL DEFAULT 'medium',
    status      VARCHAR(20) NOT NULL DEFAULT 'new',
    estimated_value money_type,
    assigned_to INT REFERENCES employees(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at   TIMESTAMPTZ
);
COMMENT ON TABLE leads IS '销售线索';

-- ---------------------------------------------------------------------------
-- Finance Domain
-- ---------------------------------------------------------------------------
CREATE TABLE invoices (
    id            SERIAL PRIMARY KEY,
    sales_order_id INT REFERENCES sales_orders(id) ON DELETE SET NULL,
    customer_id   INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    status        invoice_status NOT NULL DEFAULT 'draft',
    amount        money_type NOT NULL,
    due_date      DATE NOT NULL,
    paid_date     DATE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE invoices IS '发票';

CREATE TABLE expenses (
    id          SERIAL PRIMARY KEY,
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    employee_id  INT REFERENCES employees(id) ON DELETE SET NULL,
    category     expense_category NOT NULL,
    amount       money_type NOT NULL,
    description  TEXT,
    receipt_no   VARCHAR(50),
    status       invoice_status NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMPTZ,
    approved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE expenses IS '报销';

CREATE TABLE budgets (
    id            SERIAL PRIMARY KEY,
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    fiscal_year   INT NOT NULL,
    quarter       INT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    planned       money_type NOT NULL,
    actual        money_type,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (department_id, fiscal_year, quarter)
);
COMMENT ON TABLE budgets IS '部门预算';

-- ---------------------------------------------------------------------------
-- Operational Domain
-- ---------------------------------------------------------------------------
CREATE TABLE support_tickets (
    id          SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id) ON DELETE SET NULL,
    subject     VARCHAR(300) NOT NULL,
    priority    priority_level NOT NULL DEFAULT 'medium',
    status      VARCHAR(20) NOT NULL DEFAULT 'open',
    assigned_to INT REFERENCES employees(id) ON DELETE SET NULL,
    resolution  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    closed_at   TIMESTAMPTZ
);
COMMENT ON TABLE support_tickets IS '工单';

CREATE TABLE activity_log (
    id          BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   INT NOT NULL,
    action      VARCHAR(50) NOT NULL,
    performed_by INT REFERENCES employees(id) ON DELETE SET NULL,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE activity_log IS '操作日志';

-- ===================================================================
-- REPORTING SCHEMA
-- ===================================================================

-- ---------------------------------------------------------------------------
-- Views (reporting schema)
-- ---------------------------------------------------------------------------
CREATE VIEW reporting.employee_summary AS
SELECT
    e.id, e.name, e.email, e.status,
    d.name AS department_name, d.type AS department_type,
    e.hire_date, e.salary,
    EXTRACT(YEAR FROM AGE(CURRENT_DATE, e.hire_date))::int AS years_of_service,
    COUNT(DISTINCT s.id) AS salary_adjustments
FROM employees e
JOIN departments d ON e.department_id = d.id
LEFT JOIN salaries s ON s.employee_id = e.id
GROUP BY e.id, e.name, e.email, e.status, d.name, d.type, e.hire_date, e.salary;
COMMENT ON VIEW reporting.employee_summary IS '员工摘要视图';

CREATE VIEW reporting.department_stats AS
SELECT
    d.id, d.name, d.type,
    d.budget,
    COUNT(e.id) AS headcount,
    AVG(e.salary) AS avg_salary,
    MIN(e.salary) AS min_salary,
    MAX(e.salary) AS max_salary,
    SUM(e.salary) AS total_monthly_payroll,
    COUNT(CASE WHEN e.status = 'active' THEN 1 END) AS active_count,
    COUNT(CASE WHEN e.hire_date >= CURRENT_DATE - INTERVAL '90 days' THEN 1 END) AS new_hires_90d
FROM departments d
LEFT JOIN employees e ON e.department_id = d.id
GROUP BY d.id, d.name, d.type, d.budget;
COMMENT ON VIEW reporting.department_stats IS '部门统计视图';

CREATE VIEW reporting.sales_summary AS
SELECT
    so.id AS order_id,
    so.channel, so.status,
    c.company_name AS customer_name,
    e.name AS sales_rep,
    so.total_amount,
    so.discount_pct,
    so.created_at, so.confirmed_at, so.delivered_at, so.invoiced_at,
    COALESCE(inv.status, 'draft') AS invoice_status
FROM sales_orders so
LEFT JOIN customers c ON so.customer_id = c.id
LEFT JOIN employees e ON so.assigned_to = e.id
LEFT JOIN invoices inv ON inv.sales_order_id = so.id;
COMMENT ON VIEW reporting.sales_summary IS '销售摘要视图';

CREATE VIEW reporting.customer_lifetime_value AS
SELECT
    c.id AS customer_id,
    c.company_name,
    c.industry,
    c.source,
    c.tier,
    e.name AS account_manager,
    COUNT(DISTINCT so.id) AS total_orders,
    COALESCE(SUM(soi.subtotal), 0) AS total_revenue,
    COALESCE(AVG(soi.subtotal), 0) AS avg_order_value,
    MIN(so.created_at) AS first_order_date,
    MAX(so.created_at) AS last_order_date,
    COALESCE(SUM((inv.amount).amount), 0) AS total_invoiced,
    COUNT(DISTINCT st.id) AS total_tickets
FROM customers c
LEFT JOIN employees e ON c.assigned_to = e.id
LEFT JOIN sales_orders so ON so.customer_id = c.id AND so.status NOT IN ('draft', 'cancelled')
LEFT JOIN sales_order_items soi ON soi.sales_order_id = so.id
LEFT JOIN invoices inv ON inv.customer_id = c.id AND inv.status = 'paid'
LEFT JOIN support_tickets st ON st.customer_id = c.id
GROUP BY c.id, c.company_name, c.industry, c.source, c.tier, e.name;
COMMENT ON VIEW reporting.customer_lifetime_value IS '客户生命周期价值视图';

CREATE VIEW reporting.campaign_performance AS
SELECT
    camp.id, camp.name, camp.channel, camp.status,
    camp.budget,
    camp.start_date, camp.end_date,
    COUNT(DISTINCT l.id) AS leads_generated,
    COUNT(DISTINCT CASE WHEN l.status = 'won' THEN l.id END) AS leads_converted,
    COALESCE(SUM((l.estimated_value).amount), 0) AS total_pipeline_value,
    COALESCE(COUNT(DISTINCT l.id)::numeric / NULLIF(COUNT(DISTINCT CASE WHEN l.status = 'won' THEN l.id END), 0), 0) AS cost_per_conversion
FROM campaigns camp
LEFT JOIN leads l ON l.campaign_id = camp.id
GROUP BY camp.id, camp.name, camp.channel, camp.status, camp.budget, camp.start_date, camp.end_date;
COMMENT ON VIEW reporting.campaign_performance IS '营销活动效果视图';

CREATE VIEW reporting.financial_summary AS
SELECT
    d.name AS department,
    b.fiscal_year, b.quarter,
    b.planned,
    COALESCE(b.actual, ROW(0, 'CNY')::money_type) AS actual,
    CASE WHEN b.actual IS NOT NULL
         THEN (b.planned).amount - (b.actual).amount
         ELSE (b.planned).amount
    END AS variance
FROM budgets b
JOIN departments d ON b.department_id = d.id
ORDER BY d.name, b.fiscal_year, b.quarter;
COMMENT ON VIEW reporting.financial_summary IS '财务概览视图';

CREATE VIEW reporting.inventory_status AS
SELECT
    p.id, p.name, p.sku, p.unit_price,
    pc.name AS category,
    s.name AS supplier,
    i.quantity AS on_hand,
    i.reserved,
    i.quantity - i.reserved AS available,
    CASE
        WHEN i.quantity - i.reserved < 10 THEN 'low_stock'
        WHEN i.quantity - i.reserved < 50 THEN 'moderate'
        ELSE 'in_stock'
    END AS stock_level,
    i.warehouse,
    i.last_restock
FROM products p
JOIN product_categories pc ON p.category_id = pc.id
LEFT JOIN suppliers s ON p.supplier_id = s.id
LEFT JOIN inventory i ON i.product_id = p.id
WHERE p.is_active = true;
COMMENT ON VIEW reporting.inventory_status IS '库存状态视图';

CREATE VIEW reporting.top_products AS
SELECT
    p.id, p.name, p.sku,
    pc.name AS category,
    SUM(soi.quantity) AS total_units_sold,
    SUM(soi.subtotal) AS total_revenue,
    COUNT(DISTINCT soi.sales_order_id) AS order_count,
    AVG(soi.unit_price) AS avg_selling_price,
    p.cost_price,
    SUM(soi.subtotal) - SUM(soi.quantity * p.cost_price) AS gross_profit,
    ROUND(
        (SUM(soi.subtotal) - SUM(soi.quantity * p.cost_price)) / NULLIF(SUM(soi.subtotal), 0) * 100, 2
    ) AS gross_margin_pct
FROM products p
JOIN product_categories pc ON p.category_id = pc.id
JOIN sales_order_items soi ON soi.product_id = p.id
JOIN sales_orders so ON so.id = soi.sales_order_id AND so.status NOT IN ('draft', 'cancelled')
GROUP BY p.id, p.name, p.sku, pc.name, p.cost_price
ORDER BY total_revenue DESC;
COMMENT ON VIEW reporting.top_products IS '热销产品排行视图';

CREATE VIEW reporting.expense_report AS
SELECT
    d.name AS department,
    e.name AS employee,
    ex.category,
    ex.amount,
    ex.description,
    ex.status,
    ex.submitted_at,
    ex.approved_at
FROM expenses ex
JOIN departments d ON ex.department_id = d.id
LEFT JOIN employees e ON ex.employee_id = e.id
ORDER BY ex.submitted_at DESC NULLS LAST;
COMMENT ON VIEW reporting.expense_report IS '报销报表视图';

CREATE VIEW reporting.support_metrics AS
SELECT
    st.priority,
    st.status,
    c.company_name AS customer,
    e.name AS assigned_to,
    st.subject,
    st.created_at,
    st.resolved_at,
    st.closed_at,
    EXTRACT(EPOCH FROM (COALESCE(st.resolved_at, st.closed_at, now()) - st.created_at)) / 3600 AS hours_to_resolve
FROM support_tickets st
LEFT JOIN customers c ON st.customer_id = c.id
LEFT JOIN employees e ON st.assigned_to = e.id;
COMMENT ON VIEW reporting.support_metrics IS '客服指标视图';

-- ---------------------------------------------------------------------------
-- Materialized views (reporting schema)
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW reporting.monthly_sales_report AS
SELECT
    DATE_TRUNC('month', so.created_at) AS month,
    so.channel,
    COUNT(DISTINCT so.id) AS order_count,
    COUNT(DISTINCT so.customer_id) AS unique_customers,
    SUM(soi.quantity) AS units_sold,
    SUM(soi.subtotal) AS revenue,
    AVG(soi.subtotal) AS avg_order_value,
    SUM(so.discount_pct * (so.total_amount).amount / 100) AS total_discount
FROM sales_orders so
JOIN sales_order_items soi ON soi.sales_order_id = so.id
WHERE so.status NOT IN ('draft', 'cancelled')
GROUP BY DATE_TRUNC('month', so.created_at), so.channel
ORDER BY month DESC, channel;
COMMENT ON MATERIALIZED VIEW reporting.monthly_sales_report IS '月度销售报表';

CREATE MATERIALIZED VIEW reporting.quarterly_costs AS
SELECT
    b.fiscal_year, b.quarter,
    d.name AS department, d.type AS department_type,
    b.planned AS budget,
    COALESCE(SUM((ex.amount).amount), 0) AS actual_expenses,
    COALESCE(SUM(e.salary), 0) AS payroll,
    COALESCE(SUM((ex.amount).amount), 0) + COALESCE(SUM(e.salary), 0) AS total_cost
FROM budgets b
JOIN departments d ON b.department_id = d.id
LEFT JOIN expenses ex ON ex.department_id = d.id
    AND EXTRACT(YEAR FROM ex.submitted_at) = b.fiscal_year
    AND EXTRACT(QUARTER FROM ex.submitted_at) = b.quarter
    AND ex.status = 'paid'
LEFT JOIN employees e ON e.department_id = d.id AND e.status = 'active'
GROUP BY b.fiscal_year, b.quarter, d.name, d.type, b.planned
ORDER BY b.fiscal_year, b.quarter, d.name;
COMMENT ON MATERIALIZED VIEW reporting.quarterly_costs IS '季度成本报表';

CREATE MATERIALIZED VIEW reporting.daily_lead_funnel AS
SELECT
    DATE(l.created_at) AS date,
    l.source,
    l.priority,
    COUNT(*) AS total_leads,
    COUNT(CASE WHEN l.status = 'contacted' THEN 1 END) AS contacted,
    COUNT(CASE WHEN l.status = 'qualified' THEN 1 END) AS qualified,
    COUNT(CASE WHEN l.status = 'proposal' THEN 1 END) AS proposal_sent,
    COUNT(CASE WHEN l.status = 'won' THEN 1 END) AS won,
    COUNT(CASE WHEN l.status = 'lost' THEN 1 END) AS lost,
    COALESCE(SUM((l.estimated_value).amount), 0) AS pipeline_value
FROM leads l
GROUP BY DATE(l.created_at), l.source, l.priority
ORDER BY date DESC;
COMMENT ON MATERIALIZED VIEW reporting.daily_lead_funnel IS '每日线索漏斗';

-- ---------------------------------------------------------------------------
-- Indexes (public schema)
-- ---------------------------------------------------------------------------
CREATE INDEX idx_employees_dept     ON employees(department_id);
CREATE INDEX idx_employees_manager  ON employees(manager_id);
CREATE INDEX idx_employees_status   ON employees(status);
CREATE INDEX idx_employees_email    ON employees(email);
CREATE INDEX idx_employees_hire     ON employees(hire_date);
CREATE INDEX idx_salaries_emp       ON salaries(employee_id);
CREATE INDEX idx_salaries_effective ON salaries(effective_from);
CREATE INDEX idx_attendance_emp     ON attendance(employee_id);
CREATE INDEX idx_attendance_date    ON attendance(work_date);
CREATE INDEX idx_customers_source   ON customers(source);
CREATE INDEX idx_customers_tier     ON customers(tier);
CREATE INDEX idx_customers_assigned ON customers(assigned_to);
CREATE INDEX idx_customer_contacts_cust ON customer_contacts(customer_id);
CREATE INDEX idx_products_category  ON products(category_id);
CREATE INDEX idx_products_supplier  ON products(supplier_id);
CREATE INDEX idx_products_sku       ON products(sku);
CREATE INDEX idx_products_active    ON products(is_active);
CREATE INDEX idx_inventory_product  ON inventory(product_id);
CREATE INDEX idx_sales_orders_cust  ON sales_orders(customer_id);
CREATE INDEX idx_sales_orders_channel ON sales_orders(channel);
CREATE INDEX idx_sales_orders_status ON sales_orders(status);
CREATE INDEX idx_sales_orders_assigned ON sales_orders(assigned_to);
CREATE INDEX idx_sales_orders_created ON sales_orders(created_at);
CREATE INDEX idx_sales_order_items_order ON sales_order_items(sales_order_id);
CREATE INDEX idx_sales_order_items_product ON sales_order_items(product_id);
CREATE INDEX idx_campaigns_status   ON campaigns(status);
CREATE INDEX idx_leads_campaign     ON leads(campaign_id);
CREATE INDEX idx_leads_source       ON leads(source);
CREATE INDEX idx_leads_assigned     ON leads(assigned_to);
CREATE INDEX idx_leads_status       ON leads(status);
CREATE INDEX idx_invoices_customer  ON invoices(customer_id);
CREATE INDEX idx_invoices_status    ON invoices(status);
CREATE INDEX idx_expenses_dept      ON expenses(department_id);
CREATE INDEX idx_expenses_category  ON expenses(category);
CREATE INDEX idx_expenses_status    ON expenses(status);
CREATE INDEX idx_tickets_customer   ON support_tickets(customer_id);
CREATE INDEX idx_tickets_assigned   ON support_tickets(assigned_to);
CREATE INDEX idx_tickets_status     ON support_tickets(status);
CREATE INDEX idx_activity_entity    ON activity_log(entity_type, entity_id);
CREATE INDEX idx_activity_created   ON activity_log(created_at);
