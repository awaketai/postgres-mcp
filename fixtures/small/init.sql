-- =============================================================================
-- Fixture: bookshelf (small)
-- Database: pg_mcp_test_small
-- Description: A simple personal library management system.
--   4 tables, 1 view, 1 ENUM type, basic indexes.
-- Data: seeded via seed.py (~50 rows)
-- =============================================================================

CREATE TYPE book_genre AS ENUM (
    'fiction', 'non_fiction', 'science', 'history',
    'biography', 'technology', 'philosophy', 'art'
);

CREATE TABLE authors (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    nationality VARCHAR(100),
    birth_year  INT,
    biography   TEXT
);
COMMENT ON TABLE authors IS '图书作者';

CREATE TABLE categories (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);
COMMENT ON TABLE categories IS '图书分类';

CREATE TABLE books (
    id            SERIAL PRIMARY KEY,
    title         VARCHAR(300) NOT NULL,
    author_id     INT REFERENCES authors(id) ON DELETE SET NULL,
    category_id   INT REFERENCES categories(id) ON DELETE SET NULL,
    genre         book_genre NOT NULL,
    isbn          VARCHAR(20) UNIQUE,
    pages         INT,
    published_year INT,
    rating        NUMERIC(3,2) CHECK (rating >= 0 AND rating <= 5),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE books IS '图书信息';
COMMENT ON COLUMN books.rating IS '读者评分，0-5 分';

CREATE TABLE reviews (
    id         SERIAL PRIMARY KEY,
    book_id    INT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    reviewer   VARCHAR(100) NOT NULL,
    rating     INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE reviews IS '图书评论';

CREATE INDEX idx_books_author_id     ON books(author_id);
CREATE INDEX idx_books_category_id   ON books(category_id);
CREATE INDEX idx_books_genre         ON books(genre);
CREATE INDEX idx_books_published_year ON books(published_year);
CREATE INDEX idx_reviews_book_id     ON reviews(book_id);
CREATE INDEX idx_reviews_rating      ON reviews(rating);

CREATE VIEW book_summary AS
SELECT
    b.id,
    b.title,
    a.name  AS author_name,
    c.name  AS category_name,
    b.genre,
    b.pages,
    b.published_year,
    b.rating AS avg_rating,
    COALESCE(rc.review_count, 0) AS review_count
FROM books b
LEFT JOIN authors a   ON b.author_id = a.id
LEFT JOIN categories c ON b.category_id = c.id
LEFT JOIN (
    SELECT book_id, COUNT(*) AS review_count
    FROM reviews
    GROUP BY book_id
) rc ON rc.book_id = b.id;
COMMENT ON VIEW book_summary IS '图书摘要视图：包含作者、分类、评论数等信息';
