#!/usr/bin/env python3
"""Seed data for the large (enterprise) fixture database.

Generates ~5000 rows across HR, sales, marketing, finance, and operations domains.
  - 8 departments, 120 employees, 300 attendance, 200 salary records
  - 100 customers, 200 customer contacts
  - 15 product categories, 80 products, 20 suppliers, 80 inventory
  - 500 sales orders, 1200 order items, 30 purchase orders
  - 20 campaigns, 300 leads
  - 400 invoices, 300 expenses, 40 budgets
  - 150 support tickets, 500 activity log entries
"""

from __future__ import annotations

import os
import random
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras
from faker import Faker

SEED = 42
DB_URL = os.environ.get(
    "PG_FIXTURE_URL",
    "postgresql://postgres@localhost/pg_mcp_test_large",
)

fake = Faker("zh_CN")
Faker.seed(SEED)
random.seed(SEED)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    ("工程部", "engineering", 5_000_000),
    ("销售部", "sales", 3_000_000),
    ("市场部", "marketing", 2_500_000),
    ("财务部", "finance", 1_500_000),
    ("人力资源部", "hr", 1_000_000),
    ("运营部", "operations", 2_000_000),
    ("法务部", "legal", 800_000),
    ("总裁办", "executive", 1_200_000),
]

INDUSTRIES = [
    "互联网", "金融", "制造业", "零售", "教育", "医疗",
    "物流", "房地产", "能源", "通信", "传媒", "咨询",
]
CUSTOMER_TIERS = ["standard", "silver", "gold", "platinum", "enterprise"]
LEAD_SOURCES = ["website", "referral", "advertisement", "social_media", "trade_show", "cold_call", "partner"]
ORDER_CHANNELS = ["online", "offline", "phone", "partner", "enterprise"]
EXPENSE_CATS = ["travel", "office", "software", "hardware", "marketing", "training", "meals", "other"]
CAMPAIGN_CHANNELS = ["email", "search_ads", "social", "content", "event", "offline"]
LEAD_STATUSES = ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
TICKET_STATUSES = ["open", "in_progress", "pending_customer", "resolved", "closed"]
PRODUCT_CATEGORIES = [
    (1, "软件产品", None),
    (2, "CRM 系统", 1),
    (3, "ERP 系统", 1),
    (4, "数据分析平台", 1),
    (5, "云服务", 1),
    (6, "硬件设备", None),
    (7, "服务器", 6),
    (8, "网络设备", 6),
    (9, "安全设备", 6),
    (10, "终端设备", 6),
    (11, "技术服务", None),
    (12, "实施服务", 11),
    (13, "培训服务", 11),
    (14, "运维服务", 11),
    (15, "咨询服务", 11),
]

PRODUCT_NAMES = [
    ("企业版 CRM 系统", 2, 280000, 120000, "套"),
    ("标准版 CRM 系统", 2, 98000, 35000, "套"),
    ("ERP 生产管理模块", 3, 350000, 150000, "套"),
    ("ERP 财务管理模块", 3, 180000, 75000, "套"),
    ("ERP 供应链模块", 3, 220000, 95000, "套"),
    ("数据可视化平台", 4, 150000, 60000, "套"),
    ("实时数据分析引擎", 4, 250000, 100000, "套"),
    ("云主机 标准型", 5, 3600, 1800, "台/月"),
    ("云主机 高性能型", 5, 8400, 4200, "台/月"),
    ("对象存储服务", 5, 0.12, 0.04, "GB/月"),
    ("机架式服务器 R530", 7, 45000, 32000, "台"),
    ("塔式服务器 T350", 7, 28000, 18000, "台"),
    ("核心交换机 S5735", 8, 18000, 11000, "台"),
    ("无线 AP WA6320", 8, 2800, 1500, "台"),
    ("下一代防火墙", 9, 35000, 22000, "台"),
    ("Web 应用防火墙", 9, 22000, 13000, "台"),
    ("商务笔记本 ThinkPad T14", 10, 8500, 6500, "台"),
    ("商务笔记本 ThinkPad X1", 10, 12000, 9000, "台"),
    ("27 寸 4K 显示器", 10, 3200, 2100, "台"),
    ("ERP 实施服务", 12, 150000, 80000, "项目"),
    ("CRM 实施服务", 12, 80000, 40000, "项目"),
    ("系统培训服务", 13, 15000, 6000, "人天"),
    ("高级培训服务", 13, 30000, 12000, "人天"),
    ("基础运维服务", 14, 60000, 30000, "年"),
    ("高级运维服务", 14, 180000, 90000, "年"),
    ("数字化转型咨询", 15, 200000, 80000, "项目"),
    ("IT 架构咨询服务", 15, 150000, 60000, "项目"),
    ("安全评估服务", 15, 80000, 35000, "项目"),
]

