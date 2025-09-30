"""QIF file parser and DuckDB loader."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class QIFParser:
    """Parser for Quicken Interchange Format (QIF) files."""

    def __init__(self):
        self.accounts = []
        self.categories = []
        self.transactions = []
        self.current_account = None

    def parse_file(self, file_path: str) -> Dict[str, List]:
        """Parse a QIF file and return structured data."""
        logger.info(f"Parsing QIF file: {file_path}")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return self._parse_content(content)

    def _parse_content(self, content: str) -> Dict[str, List]:
        """Parse QIF content into structured data."""
        lines = content.strip().split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Parse different sections
            if line == '!Option:AutoSwitch':
                i += 1
                continue
            elif line == '!Account':
                i = self._parse_accounts_section(lines, i + 1)
            elif line.startswith('!Type:'):
                account_type = line.split(':', 1)[1]
                i = self._parse_transactions_section(lines, i + 1, account_type)
            else:
                # This might be a category definition or transaction
                if line.startswith('N') and i + 1 < len(lines) and lines[i + 1].startswith('D'):
                    # Check if this looks like a category (D followed by description) or transaction (D followed by date)
                    next_line = lines[i + 1].strip()[1:] if lines[i + 1].strip() else ""
                    if self._looks_like_date(next_line):
                        # This is likely a transaction without !Type: header
                        i = self._parse_transactions_section(lines, i, "Unknown")
                    else:
                        # This looks like a category definition
                        i = self._parse_category_definition(lines, i)
                elif line.startswith('D') and self._looks_like_date(line[1:]):
                    # This is likely the start of transactions without !Type: header
                    i = self._parse_transactions_section(lines, i, "Unknown")
                else:
                    i += 1

        logger.info(f"Parsed {len(self.accounts)} accounts, {len(self.categories)} categories, {len(self.transactions)} transactions")

        return {
            'accounts': self.accounts,
            'categories': self.categories,
            'transactions': self.transactions
        }

    def _parse_accounts_section(self, lines: List[str], start_idx: int) -> int:
        """Parse the accounts section."""
        i = start_idx

        while i < len(lines):
            line = lines[i].strip()

            if line == '^':
                i += 1
                continue

            if line.startswith('!') or (not line.startswith(('N', 'T', 'D', 'B', 'L', 'A'))):
                break

            # Parse account entry
            account = {}
            while i < len(lines) and lines[i].strip() != '^':
                line = lines[i].strip()
                if line.startswith('N'):
                    account['name'] = line[1:]
                elif line.startswith('T'):
                    account['type'] = line[1:]
                elif line.startswith('D'):
                    account['description'] = line[1:]
                elif line.startswith('B'):
                    try:
                        account['balance'] = float(line[1:]) if line[1:] else 0.0
                    except ValueError:
                        account['balance'] = 0.0
                elif line.startswith('L'):
                    try:
                        account['credit_limit'] = float(line[1:]) if line[1:] else None
                    except ValueError:
                        account['credit_limit'] = None
                elif line.startswith('A'):
                    account['note'] = line[1:]
                i += 1

            if account.get('name'):
                account['account_id'] = len(self.accounts) + 1
                self.accounts.append(account)

        return i

    def _parse_category_definition(self, lines: List[str], start_idx: int) -> int:
        """Parse a category definition."""
        i = start_idx
        category = {}

        while i < len(lines) and lines[i].strip() != '^':
            line = lines[i].strip()
            if line.startswith('N'):
                category['name'] = line[1:]
            elif line.startswith('D'):
                category['description'] = line[1:]
            elif line.startswith('E'):
                category['expense_category'] = True
            elif line.startswith('I'):
                category['income_category'] = True
            elif line.startswith('T'):
                category['tax_related'] = True
            elif line.startswith('R'):
                category['tax_schedule'] = line[1:]
            i += 1

        if category.get('name'):
            category['category_id'] = len(self.categories) + 1
            self.categories.append(category)

        return i + 1

    def _parse_transactions_section(self, lines: List[str], start_idx: int, account_type: str) -> int:
        """Parse a transactions section."""
        i = start_idx

        while i < len(lines):
            line = lines[i].strip()

            if line.startswith('!'):
                break

            # Parse individual transaction
            transaction = {'account_type': account_type}
            transaction_lines = []

            # Collect all lines until ^
            while i < len(lines) and lines[i].strip() != '^':
                if lines[i].strip():
                    transaction_lines.append(lines[i].strip())
                i += 1

            if transaction_lines:
                parsed_tx = self._parse_transaction_lines(transaction_lines)
                if parsed_tx:
                    parsed_tx['tx_id'] = len(self.transactions) + 1
                    parsed_tx['account_type'] = account_type
                    self.transactions.append(parsed_tx)

            i += 1  # Skip the ^

        return i

    def _parse_transaction_lines(self, lines: List[str]) -> Optional[Dict]:
        """Parse individual transaction lines."""
        transaction = {}

        for line in lines:
            if not line:
                continue

            code = line[0]
            value = line[1:] if len(line) > 1 else ""

            if code == 'D':  # Date
                transaction['date'] = self._parse_date(value)
            elif code == 'P':  # Payee
                transaction['payee'] = value
            elif code == 'M':  # Memo
                transaction['memo'] = value
            elif code == 'T':  # Amount
                transaction['amount'] = self._parse_amount(value)
            elif code == 'C':  # Cleared status
                transaction['cleared'] = value
            elif code == 'N':  # Number (check number, etc.)
                transaction['number'] = value
            elif code == 'L':  # Category
                transaction['category'] = value
            elif code == 'S':  # Split category
                if 'splits' not in transaction:
                    transaction['splits'] = []
                transaction['splits'].append({'category': value})
            elif code == '$':  # Split amount
                if 'splits' in transaction and transaction['splits']:
                    transaction['splits'][-1]['amount'] = self._parse_amount(value)
            elif code == 'E':  # Split memo
                if 'splits' in transaction and transaction['splits']:
                    transaction['splits'][-1]['memo'] = value

        # Only return transaction if it has required fields
        if 'date' in transaction and 'amount' in transaction:
            return transaction

        return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse various date formats into ISO format."""
        if not date_str:
            return None

        # Common QIF date formats
        formats = [
            '%m/%d/%y',    # 12/31/23
            '%m/%d/%Y',    # 12/31/2023
            '%m-%d-%y',    # 12-31-23
            '%m-%d-%Y',    # 12-31-2023
            '%Y-%m-%d',    # 2023-12-31
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Convert 2-digit years
                if dt.year < 1950:
                    dt = dt.replace(year=dt.year + 100)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string to float."""
        if not amount_str:
            return None

        # Remove common currency symbols and whitespace
        cleaned = re.sub(r'[,$\s]', '', amount_str)

        try:
            return float(cleaned)
        except (ValueError, InvalidOperation):
            logger.warning(f"Could not parse amount: {amount_str}")
            return None

    def _looks_like_date(self, date_str: str) -> bool:
        """Check if a string looks like a date."""
        if not date_str:
            return False

        # Check common date patterns
        date_patterns = [
            r'^\d{2}/\d{2}/\d{2}$',    # MM/DD/YY
            r'^\d{2}/\d{2}/\d{4}$',    # MM/DD/YYYY
            r'^\d{1}/\d{2}/\d{2}$',    # M/DD/YY
            r'^\d{1}/\d{1}/\d{2}$',    # M/D/YY
            r'^\d{2}/\d{1}/\d{2}$',    # MM/D/YY
            r'^\d{2}-\d{2}-\d{2}$',    # MM-DD-YY
            r'^\d{4}-\d{2}-\d{2}$',    # YYYY-MM-DD
        ]

        for pattern in date_patterns:
            if re.match(pattern, date_str.strip()):
                return True

        return False


def load_qif_to_duckdb(qif_path: str, db_connection) -> Dict[str, int]:
    """Load QIF file data into DuckDB tables."""
    parser = QIFParser()
    data = parser.parse_file(qif_path)

    # Create tables if they don't exist
    _create_tables(db_connection)

    # Load data
    accounts_loaded = _load_accounts(db_connection, data['accounts'])
    categories_loaded = _load_categories(db_connection, data['categories'])
    transactions_loaded = _load_transactions(db_connection, data['transactions'])

    return {
        'accounts': accounts_loaded,
        'categories': categories_loaded,
        'transactions': transactions_loaded
    }


def _create_tables(db_connection):
    """Create the necessary tables in DuckDB."""

    # Accounts table
    db_connection.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id INTEGER PRIMARY KEY,
            name VARCHAR,
            type VARCHAR,
            description VARCHAR,
            balance DECIMAL(15,2),
            credit_limit DECIMAL(15,2),
            note TEXT
        )
    """)

    # Categories table
    db_connection.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY,
            name VARCHAR,
            description VARCHAR,
            expense_category BOOLEAN DEFAULT FALSE,
            income_category BOOLEAN DEFAULT FALSE,
            tax_related BOOLEAN DEFAULT FALSE,
            tax_schedule VARCHAR
        )
    """)

    # Transactions table
    db_connection.execute("""
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
        )
    """)

    # Transaction splits table
    db_connection.execute("""
        CREATE TABLE IF NOT EXISTS transaction_splits (
            split_id INTEGER PRIMARY KEY,
            tx_id INTEGER,
            category VARCHAR,
            amount DECIMAL(15,2),
            memo TEXT,
            FOREIGN KEY (tx_id) REFERENCES transactions(tx_id)
        )
    """)

    # Create useful views
    db_connection.execute("""
        CREATE OR REPLACE VIEW transactions_with_categories AS
        SELECT
            t.*,
            c.description as category_description,
            c.expense_category,
            c.income_category,
            c.tax_related
        FROM transactions t
        LEFT JOIN categories c ON t.category = c.name
    """)

    # Monthly summaries view
    db_connection.execute("""
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
        ORDER BY month DESC, total_amount DESC
    """)

    # Category summaries view
    db_connection.execute("""
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
        ORDER BY total_amount DESC
    """)

    # Account type summaries view
    db_connection.execute("""
        CREATE OR REPLACE VIEW account_type_summaries AS
        SELECT
            account_type,
            COUNT(*) as transaction_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount
        FROM transactions
        WHERE account_type IS NOT NULL
        GROUP BY account_type
        ORDER BY total_amount DESC
    """)


def _load_accounts(db_connection, accounts: List[Dict]) -> int:
    """Load accounts into the database."""
    if not accounts:
        return 0

    # Clear existing data
    db_connection.execute("DELETE FROM accounts")

    for account in accounts:
        db_connection.execute("""
            INSERT INTO accounts (account_id, name, type, description, balance, credit_limit, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            account.get('account_id'),
            account.get('name'),
            account.get('type'),
            account.get('description'),
            account.get('balance'),
            account.get('credit_limit'),
            account.get('note')
        ))

    return len(accounts)


