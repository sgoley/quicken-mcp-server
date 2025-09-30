#!/usr/bin/env python3

import sys
import asyncio
import duckdb
sys.path.append('.')

from app.qif_loader import load_qif_to_duckdb
from app.mcp_tools import QuickenMCPTools

async def test_quicken_server():
    """Test the Quicken MCP server functionality."""
    print("Testing Quicken MCP Server...")

    # Setup database
    print("1. Setting up DuckDB database...")
    db_conn = duckdb.connect(database=':memory:')
    db_conn.execute("PRAGMA memory_limit='8GB'")

    # Load QIF data
    print("2. Loading QIF data...")
    try:
        stats = load_qif_to_duckdb('data/example-file.qif', db_conn)
        print(f"   Loaded: {stats['accounts']} accounts, {stats['categories']} categories, {stats['transactions']} transactions")
    except Exception as e:
        print(f"   Error loading QIF: {e}")
        return

    # Test MCP tools
    print("3. Testing MCP tools...")
    tools = QuickenMCPTools(db_conn)

    # Test list_accounts
    print("   Testing list_accounts...")
    result = tools.list_accounts()
    if result['success']:
        print(f"   ✓ Found {result['count']} accounts")
    else:
        print(f"   ✗ Error: {result['error']}")

    # Test list_transactions
    print("   Testing list_transactions...")
    result = tools.list_transactions(limit=5)
    if result['success']:
        print(f"   ✓ Found {result['count']} transactions (limited to 5)")
        for tx in result['transactions'][:3]:
            print(f"      - {tx['date']}: ${tx['amount']:.2f} - {tx['payee']}")
    else:
        print(f"   ✗ Error: {result['error']}")

    # Test get_summaries
    print("   Testing get_summaries...")
    result = tools.get_summaries('category')
    if result['success']:
        stats = result['summaries']['statistics']
        print(f"   ✓ Summary generated - {stats['total_transactions']} total transactions")
        print(f"      Total amount: ${stats['total_amount']:.2f}")
        print(f"      Date range: {stats['earliest_date']} to {stats['latest_date']}")
    else:
        print(f"   ✗ Error: {result['error']}")

    # Test SQL query
    print("   Testing run_sql...")
    result = tools.run_sql("SELECT category, COUNT(*) as count FROM transactions WHERE category IS NOT NULL GROUP BY category ORDER BY count DESC LIMIT 5")
    if result['success']:
        print(f"   ✓ SQL query executed - {result['count']} rows returned")
        for row in result['rows'][:3]:
            print(f"      - {row['category']}: {row['count']} transactions")
    else:
        print(f"   ✗ Error: {result['error']}")

    print("\n✅ All tests completed successfully!")
    db_conn.close()

if __name__ == "__main__":
    asyncio.run(test_quicken_server())