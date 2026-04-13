#!/usr/bin/env python3
"""Seed data for the small (bookshelf) fixture database.

Generates ~50 rows: 10 authors, 6 categories, 20 books, 20 reviews.
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
    "postgresql://postgres@localhost/pg_mcp_test_small",
)

fake = Faker("zh_CN")
Faker.seed(SEED)
random.seed(SEED)

GENRES = ["fiction", "non_fiction", "science", "history", "biography", "technology", "philosophy", "art"]
CATEGORY_NAMES = ["文学小说", "科幻", "悬疑推理", "历史", "哲学", "技术"]

REVIEWER_TITLES = [
    "非常推荐", "值得一读", "一般般", "经典之作", "文笔优美",
    "内容深刻", "翻译不错", "纸张好", "有点失望", "超出预期",
]
REVIEW_COMMENTS = [
    "这本书真的很棒，强烈推荐给所有人。",
    "内容丰富，观点独到，值得一读再读。",
    "文笔流畅，故事引人入胜。",
    "翻译质量一般，建议看原版。",
    "作为入门读物非常合适。",
    "深度适中，不会太晦涩也不会太浅显。",
    "排版舒服，阅读体验很好。",
    "虽然有些地方不太认同，但整体很好。",
    "适合碎片时间阅读的小品。",
    "经典永不过时，每次重读都有新感悟。",
]


def seed(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        # --- Authors (10) ---
        nationalities = ["中国", "日本", "美国", "英国", "法国", "德国", "俄罗斯", "哥伦比亚", "土耳其", "捷克"]
        authors = []
        for i in range(10):
            name = fake.name()
            birth_year = random.randint(1880, 1990)
            cur.execute(
                """INSERT INTO authors (name, nationality, birth_year, biography)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (name, nationalities[i], birth_year, fake.paragraph(nb_sentences=2)),
            )
            authors.append(cur.fetchone()[0])

        # --- Categories (6) ---
        cat_ids: list[int] = []
        for name in CATEGORY_NAMES:
            cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", (name,))
            cat_ids.append(cur.fetchone()[0])

        # --- Books (20) ---
        book_ids: list[int] = []
        for i in range(20):
            title = fake.sentence(nb_words=5).rstrip("。")
            cur.execute(
                """INSERT INTO books (title, author_id, category_id, genre, isbn, pages,
                       published_year, rating)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    title,
                    random.choice(authors),
                    random.choice(cat_ids),
                    random.choice(GENRES),
                    f"978{fake.numerify(text='################')}",
                    random.randint(100, 800),
                    random.randint(1950, 2025),
                    round(random.uniform(3.0, 5.0), 1),
                ),
            )
            book_ids.append(cur.fetchone()[0])

        # --- Reviews (20) ---
        for i in range(20):
            cur.execute(
                """INSERT INTO reviews (book_id, reviewer, rating, comment)
                   VALUES (%s, %s, %s, %s)""",
                (
                    random.choice(book_ids),
                    fake.name(),
                    random.randint(3, 5),
                    random.choice(REVIEW_COMMENTS),
                ),
            )

    conn.commit()
    print(f"Seeded small fixture: {len(authors)} authors, {len(cat_ids)} categories, "
          f"{len(book_ids)} books, 20 reviews")


if __name__ == "__main__":
    conn = psycopg2.connect(DB_URL)
    try:
        seed(conn)
    finally:
        conn.close()