def _load_categories(db_connection, categories: List[Dict]) -> int:
    """Load categories into the database."""
    if not categories:
        return 0

    # Clear existing data
    db_connection.execute("DELETE FROM categories")

    for category in categories:
        db_connection.execute("""
            INSERT INTO categories (category_id, name, description, expense_category, income_category, tax_related, tax_schedule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            category.get('category_id'),
            category.get('name'),
            category.get('description'),
            category.get('expense_category', False),
            category.get('income_category', False),
            category.get('tax_related', False),
            category.get('tax_schedule')
        ))

    return len(categories)


def _load_transactions(db_connection, transactions: List[Dict]) -> int:
    """Load transactions into the database."""
    if not transactions:
        return 0

    # Clear existing data
    db_connection.execute("DELETE FROM transaction_splits")
    db_connection.execute("DELETE FROM transactions")

    split_id = 1

    for transaction in transactions:
        # Insert main transaction
        db_connection.execute("""
            INSERT INTO transactions (tx_id, account_type, date, payee, memo, amount, cleared, number, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.get('tx_id'),
            transaction.get('account_type'),
            transaction.get('date'),
            transaction.get('payee'),
            transaction.get('memo'),
            transaction.get('amount'),
            transaction.get('cleared'),
            transaction.get('number'),
            transaction.get('category')
        ))

        # Insert splits if they exist
        if 'splits' in transaction:
            for split in transaction['splits']:
                db_connection.execute("""
                    INSERT INTO transaction_splits (split_id, tx_id, category, amount, memo)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    split_id,
                    transaction.get('tx_id'),
                    split.get('category'),
                    split.get('amount'),
                    split.get('memo')
                ))
                split_id += 1

    return len(transactions)