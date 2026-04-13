#!/usr/bin/env python3
"""Seed data for the medium (ecommerce) fixture database.

Generates ~500 rows: 30 users, 40 addresses, 15 categories, 6 vendors,
50 products, 50 inventory, 80 orders, 80+ order items, 80 payments, 50 reviews.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from faker import Faker

SEED = 42
DB_URL = os.environ.get(
    "PG_FIXTURE_URL",
    "postgresql://postgres@localhost/pg_mcp_test_medium",
)

fake = Faker("zh_CN")
Faker.seed(SEED)
random.seed(SEED)

PROVINCES_CITIES = [
    ("北京市", "北京市", ["朝阳区", "海淀区", "东城区", "西城区", "丰台区"]),
    ("上海市", "上海市", ["浦东新区", "徐汇区", "静安区", "杨浦区", "长宁区"]),
    ("广东省", "广州市", ["天河区", "越秀区", "番禺区", "海珠区"]),
    ("广东省", "深圳市", ["南山区", "福田区", "宝安区", "龙岗区", "罗湖区"]),
    ("浙江省", "杭州市", ["西湖区", "余杭区", "滨江区", "拱墅区"]),
    ("江苏省", "南京市", ["鼓楼区", "玄武区", "江宁区", "建邺区"]),
    ("四川省", "成都市", ["武侯区", "高新区", "锦江区", "青羊区"]),
    ("湖北省", "武汉市", ["洪山区", "武昌区", "江汉区", "江岸区"]),
]

CATEGORIES = [
    (1, "电子产品", "手机、电脑、数码配件等", None),
    (2, "手机", "智能手机、功能手机", 1),
    (3, "笔记本电脑", "轻薄本、游戏本、商务本", 1),
    (4, "数码配件", "耳机、充电器、保护壳等", 1),
    (5, "家居生活", "家具、厨具、家纺等", None),
    (6, "厨房用品", "锅具、刀具、小家电", 5),
    (7, "家具", "桌椅、沙发、床品", 5),
    (8, "家纺", "床上用品、窗帘、地毯", 5),
    (9, "食品饮料", "零食、酒水、生鲜", None),
    (10, "休闲零食", "坚果、糖果、饼干", 9),
    (11, "酒水饮料", "茶叶、咖啡、果汁", 9),
    (12, "运动户外", "运动装备、户外用品", None),
    (13, "运动服饰", "运动服、运动鞋", 12),
    (14, "运动器材", "跑步机、哑铃、瑜伽垫", 12),
    (15, "图书文具", "图书、办公用品", None),
]

PRODUCT_TEMPLATES = [
    # (name, category_id, price_range, weight_range, vendor_idx)
    ("iPhone 15 Pro 256GB", 2, (7000, 10000), (0.15, 0.25), 0),
    ("华为 Mate 60 Pro", 2, (5000, 7500), (0.18, 0.25), 0),
    ("小米14 Ultra", 2, (4000, 6500), (0.18, 0.25), 0),
    ("三星 Galaxy S24 Ultra", 2, (8000, 10500), (0.18, 0.25), 0),
    ("MacBook Pro 14", 3, (10000, 16000), (1.2, 2.0), 1),
    ("ThinkPad X1 Carbon", 3, (9000, 14000), (1.0, 1.5), 1),
    ("联想小新 Pro 16", 3, (4000, 6000), (1.5, 2.5), 1),
    ("Sony WH-1000XM5", 4, (1800, 3000), (0.2, 0.3), 0),
    ("AirPods Pro 2", 4, (1400, 2000), (0.04, 0.08), 0),
    ("Anker 65W 氮化镓充电器", 4, (150, 260), (0.08, 0.15), 1),
    ("北欧实木餐桌 1.4m", 7, (2000, 4000), (25, 45), 2),
    ("人体工学办公椅", 7, (1000, 2500), (10, 20), 2),
    ("乳胶枕", 8, (200, 450), (0.5, 1.2), 2),
    ("全棉四件套 1.8m", 8, (350, 700), (1.5, 3.5), 2),
    ("苏泊尔不粘锅套装", 6, (400, 850), (3, 7), 2),
    ("摩飞多功能料理锅", 6, (700, 1200), (2.5, 5), 2),
    ("欧式布艺沙发 三人位", 7, (3500, 7000), (45, 80), 2),
    ("智能扫地机器人 T20 Pro", 5, (2500, 4200), (3, 6), 2),
    ("陶瓷餐具套装 16 件", 6, (180, 350), (2.5, 5.5), 2),
    ("LED 护眼台灯", 5, (250, 500), (0.8, 1.8), 2),
    ("三只松鼠坚果大礼包 1.5kg", 10, (90, 170), (1.0, 2.0), 3),
    ("良品铺子猪肉脯 500g", 10, (40, 85), (0.3, 0.7), 3),
    ("农夫山泉矿泉水 24 瓶装", 11, (30, 50), (8, 15), 3),
    ("八马茶业铁观音 250g", 11, (200, 450), (0.2, 0.5), 3),
    ("瑞幸咖啡液 10 条装", 11, (50, 90), (0.1, 0.3), 3),
    ("百草味零食大礼包 1.2kg", 10, (80, 150), (0.8, 1.6), 3),
    ("星巴克胶囊咖啡 12 粒", 11, (70, 120), (0.1, 0.3), 3),
    ("三顿半精品速溶 24 颗", 11, (100, 200), (0.2, 0.4), 3),
    ("Nike Air Max 270", 13, (600, 1200), (0.25, 0.45), 4),
    ("Adidas Ultraboost 23", 13, (900, 1550), (0.25, 0.40), 4),
    ("Lululemon Align 瑜伽裤", 13, (550, 900), (0.12, 0.25), 4),
    ("迪卡侬登山背包 40L", 14, (200, 400), (0.5, 1.2), 4),
    ("Keep 瑜伽垫 10mm", 14, (120, 200), (1.0, 2.0), 4),
    ("李宁跑步鞋 飞电 3", 13, (700, 1150), (0.18, 0.30), 4),
    ("速干运动T恤 男款", 13, (80, 180), (0.1, 0.2), 4),
    ("哑铃套装 20kg", 14, (200, 420), (15, 25), 4),
    ("运动水壶 750ml", 14, (35, 70), (0.2, 0.4), 4),
    ("登山杖 碳纤维一对", 14, (180, 350), (0.3, 0.6), 4),
    ("Python 编程从入门到实践", 15, (50, 100), (0.4, 0.8), 5),
    ("深度学习", 15, (90, 150), (0.8, 1.5), 5),
    ("Moleskine 经典笔记本", 15, (150, 260), (0.12, 0.25), 5),
    ("得力中性笔 0.5mm 12 支装", 15, (12, 30), (0.1, 0.2), 5),
    ("Kindle Paperwhite 5", 15, (800, 1250), (0.12, 0.22), 5),
]

VENDOR_NAMES = ["优品科技", "恒信电子", "尚品家居", "美食天下", "运动前线", "文创工坊"]
WAREHOUSES = ["华东仓", "华南仓", "华北仓"]
PAYMENT_METHODS = ["credit_card", "debit_card", "alipay", "wechat_pay", "bank_transfer"]
ORDER_STATUSES = ["pending", "paid", "processing", "shipped", "delivered", "cancelled", "refunded"]

REVIEW_TITLES = ["不错", "推荐购买", "一般般", "超出预期", "物超所值", "有待改进", "经典好物", "体验很好"]
REVIEW_COMMENTS = [
    "质量很好，包装精美，物流也很快。",
    "性价比高，推荐给大家。",
    "用了一段时间，感觉还可以。",
    "和描述一致，没有色差。",
    "客服态度很好，耐心解答了问题。",
    "材质不错，做工精细。",
    "第二次购买了，一如既往的好。",
    "送给朋友的，对方很喜欢。",
]


def _rand_price(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def seed(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        # --- Vendors (6) ---
        vendor_ids: list[int] = []
        for name in VENDOR_NAMES:
            cur.execute(
                "INSERT INTO vendors (name, contact_email, rating) VALUES (%s, %s, %s) RETURNING id",
                (name, f"contact@{fake.slug()}.com", round(random.uniform(3.8, 4.9), 1)),
            )
            vendor_ids.append(cur.fetchone()[0])

        # --- Categories (15, hierarchical) ---
        for cat_id, name, desc, parent in CATEGORIES:
            cur.execute(
                "INSERT INTO categories (id, name, description, parent_id) VALUES (%s, %s, %s, %s)",
                (cat_id, name, desc, parent),
            )

        # --- Users (30) ---
        user_ids: list[int] = []
        for i in range(30):
            role = "customer"
            if i == 20:
                role = "admin"
            elif i == 21:
                role = "vendor"
            cur.execute(
                """INSERT INTO users (username, email, role, phone, is_active, last_login_at)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    fake.user_name(),
                    fake.email(),
                    role,
                    fake.phone_number(),
                    random.random() > 0.07,  # ~2 inactive
                    fake.date_time_between(start_date="-90d", end_date="now"),
                ),
            )
            user_ids.append(cur.fetchone()[0])

        # --- Addresses (~40) ---
        addr_ids: list[int] = []
        user_addr_map: dict[int, int] = {}  # user_id -> default addr_id
        for uid in user_ids:
            n_addrs = random.choices([1, 2, 3], weights=[60, 35, 5])[0]
            for j in range(n_addrs):
                prov, city, districts = random.choice(PROVINCES_CITIES)
                cur.execute(
                    """INSERT INTO addresses (user_id, province, city, district, street,
                           postal_code, is_default)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (
                        uid, prov, city, random.choice(districts),
                        fake.street_address(), fake.postcode(),
                        j == 0,
                    ),
                )
                aid = cur.fetchone()[0]
                addr_ids.append(aid)
                if j == 0:
                    user_addr_map[uid] = aid

        # --- Products (50) ---
        product_ids: list[int] = []
        for name, cat_id, (p_lo, p_hi), (w_lo, w_hi), v_idx in PRODUCT_TEMPLATES:
            price = _rand_price(p_lo, p_hi)
            orig = round(price * random.uniform(1.05, 1.35), 2)
            status = random.choices(
                ["active", "inactive", "out_of_stock"],
                weights=[90, 7, 3],
            )[0]
            cur.execute(
                """INSERT INTO products (name, vendor_id, category_id, price, original_price,
                       status, description, weight_kg)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (name, vendor_ids[v_idx], cat_id, price, orig, status,
                 fake.sentence(nb_words=8), round(random.uniform(w_lo, w_hi), 2)),
            )
            product_ids.append(cur.fetchone()[0])

        # --- Product Tags ---
        for pid in random.sample(product_ids, min(25, len(product_ids))):
            n_tags = random.randint(1, 3)
            tags = random.sample(["旗舰", "苹果", "华为", "小米", "三星", "降噪", "蓝牙",
                                  "快充", "北欧", "实木", "人体工学", "乳胶", "坚果",
                                  "零食", "Nike", "Adidas", "瑜伽", "Python", "AI",
                                  "编程", "电子书", "性价比", "轻薄", "商务", "国产"],
                                 n_tags)
            for tag in tags:
                cur.execute(
                    "INSERT INTO product_tags (product_id, tag) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (pid, tag),
                )

        # --- Inventory (50) ---
        for pid in product_ids:
            qty = random.randint(0, 800)
            cur.execute(
                """INSERT INTO inventory (product_id, quantity, reserved, warehouse)
                   VALUES (%s, %s, %s, %s)""",
                (pid, qty, random.randint(0, qty // 3), random.choice(WAREHOUSES)),
            )

        # --- Orders (80) ---
        order_ids: list[int] = []
        for i in range(80):
            uid = random.choice(user_ids[:21])  # mostly customers
            addr_id = user_addr_map.get(uid)
            if addr_id is None:
                addr_id = random.choice(addr_ids)
            status = random.choices(
                ORDER_STATUSES, weights=[5, 8, 7, 10, 50, 10, 10],
            )[0]
            created = fake.date_time_between(start_date="-150d", end_date="now")
            total = _rand_price(50, 15000)
            cur.execute(
                """INSERT INTO orders (user_id, address_id, status, total_amount, note,
                       created_at, paid_at, shipped_at, delivered_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    uid, addr_id, status, (total, "CNY"),
                    random.choice([None, None, None, fake.sentence(nb_words=4)]),
                    created,
                    created + timedelta(hours=1) if status in ("paid", "processing", "shipped", "delivered") else None,
                    created + timedelta(hours=24) if status in ("shipped", "delivered") else None,
                    created + timedelta(hours=72) if status == "delivered" else None,
                ),
            )
            order_ids.append(cur.fetchone()[0])

        # --- Order Items (for non-cancelled orders) ---
        for oid in order_ids:
            cur.execute("SELECT status FROM orders WHERE id = %s", (oid,))
            status = cur.fetchone()[0]
            n_items = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
            chosen_products = random.sample(product_ids, n_items)
            for pid in chosen_products:
                cur.execute("SELECT name, price FROM products WHERE id = %s", (pid,))
                pname, price = cur.fetchone()
                qty = random.randint(1, 3)
                cur.execute(
                    """INSERT INTO order_items (order_id, product_id, product_name,
                           unit_price, quantity, subtotal)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (oid, pid, pname, price, qty, round(price * qty, 2)),
                )

        # --- Payments (for paid orders) ---
        for oid in order_ids:
            cur.execute("SELECT status, total_amount FROM orders WHERE id = %s", (oid,))
            row = cur.fetchone()
            if row and row[0] not in ("pending", "cancelled"):
                cur.execute(
                    """INSERT INTO payments (order_id, method, amount, transaction_id,
                           status, paid_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        oid,
                        random.choice(PAYMENT_METHODS),
                        row[1],  # money_value tuple
                        f"TXN{fake.numerify(text='################')}",
                        "success",
                        fake.date_time_between(start_date="-150d", end_date="now"),
                    ),
                )

        # --- Reviews (50) ---
        for _ in range(50):
            pid = random.choice(product_ids)
            uid = random.choice(user_ids[:21])
            cur.execute(
                """INSERT INTO reviews (product_id, user_id, rating, title, content,
                       is_verified, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    pid, uid, random.randint(3, 5),
                    random.choice(REVIEW_TITLES),
                    random.choice(REVIEW_COMMENTS),
                    random.random() > 0.3,
                    fake.date_time_between(start_date="-120d", end_date="now"),
                ),
            )

    conn.commit()
    print("Seeded medium fixture: 30 users, 40 addresses, 15 categories, 6 vendors, "
          "50 products, 80 orders, 50 reviews")


if __name__ == "__main__":
    conn = psycopg2.connect(DB_URL)
    try:
        seed(conn)
    finally:
        conn.close()
