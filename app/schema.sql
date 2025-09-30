-- Schema definitions for QIF data in DuckDB

-- Accounts table
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    name VARCHAR,
    type VARCHAR,
    description VARCHAR,
    balance DECIMAL(15,2),
    credit_limit DECIMAL(15,2),
    note TEXT
);

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    name VARCHAR,
    description VARCHAR,
    expense_category BOOLEAN DEFAULT FALSE,
    income_category BOOLEAN DEFAULT FALSE,
    tax_related BOOLEAN DEFAULT FALSE,
    tax_schedule VARCHAR,
    parent_category VARCHAR
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    tx_id INTEGER PRIMARY KEY,
    account_type VARCHAR,
    date DATE,
    payee VARCHAR,
    memo TEXT,
    amount DECIMAL(15,2),
    cleared VARCHAR,
    number VARCHAR,
    category VARCHAR
);

-- Transaction splits table (for transactions split across multiple categories)
CREATE TABLE IF NOT EXISTS transaction_splits (
    split_id INTEGER PRIMARY KEY,
    tx_id INTEGER,
    category VARCHAR,
    amount DECIMAL(15,2),
    memo TEXT,
    FOREIGN KEY (tx_id) REFERENCES transactions(tx_id)
);

-- Useful views for common queries

-- Transactions with category information
CREATE OR REPLACE VIEW transactions_with_categories AS
SELECT
    t.*,
    c.description as category_description,
    c.expense_category,
    c.income_category,
    c.tax_related
FROM transactions t
LEFT JOIN categories c ON t.category = c.name;

-- Monthly summaries
CREATE OR REPLACE VIEW monthly_summaries AS
SELECT
    strftime('%Y-%m', date) as month,
    category,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount,
    MIN(amount) as min_amount,
    MAX(amount) as max_amount
FROM transactions
WHERE date IS NOT NULL
GROUP BY strftime('%Y-%m', date), category
ORDER BY month DESC, total_amount DESC;

-- Category summaries
CREATE OR REPLACE VIEW category_summaries AS
SELECT
    category,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount,
    MIN(date) as first_transaction,
    MAX(date) as last_transaction
FROM transactions
WHERE category IS NOT NULL
GROUP BY category
ORDER BY total_amount DESC;

-- Account type summaries
CREATE OR REPLACE VIEW account_type_summaries AS
SELECT
    account_type,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount
FROM transactions
WHERE account_type IS NOT NULL
GROUP BY account_type
ORDER BY total_amount DESC;