WAREHOUSES = ["北京仓", "上海仓", "广州仓", "成都仓"]


def _rand_price(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def _date_between(d1: str | date, d2: str | date) -> date:
    if isinstance(d1, str):
        d1 = date.fromisoformat(d1)
    if isinstance(d2, str):
        d2 = date.fromisoformat(d2)
    delta = (d2 - d1).days
    return d1 + timedelta(days=random.randint(0, max(delta, 1)))


def seed(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        now = date.today()

        # ==================================================================
        # Departments
        # ==================================================================
        dept_ids: list[int] = []
        for name, dtype, budget in DEPARTMENTS:
            cur.execute(
                """INSERT INTO departments (name, type, budget) VALUES (%s, %s, %s)
                   RETURNING id""",
                (name, dtype, (budget, "CNY")),
            )
            dept_ids.append(cur.fetchone()[0])

        # ==================================================================
        # Employees (~120)
        # ==================================================================
        emp_ids: list[int] = []
        emp_dept: dict[int, int] = {}
        # Distribute: engineering 35, sales 25, marketing 15, finance 12,
        #             hr 10, operations 12, legal 6, executive 5
        dept_counts = [35, 25, 15, 12, 10, 12, 6, 5]
        for dept_idx, count in enumerate(dept_counts):
            for _ in range(count):
                salary = _rand_price(
                    {"engineering": 15000, "sales": 12000, "marketing": 11000,
                     "finance": 13000, "hr": 10000, "operations": 10000,
                     "legal": 18000, "executive": 25000}[DEPARTMENTS[dept_idx][1]],
                    {"engineering": 60000, "sales": 45000, "marketing": 35000,
                     "finance": 40000, "hr": 30000, "operations": 30000,
                     "legal": 55000, "executive": 80000}[DEPARTMENTS[dept_idx][1]],
                )
                hire_date = _date_between("2018-01-01", now)
                status = random.choices(
                    ["active", "on_leave", "resigned", "terminated"],
                    weights=[85, 5, 8, 2],
                )[0]
                cur.execute(
                    """INSERT INTO employees (name, email, contact, department_id,
                           hire_date, status, salary)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (
                        fake.name(),
                        fake.email(),
                        (fake.email(), fake.phone_number()),
                        dept_ids[dept_idx],
                        hire_date,
                        status,
                        salary,
                    ),
                )
                eid = cur.fetchone()[0]
                emp_ids.append(eid)
                emp_dept[eid] = dept_ids[dept_idx]

        # Set department managers
        for dept_idx, did in enumerate(dept_ids):
            dept_emps = [e for e, d in emp_dept.items() if d == did and e in emp_ids]
            if dept_emps:
                cur.execute("UPDATE departments SET manager_id = %s WHERE id = %s",
                            (random.choice(dept_emps), did))

        # Set some employee managers (each employee's manager is a senior in same dept)
        for did in dept_ids:
            dept_emps = [e for e, d in emp_dept.items() if d == did]
            if len(dept_emps) > 1:
                managers = random.sample(dept_emps, max(1, len(dept_emps) // 5))
                for emp in dept_emps:
                    if emp not in managers:
                        cur.execute(
                            "UPDATE employees SET manager_id = %s WHERE id = %s",
                            (random.choice(managers), emp),
                        )

        # ==================================================================
        # Salaries (~200 records)
        # ==================================================================
        active_emps = [e for e in emp_ids]
        salary_count = 0
        for emp in random.sample(active_emps, min(200, len(active_emps))):
            n_adjustments = random.choices([1, 2, 3], weights=[50, 40, 10])[0]
            base_date = _date_between("2018-01-01", "2024-01-01")
            for j in range(n_adjustments):
                eff_from = base_date + timedelta(days=j * 365)
                eff_to = (eff_from + timedelta(days=365)) if j < n_adjustments - 1 else None
                cur.execute(
                    """INSERT INTO salaries (employee_id, amount, effective_from, effective_to, reason)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (emp, _rand_price(10000, 60000), eff_from, eff_to,
                     random.choice(["年度调薪", "晋升调薪", "绩效调薪", "入职定薪"])),
                )
                salary_count += 1

        # ==================================================================
        # Attendance (~300 records)
        # ==================================================================
        attendance_count = 0
        for emp in random.sample(active_emps, min(80, len(active_emps))):
            n_days = random.randint(2, 6)
            for _ in range(n_days):
                work_date = _date_between("2025-10-01", "2026-03-31")
                try:
                    cur.execute(
                        """INSERT INTO attendance (employee_id, work_date, hours_worked, is_overtime, note)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (emp, work_date,
                         round(random.uniform(4, 12), 2),
                         random.random() > 0.85,
                         random.choice([None, "加班完成项目", "周末值班", "远程办公"])),
                    )
                    attendance_count += 1
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()  # skip duplicate dates
                    continue

        # ==================================================================
        # Customers (~100)
        # ==================================================================
        customer_ids: list[int] = []
        for _ in range(100):
            cur.execute(
                """INSERT INTO customers (company_name, contact_name, contact, industry,
                       source, tier, assigned_to, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    fake.company(),
                    fake.name(),
                    (fake.email(), fake.phone_number()),
                    random.choice(INDUSTRIES),
                    random.choice(LEAD_SOURCES),
                    random.choices(CUSTOMER_TIERS, weights=[40, 25, 20, 10, 5])[0],
                    random.choice(emp_ids[:50]),  # sales/marketing employees
                    _date_between("2023-01-01", now),
                ),
            )
            customer_ids.append(cur.fetchone()[0])

        # Customer contacts (~200)
        for cid in customer_ids:
            n_contacts = random.choices([1, 2, 3, 4], weights=[30, 40, 20, 10])[0]
            for j in range(n_contacts):
                cur.execute(
                    """INSERT INTO customer_contacts (customer_id, name, role, contact, is_primary)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        cid,
                        fake.name(),
                        random.choice(["CEO", "CTO", "采购经理", "IT 总监", "项目经理",
                                       "财务经理", "技术负责人", "商务经理"]),
                        (fake.email(), fake.phone_number()),
                        j == 0,
                    ),
                )

        # ==================================================================
        # Product categories
        # ==================================================================
        for cat_id, name, parent in PRODUCT_CATEGORIES:
            cur.execute(
                "INSERT INTO product_categories (id, name, parent_id) VALUES (%s, %s, %s)",
                (cat_id, name, parent),
            )

        # ==================================================================
        # Suppliers (~20)
        # ==================================================================
        supplier_ids: list[int] = []
        for _ in range(20):
            cur.execute(
                """INSERT INTO suppliers (name, contact, rating, contract_start, contract_end)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (
                    fake.company(),
                    (fake.email(), fake.phone_number()),
                    round(random.uniform(3.5, 5.0), 1),
                    _date_between("2022-01-01", "2024-01-01"),
                    _date_between("2025-01-01", "2027-12-31"),
                ),
            )
            supplier_ids.append(cur.fetchone()[0])

        # ==================================================================
        # Products (~80)
        # ==================================================================
        product_ids: list[int] = []
        for name, cat_id, price, cost, unit in PRODUCT_NAMES:
            cur.execute(
                """INSERT INTO products (name, sku, category_id, supplier_id, unit_price,
                       cost_price, is_active, min_order_qty, unit)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    name,
                    f"SKU-{fake.numerify(text='######')}",
                    cat_id,
                    random.choice(supplier_ids),
                    price,
                    cost,
                    random.random() > 0.1,
                    random.randint(1, 10),
                    unit,
                ),
            )
            product_ids.append(cur.fetchone()[0])

        # Inventory (80)
        for pid in product_ids:
            qty = random.randint(0, 500)
            cur.execute(
                """INSERT INTO inventory (product_id, quantity, reserved, warehouse, last_restock)
                   VALUES (%s, %s, %s, %s, %s)""",
                (pid, qty, random.randint(0, max(qty // 4, 1)),
                 random.choice(WAREHOUSES),
                 fake.date_time_between(start_date="-180d", end_date="now")),
            )

        # ==================================================================
        # Purchase orders (~30)
        # ==================================================================
        po_ids: list[int] = []
        for _ in range(30):
            status = random.choices(
                ["draft", "sent", "paid", "overdue", "cancelled"],
                weights=[5, 15, 50, 10, 20],
            )[0]
            total = _rand_price(10000, 500000)
            created = fake.date_time_between(start_date="-365d", end_date="now")
            cur.execute(
                """INSERT INTO purchase_orders (supplier_id, status, total, created_at,
                       approved_at, received_at)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    random.choice(supplier_ids),
                    status,
                    (total, "CNY"),
                    created,
                    created + timedelta(hours=48) if status in ("paid",) else None,
                    created + timedelta(days=random.randint(5, 30)) if status == "paid" else None,
                ),
            )
            po_id = cur.fetchone()[0]
            po_ids.append(po_id)
            # PO items
            n_items = random.randint(1, 4)
            for pid in random.sample(product_ids, n_items):
                cur.execute(
                    """INSERT INTO purchase_order_items (purchase_order_id, product_id,
                           quantity, unit_cost)
                       VALUES (%s, %s, %s, %s)""",
                    (po_id, pid, random.randint(5, 100),
                     _rand_price(1000, 100000)),
                )

        # ==================================================================
        # Sales orders (~500)
        # ==================================================================
        order_ids: list[int] = []
        sales_reps = [e for e, d in emp_dept.items() if DEPARTMENTS[dept_ids.index(d)][1] == "sales"]
        if not sales_reps:
            sales_reps = emp_ids[:20]

        for i in range(500):
            status = random.choices(
                ["draft", "sent", "paid", "overdue", "cancelled"],
                weights=[5, 10, 55, 15, 15],
            )[0]
            created = fake.date_time_between(start_date="-365d", end_date="now")
            total = _rand_price(5000, 800000)
            cur.execute(
                """INSERT INTO sales_orders (customer_id, channel, status, assigned_to,
                       total_amount, discount_pct, note, created_at, confirmed_at,
                       delivered_at, invoiced_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    random.choice(customer_ids),
                    random.choice(ORDER_CHANNELS),
                    status,
                    random.choice(sales_reps),
                    (total, "CNY"),
                    round(random.uniform(0, 15), 2) if random.random() > 0.6 else 0,
                    random.choice([None, None, None, fake.sentence(nb_words=5)]),
                    created,
                    created + timedelta(hours=random.randint(1, 48)) if status in ("paid", "sent") else None,
                    created + timedelta(days=random.randint(3, 30)) if status == "paid" else None,
                    created + timedelta(days=random.randint(5, 45)) if status == "paid" else None,
                ),
            )
            order_ids.append(cur.fetchone()[0])

        # Sales order items (~1200)
        item_count = 0
        for oid in order_ids:
            n_items = random.choices([1, 2, 3, 4, 5], weights=[30, 35, 20, 10, 5])[0]
            for pid in random.sample(product_ids, min(n_items, len(product_ids))):
                cur.execute("SELECT unit_price FROM products WHERE id = %s", (pid,))
                row = cur.fetchone()
                if not row:
                    continue
                unit_price = row[0]
                qty = random.randint(1, 20)
                discount = round(random.uniform(0, 10), 2) if random.random() > 0.7 else 0
                subtotal = round(unit_price * qty * (1 - discount / 100), 2)
                cur.execute(
                    """INSERT INTO sales_order_items (sales_order_id, product_id, quantity,
                           unit_price, discount, subtotal)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (oid, pid, qty, unit_price, discount, subtotal),
                )
                item_count += 1

        # ==================================================================
        # Campaigns (~20)
        # ==================================================================
        campaign_ids: list[int] = []
        marketing_emps = [e for e, d in emp_dept.items()
                          if DEPARTMENTS[dept_ids.index(d)][1] == "marketing"]
        if not marketing_emps:
            marketing_emps = emp_ids[:10]

        for i in range(20):
            status = random.choices(
                ["draft", "active", "paused", "completed", "cancelled"],
                weights=[5, 20, 10, 50, 15],
            )[0]
            budget = _rand_price(50000, 500000)
            start_d = _date_between("2025-01-01", "2026-03-01")
            end_d = start_d + timedelta(days=random.randint(14, 90))
            cur.execute(
                """INSERT INTO campaigns (name, status, channel, budget, start_date, end_date,
                       target_audience, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    f"{random.choice(['Q1', 'Q2', 'Q3', 'Q4', '年度', '新品'])}"
                    f"{random.choice(['品牌推广', '获客', '线索培育', '产品发布', '促销'])}"
                    f"活动-{i+1}",
                    status,
                    random.choice(CAMPAIGN_CHANNELS),
                    (budget, "CNY"),
                    start_d, end_d,
                    random.choice(["中小企业 CTO", "IT 决策者", "行业分析师", "渠道合作伙伴"]),
                    random.choice(marketing_emps),
                ),
            )
            campaign_ids.append(cur.fetchone()[0])

        # ==================================================================
        # Leads (~300)
        # ==================================================================
        lead_count = 0
        for _ in range(300):
            status = random.choices(
                LEAD_STATUSES, weights=[15, 15, 12, 10, 8, 20, 20],
            )[0]
            created = fake.date_time_between(start_date="-365d", end_date="now")
            closed = created + timedelta(days=random.randint(7, 90)) if status in ("won", "lost") else None
            cur.execute(
                """INSERT INTO leads (campaign_id, customer_id, source, priority, status,
                       estimated_value, assigned_to, created_at, closed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    random.choice(campaign_ids) if random.random() > 0.3 else None,
                    random.choice(customer_ids) if random.random() > 0.4 else None,
                    random.choice(LEAD_SOURCES),
                    random.choices(["low", "medium", "high", "critical"], weights=[20, 40, 30, 10])[0],
                    status,
                    (_rand_price(10000, 500000), "CNY"),
                    random.choice(sales_reps),
                    created,
                    closed,
                ),
            )
            lead_count += 1

        # ==================================================================
        # Invoices (~400)
        # ==================================================================
        paid_orders = []
        for oid in order_ids:
            cur.execute("SELECT customer_id, total_amount, status FROM sales_orders WHERE id = %s", (oid,))
            row = cur.fetchone()
            if row and row[2] == "paid":
                paid_orders.append((oid, row[0], row[1]))

        invoice_count = 0
        for oid, cid, amount in paid_orders:
            if random.random() > 0.85:
                continue  # not every paid order gets invoiced immediately
            inv_status = random.choices(
                ["draft", "sent", "paid", "overdue", "cancelled"],
                weights=[5, 15, 55, 15, 10],
            )[0]
            created = fake.date_time_between(start_date="-300d", end_date="now")
            cur.execute(
                """INSERT INTO invoices (sales_order_id, customer_id, status, amount,
                       due_date, paid_date, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    oid, cid, inv_status, amount,
                    _date_between("2025-06-01", "2026-06-30"),
                    _date_between("2025-07-01", "2026-04-30") if inv_status == "paid" else None,
                    created,
                ),
            )
            invoice_count += 1

        # ==================================================================
        # Expenses (~300)
        # ==================================================================
        expense_count = 0
        for _ in range(300):
            dept_id = random.choice(dept_ids)
            emp = random.choice([e for e, d in emp_dept.items() if d == dept_id] or emp_ids)
            ex_status = random.choices(
                ["draft", "sent", "paid", "overdue", "cancelled"],
                weights=[10, 15, 50, 15, 10],
            )[0]
            submitted = fake.date_time_between(start_date="-300d", end_date="now")
            cur.execute(
                """INSERT INTO expenses (department_id, employee_id, category, amount,
                       description, receipt_no, status, submitted_at, approved_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    dept_id,
                    emp if random.random() > 0.2 else None,
                    random.choice(EXPENSE_CATS),
                    (_rand_price(100, 50000), "CNY"),
                    fake.sentence(nb_words=6),
                    f"RCP-{fake.numerify(text='########')}" if random.random() > 0.3 else None,
                    ex_status,
                    submitted,
                    submitted + timedelta(days=random.randint(1, 14)) if ex_status in ("paid", "sent") else None,
                ),
            )
            expense_count += 1

        # ==================================================================
        # Budgets (~40 = 8 depts × ~5 quarters)
        # ==================================================================
        budget_count = 0
        for did in dept_ids:
            for fy in [2025, 2026]:
                for q in range(1, 5):
                    if fy == 2026 and q > 1:
                        break
                    planned = _rand_price(200000, 2000000)
                    actual = (_rand_price(planned * 0.7, planned * 1.1), "CNY") if random.random() > 0.3 else None
                    cur.execute(
                        """INSERT INTO budgets (department_id, fiscal_year, quarter, planned, actual)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (did, fy, q, (planned, "CNY"), actual),
                    )
                    budget_count += 1

        # ==================================================================
        # Support tickets (~150)
        # ==================================================================
        ticket_count = 0
        for _ in range(150):
            priority = random.choices(
                ["low", "medium", "high", "critical"], weights=[30, 40, 20, 10],
            )[0]
            t_status = random.choices(
                TICKET_STATUSES, weights=[15, 20, 10, 30, 25],
            )[0]
            created = fake.date_time_between(start_date="-365d", end_date="now")
            resolved = created + timedelta(hours=random.randint(2, 168)) if t_status in ("resolved", "closed") else None
            closed = resolved + timedelta(hours=random.randint(1, 72)) if t_status == "closed" else None
            cur.execute(
                """INSERT INTO support_tickets (customer_id, subject, priority, status,
                       assigned_to, resolution, created_at, resolved_at, closed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    random.choice(customer_ids),
                    fake.sentence(nb_words=8),
                    priority,
                    t_status,
                    random.choice(emp_ids),
                    fake.paragraph(nb_sentences=2) if t_status in ("resolved", "closed") else None,
                    created, resolved, closed,
                ),
            )
            ticket_count += 1

        # ==================================================================
        # Activity log (~500)
        # ==================================================================
        log_count = 0
        entity_actions = [
            ("sales_order", "created"),
            ("sales_order", "updated"),
            ("sales_order", "status_changed"),
            ("invoice", "created"),
            ("invoice", "paid"),
            ("customer", "created"),
            ("customer", "updated"),
            ("lead", "created"),
            ("lead", "status_changed"),
            ("support_ticket", "created"),
            ("support_ticket", "resolved"),
            ("expense", "submitted"),
            ("expense", "approved"),
            ("campaign", "created"),
            ("campaign", "launched"),
        ]
        for _ in range(500):
            entity_type, action = random.choice(entity_actions)
            cur.execute(
                """INSERT INTO activity_log (entity_type, entity_id, action, performed_by,
                       details, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    entity_type,
                    random.randint(1, 500),
                    action,
                    random.choice(emp_ids) if random.random() > 0.1 else None,
                    {"reason": fake.sentence(nb_words=4)} if random.random() > 0.5 else None,
                    fake.date_time_between(start_date="-365d", end_date="now"),
                ),
            )
            log_count += 1

    conn.commit()
    print(
        f"Seeded large fixture: {len(emp_ids)} employees, {len(customer_ids)} customers, "
        f"{len(product_ids)} products, {len(order_ids)} sales orders, {item_count} order items, "
        f"{len(campaign_ids)} campaigns, {lead_count} leads, {invoice_count} invoices, "
        f"{expense_count} expenses, {budget_count} budgets, {ticket_count} tickets, "
        f"{log_count} activity logs, {salary_count} salary records, {attendance_count} attendance"
    )


if __name__ == "__main__":
    conn = psycopg2.connect(DB_URL)
    try:
        seed(conn)
    finally:
        conn.close()
