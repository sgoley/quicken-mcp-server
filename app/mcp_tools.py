"""MCP tool implementations for Quicken data queries."""

import json
from typing import Any, Dict, List, Optional
import logging
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


class QuickenMCPTools:
    """MCP tool implementations for querying Quicken financial data."""

    def __init__(self, db_connection):
        self.db = db_connection

    def list_accounts(self) -> Dict[str, Any]:
        """List all accounts with their basic information."""
        try:
            result = self.db.execute("""
                SELECT account_id, name, type, description, balance, credit_limit
                FROM accounts
                ORDER BY name
            """).fetchall()

            accounts = []
            for row in result:
                accounts.append({
                    'account_id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'description': row[3],
                    'balance': float(row[4]) if row[4] is not None else None,
                    'credit_limit': float(row[5]) if row[5] is not None else None
                })

            return {
                'success': True,
                'accounts': accounts,
                'count': len(accounts)
            }

        except Exception as e:
            logger.error(f"Error listing accounts: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def list_transactions(self,
                         account_type: Optional[str] = None,
                         date_from: Optional[str] = None,
                         date_to: Optional[str] = None,
                         category: Optional[str] = None,
                         payee: Optional[str] = None,
                         limit: int = 100) -> Dict[str, Any]:
        """List transactions with optional filters."""
        try:
            # Build the query dynamically based on filters
            where_conditions = []
            params = []

            if account_type:
                where_conditions.append("account_type = ?")
                params.append(account_type)

            if date_from:
                where_conditions.append("date >= ?")
                params.append(date_from)

            if date_to:
                where_conditions.append("date <= ?")
                params.append(date_to)

            if category:
                where_conditions.append("category LIKE ?")
                params.append(f"%{category}%")

            if payee:
                where_conditions.append("payee LIKE ?")
                params.append(f"%{payee}%")

            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)

            query = f"""
                SELECT tx_id, account_type, date, payee, memo, amount, cleared, number, category
                FROM transactions
                {where_clause}
                ORDER BY date DESC, tx_id DESC
                LIMIT ?
            """
            params.append(limit)

            result = self.db.execute(query, params).fetchall()

            transactions = []
            for row in result:
                transactions.append({
                    'tx_id': row[0],
                    'account_type': row[1],
                    'date': row[2],
                    'payee': row[3],
                    'memo': row[4],
                    'amount': float(row[5]) if row[5] is not None else None,
                    'cleared': row[6],
                    'number': row[7],
                    'category': row[8]
                })

            return {
                'success': True,
                'transactions': transactions,
                'count': len(transactions),
                'filters': {
                    'account_type': account_type,
                    'date_from': date_from,
                    'date_to': date_to,
                    'category': category,
                    'payee': payee,
                    'limit': limit
                }
            }

        except Exception as e:
            logger.error(f"Error listing transactions: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def run_sql(self, query: str) -> Dict[str, Any]:
        """Execute a SQL query with safety restrictions."""
        try:
            # Sanitize the query - only allow SELECT statements
            query = query.strip()
            if not query.upper().startswith('SELECT'):
                return {
                    'success': False,
                    'error': 'Only SELECT queries are allowed for security reasons'
                }

            # Check for dangerous keywords
            dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'TRUNCATE']
            query_upper = query.upper()
            for keyword in dangerous_keywords:
                if keyword in query_upper:
                    return {
                        'success': False,
                        'error': f'Query contains prohibited keyword: {keyword}'
                    }

            # Execute the query with a reasonable limit
            if 'LIMIT' not in query_upper:
                query += ' LIMIT 1000'

            result = self.db.execute(query).fetchall()
            column_names = [desc[0] for desc in self.db.description]

            # Convert result to list of dictionaries
            rows = []
            for row in result:
                row_dict = {}
                for i, value in enumerate(row):
                    # Convert decimal/numeric types to float for JSON serialization
                    if hasattr(value, '__float__'):
                        row_dict[column_names[i]] = float(value)
                    elif value is None:
                        row_dict[column_names[i]] = None
                    else:
                        row_dict[column_names[i]] = value
                rows.append(row_dict)

            return {
                'success': True,
                'rows': rows,
                'columns': column_names,
                'count': len(rows),
                'query': query
            }

        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }

    def get_summaries(self, period: str = 'month') -> Dict[str, Any]:
        """Get financial summaries for different time periods."""
        try:
            summaries = {}

            if period in ['month', 'all']:
                # Monthly summaries
                result = self.db.execute("""
                    SELECT month, category, transaction_count, total_amount, avg_amount
                    FROM monthly_summaries
                    LIMIT 50
                """).fetchall()

                monthly_data = []
                for row in result:
                    monthly_data.append({
                        'month': row[0],
                        'category': row[1],
                        'transaction_count': row[2],
                        'total_amount': float(row[3]) if row[3] is not None else None,
                        'avg_amount': float(row[4]) if row[4] is not None else None
                    })

                summaries['monthly'] = monthly_data

            if period in ['category', 'all']:
                # Category summaries
                result = self.db.execute("""
                    SELECT category, transaction_count, total_amount, avg_amount,
                           first_transaction, last_transaction
                    FROM category_summaries
                    LIMIT 50
                """).fetchall()

                category_data = []
                for row in result:
                    category_data.append({
                        'category': row[0],
                        'transaction_count': row[1],
                        'total_amount': float(row[2]) if row[2] is not None else None,
                        'avg_amount': float(row[3]) if row[3] is not None else None,
                        'first_transaction': row[4],
                        'last_transaction': row[5]
                    })

                summaries['categories'] = category_data

            if period in ['account', 'all']:
                # Account type summaries
                result = self.db.execute("""
                    SELECT account_type, transaction_count, total_amount, avg_amount
                    FROM account_type_summaries
                """).fetchall()

                account_data = []
                for row in result:
                    account_data.append({
                        'account_type': row[0],
                        'transaction_count': row[1],
                        'total_amount': float(row[2]) if row[2] is not None else None,
                        'avg_amount': float(row[3]) if row[3] is not None else None
                    })

                summaries['account_types'] = account_data

            # Overall statistics
            stats_result = self.db.execute("""
                SELECT
                    COUNT(*) as total_transactions,
                    COUNT(DISTINCT category) as unique_categories,
                    COUNT(DISTINCT account_type) as unique_account_types,
                    COUNT(DISTINCT payee) as unique_payees,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date,
                    SUM(amount) as total_amount
                FROM transactions
            """).fetchone()

            summaries['statistics'] = {
                'total_transactions': stats_result[0],
                'unique_categories': stats_result[1],
                'unique_account_types': stats_result[2],
                'unique_payees': stats_result[3],
                'earliest_date': stats_result[4],
                'latest_date': stats_result[5],
                'total_amount': float(stats_result[6]) if stats_result[6] is not None else None
            }

            return {
                'success': True,
                'summaries': summaries,
                'period': period
            }

        except Exception as e:
            logger.error(f"Error generating summaries: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_categories(self) -> Dict[str, Any]:
        """Get all categories with their metadata."""
        try:
            result = self.db.execute("""
                SELECT category_id, name, description, expense_category,
                       income_category, tax_related, tax_schedule
                FROM categories
                ORDER BY name
            """).fetchall()

            categories = []
            for row in result:
                categories.append({
                    'category_id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'expense_category': bool(row[3]) if row[3] is not None else False,
                    'income_category': bool(row[4]) if row[4] is not None else False,
                    'tax_related': bool(row[5]) if row[5] is not None else False,
                    'tax_schedule': row[6]
                })

            return {
                'success': True,
                'categories': categories,
                'count': len(categories)
            }

        except Exception as e:
            logger.error(f"Error listing categories: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def search_transactions(self, search_term: str, limit: int = 50) -> Dict[str, Any]:
        """Search transactions by payee, memo, or category."""
        try:
            query = """
                SELECT tx_id, account_type, date, payee, memo, amount, category
                FROM transactions
                WHERE payee LIKE ? OR memo LIKE ? OR category LIKE ?
                ORDER BY date DESC
                LIMIT ?
            """

            search_pattern = f"%{search_term}%"
            result = self.db.execute(query, [search_pattern, search_pattern, search_pattern, limit]).fetchall()

            transactions = []
            for row in result:
                transactions.append({
                    'tx_id': row[0],
                    'account_type': row[1],
                    'date': row[2],
                    'payee': row[3],
                    'memo': row[4],
                    'amount': float(row[5]) if row[5] is not None else None,
                    'category': row[6]
                })

            return {
                'success': True,
                'transactions': transactions,
                'count': len(transactions),
                'search_term': search_term
            }

        except Exception as e:
            logger.error(f"Error searching transactions: {e}")
            return {
                'success': False,
                'error': str(e)
            }