"""test_data_engineering_e2e.py - End-to-end integration test suite for Voila Data Engineering & Analytics."""

import unittest
import os
import sys
import json
import tempfile
import subprocess
import pandas as pd

LOCAL_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LOCAL_AGENT_DIR)

import data_tools
import document_tools

class TestDataEngineeringE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create mock data files
        self.customers_csv = os.path.join(self.temp_dir.name, "customers.csv")
        self.transactions_xlsx = os.path.join(self.temp_dir.name, "transactions.xlsx")

        cust_df = pd.DataFrame({
            "cust_id": ["C101", "C102", "C103", "C104", "C105", "C106"],
            "name": ["Acme Corp", "Beta LLC", "Gamma Inc", "Delta Co", "Echo Ltd", "Foxtrot SA"],
            "tier": ["Enterprise", "Mid-Market", "Enterprise", "SMB", "Mid-Market", "SMB"],
            "country": ["USA", "UK", "USA", "Germany", "France", "USA"]
        })
        cust_df.to_csv(self.customers_csv, index=False)

        txn_df = pd.DataFrame({
            "txn_id": ["T001", "T002", "T003", "T004", "T005", "T006", "T007"],
            "customer_id": ["C101", "C103", "C101", "C102", "C104", "C101", "C105"],
            "amount": [12500.0, 8900.0, 4500.0, 2300.0, 750.0, 15000.0, 3100.0],
            "status": ["Completed", "Completed", "Pending", "Completed", "Completed", "Completed", "Refunded"],
            "txn_date": ["2026-01-10", "2026-01-15", "2026-02-01", "2026-02-12", "2026-02-18", "2026-03-01", "2026-03-05"]
        })
        with pd.ExcelWriter(self.transactions_xlsx, engine="openpyxl") as writer:
            txn_df.to_excel(writer, sheet_name="Transactions", index=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_document_tools_read_csv_with_analyze(self):
        """Verify that document_tools.read_csv(analyze=True) invokes data profiling seamlessly."""
        output_str = document_tools.read_csv({"path": self.customers_csv, "analyze": True})
        self.assertTrue(output_str.startswith("{"))
        data = json.loads(output_str)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("rows"), 6)
        self.assertEqual(data.get("columns_count"), 4)

    def test_document_tools_read_excel_with_analyze(self):
        """Verify that document_tools.read_excel(analyze=True) invokes data profiling on Excel."""
        output_str = document_tools.read_excel({
            "path": self.transactions_xlsx,
            "sheet_name": "Transactions",
            "analyze": True
        })
        self.assertTrue(output_str.startswith("{"))
        data = json.loads(output_str)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("rows"), 7)

    def test_stdin_jsonrpc_dispatch(self):
        """Verify that data_tools.py handles JSON-RPC payloads over stdin."""
        payload = {
            "action": "query_dataset",
            "kwargs": {
                "query": "SELECT tier, COUNT(*) as cust_cnt FROM c GROUP BY tier ORDER BY cust_cnt DESC",
                "sources": {"c": self.customers_csv}
            }
        }
        proc = subprocess.run(
            [sys.executable, os.path.join(LOCAL_AGENT_DIR, "data_tools.py")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=True
        )
        res = json.loads(proc.stdout)
        self.assertTrue(res.get("ok"))
        self.assertEqual(len(res.get("records", [])), 3)

    def test_full_analytics_pipeline(self):
        """Test full end-to-end analytical workflow:
        1. SQL Query Join (Customers + Transactions)
        2. ETL Transform (Add Revenue categorization, calculate fees)
        3. Pivot/Aggregate (Revenue by Tier and Status)
        4. Multi-sheet Excel Dashboard generation
        5. Interactive HTML Report generation
        """
        # Step 1: SQL Join
        joined_csv = os.path.join(self.temp_dir.name, "joined_sales.csv")
        sql_res = data_tools.query_dataset(
            query="""
                SELECT t.txn_id, t.amount, t.status, t.txn_date, c.name as customer_name, c.tier, c.country
                FROM txns t
                JOIN cust c ON t.customer_id = c.cust_id
                WHERE t.status != 'Refunded'
                ORDER BY t.amount DESC
            """,
            sources={
                "txns": self.transactions_xlsx,
                "cust": self.customers_csv
            },
            sheet_names={"txns": "Transactions"},
            output_path=joined_csv
        )
        self.assertTrue(sql_res["ok"])
        self.assertEqual(sql_res["total_rows"], 6) # 7 minus 1 refunded
        self.assertTrue(os.path.exists(joined_csv))

        # Step 2: Transform & Clean
        transformed_csv = os.path.join(self.temp_dir.name, "transformed_sales.csv")
        transform_res = data_tools.transform_dataset(
            source_path=joined_csv,
            output_path=transformed_csv,
            steps=[
                {"action": "calculate_column", "target_column": "processing_fee", "formula": "amount * 0.029 + 0.30"},
                {"action": "calculate_column", "target_column": "net_revenue", "formula": "amount - processing_fee"},
                {"action": "string_clean", "columns": ["customer_name"], "trim": True, "case": "upper"}
            ]
        )
        self.assertTrue(transform_res["ok"])
        df_trans = pd.read_csv(transformed_csv)
        self.assertIn("processing_fee", df_trans.columns)
        self.assertIn("net_revenue", df_trans.columns)
        self.assertGreater(df_trans["net_revenue"].sum(), 40000.0)

        # Step 3: Aggregate by Tier
        agg_res = data_tools.aggregate_dataset(
            source_path=transformed_csv,
            group_by=["tier"],
            aggregations={"amount": ["sum", "mean", "count"], "net_revenue": "sum"}
        )
        self.assertTrue(agg_res["ok"])
        self.assertEqual(len(agg_res["records"]), 3)

        # Step 4: Executive Excel Dashboard
        excel_out = os.path.join(self.temp_dir.name, "Executive_Sales_Model.xlsx")
        tier_summary_data = [
            {"Tier": row["tier"], "Gross Amount": row["amount_sum"], "Net Revenue": row["net_revenue_sum"]}
            for row in agg_res["records"]
        ]
        dashboard_res = data_tools.generate_excel_dashboard(
            path=excel_out,
            title="Q1 Global Revenue & Merchant Tier Dashboard",
            sheets=[
                {
                    "name": "Summary KPI",
                    "data": tier_summary_data,
                    "formulas": [
                        {"cell": "B7", "formula": "=SUM(B4:B6)", "format": "currency"},
                        {"cell": "C7", "formula": "=SUM(C4:C6)", "format": "currency"}
                    ],
                    "number_formats": {
                        "Gross Amount": "currency",
                        "Net Revenue": "currency"
                    },
                    "charts": [
                        {
                            "type": "bar",
                            "title": "Net Revenue by Tier",
                            "category_column": 1,
                            "value_column": 3
                        }
                    ]
                },
                {
                    "name": "Transactions Detail",
                    "data": df_trans.to_dict(orient="records"),
                    "number_formats": {
                        "amount": "currency",
                        "net_revenue": "currency"
                    }
                }
            ]
        )
        self.assertTrue(dashboard_res["ok"])
        self.assertTrue(os.path.exists(excel_out))
        self.assertGreater(os.path.getsize(excel_out), 2000)

        # Step 5: Interactive HTML Report
        report_out = os.path.join(self.temp_dir.name, "Executive_Summary_Report.html")
        total_gross = f"${df_trans['amount'].sum():,.2f}"
        total_net = f"${df_trans['net_revenue'].sum():,.2f}"
        report_res = data_tools.generate_data_report(
            source_path=transformed_csv,
            title="Q1 Corporate Sales & Tier Performance Report",
            summary_notes="Analysis verified clean transactions across Enterprise, Mid-Market, and SMB tiers.",
            metrics=[
                {"label": "Total Gross Sales", "value": total_gross, "subtext": "Excluding refunds"},
                {"label": "Total Net Revenue", "value": total_net, "subtext": "After interchange fees"},
                {"label": "Active Merchants", "value": "6", "subtext": "100% matched"}
            ],
            output_path=report_out
        )
        self.assertTrue(report_res["ok"])
        self.assertTrue(os.path.exists(report_out))
        with open(report_out, "r", encoding="utf-8") as f:
            html_text = f.read()
        self.assertIn("Total Gross Sales", html_text)
        self.assertIn(total_gross, html_text)

if __name__ == "__main__":
    unittest.main()
