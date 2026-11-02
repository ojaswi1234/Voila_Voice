"""test_data_tools.py - Unit & integration tests for data_tools.py."""

import unittest
import os
import sys
import json
import tempfile
import pandas as pd
import numpy as np

# Ensure local-agent directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_tools

class TestDataTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # 1. Create a sample CSV file
        self.csv_path = os.path.join(self.temp_dir.name, "employees.csv")
        data = {
            "id": [101, 102, 103, 104, 105, 106, 107, 108],
            "name": [" Alice ", "Bob", " Charlie", "David ", "Eve", "Frank", "Grace", "Heidi"],
            "department": ["Engineering", "Engineering", "Sales", "Sales", "HR", "Engineering", "Marketing", "HR"],
            "salary": [120000, 115000, 95000, 98000, 75000, 130000, 88000, None], # 1 null
            "performance_score": [4.5, 4.2, 3.8, 4.0, 3.5, 4.8, 4.1, 3.9],
            "hire_date": ["2020-01-15", "2019-06-01", "2021-03-12", "2018-11-20", "2022-05-10", "2017-08-15", "2021-09-01", "2023-02-01"]
        }
        pd.DataFrame(data).to_csv(self.csv_path, index=False)

        # 2. Create a sample Excel file
        self.xlsx_path = os.path.join(self.temp_dir.name, "financials.xlsx")
        orders_data = {
            "order_id": ["ORD-1", "ORD-2", "ORD-3", "ORD-4", "ORD-5"],
            "employee_id": [101, 103, 104, 101, 106],
            "amount": [1500.50, 2400.00, 890.25, 4500.00, 1200.00],
            "region": ["North", "South", "East", "North", "West"]
        }
        with pd.ExcelWriter(self.xlsx_path, engine="openpyxl") as writer:
            pd.DataFrame(orders_data).to_excel(writer, sheet_name="Orders", index=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_1_profile_dataset(self):
        """Test dataset profiling on CSV with numeric, string, and null columns."""
        res = data_tools.profile_dataset(self.csv_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res["rows"], 8)
        self.assertEqual(res["columns_count"], 6)
        
        # Check salary null count
        col_map = {c["name"]: c for c in res["columns"]}
        self.assertIn("salary", col_map)
        self.assertEqual(col_map["salary"]["null_count"], 1)
        self.assertAlmostEqual(col_map["salary"]["null_pct"], 12.5, places=1)
        self.assertIn("stats", col_map["salary"])
        self.assertEqual(col_map["salary"]["stats"]["min"], 75000)

        # Check department categories
        self.assertIn("department", col_map)
        self.assertIn("Engineering", col_map["department"]["top_values"])

    def test_2_query_dataset_single_table(self):
        """Test running ANSI SQL on a single CSV file."""
        query = "SELECT department, COUNT(*) as cnt, AVG(salary) as avg_sal FROM emp WHERE salary IS NOT NULL GROUP BY department ORDER BY avg_sal DESC"
        res = data_tools.query_dataset(
            query=query,
            sources={"emp": self.csv_path}
        )
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["records"]), 4) # Engineering, Sales, Marketing, HR
        first_dept = res["records"][0]
        self.assertEqual(first_dept["department"], "Engineering")
        self.assertGreater(first_dept["avg_sal"], 100000)

    def test_3_query_dataset_cross_file_join(self):
        """Test joining a CSV file and an Excel file using SQL."""
        query = """
            SELECT o.order_id, o.amount, o.region, e.name, e.department
            FROM orders o
            JOIN emp e ON o.employee_id = e.id
            ORDER BY o.amount DESC
        """
        res = data_tools.query_dataset(
            query=query,
            sources={
                "emp": self.csv_path,
                "orders": self.xlsx_path
            },
            sheet_names={"orders": "Orders"}
        )
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["records"]), 5)
        top_order = res["records"][0]
        self.assertEqual(top_order["order_id"], "ORD-4")
        self.assertEqual(top_order["amount"], 4500.0)

    def test_4_transform_dataset_pipeline(self):
        """Test ETL pipeline: clean strings, impute nulls, filter, and calculate derived columns."""
        out_csv = os.path.join(self.temp_dir.name, "cleaned_employees.csv")
        steps = [
            {"action": "string_clean", "columns": ["name"], "trim": True, "case": "upper"},
            {"action": "fill_na", "column": "salary", "strategy": "median"},
            {"action": "calculate_column", "target_column": "bonus", "formula": "salary * 0.15"},
            {"action": "filter", "expression": "salary >= 90000"},
            {"action": "sort_by", "columns": "salary", "ascending": False}
        ]
        res = data_tools.transform_dataset(self.csv_path, out_csv, steps)
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.exists(out_csv))
        
        # Verify transformed contents
        df_clean = pd.read_csv(out_csv)
        self.assertEqual(df_clean["salary"].isna().sum(), 0) # No nulls
        self.assertIn("bonus", df_clean.columns)
        self.assertTrue(all(df_clean["salary"] >= 90000))
        self.assertEqual(df_clean.iloc[0]["name"], "FRANK")

    def test_5_aggregate_dataset_pivot(self):
        """Test 2D Pivot table and GroupBy aggregations."""
        # 1. Pivot
        res_piv = data_tools.aggregate_dataset(
            source_path=self.xlsx_path,
            sheet_name="Orders",
            pivot_index="region",
            pivot_column="employee_id",
            pivot_value="amount",
            pivot_aggfunc="sum"
        )
        self.assertTrue(res_piv["ok"])
        self.assertGreater(len(res_piv["records"]), 0)

        # 2. GroupBy
        res_grp = data_tools.aggregate_dataset(
            source_path=self.csv_path,
            group_by=["department"],
            aggregations={"salary": ["mean", "max"], "performance_score": "mean"}
        )
        self.assertTrue(res_grp["ok"])
        self.assertEqual(len(res_grp["records"]), 4)

    def test_6_join_datasets(self):
        """Test programmatic join between CSV and Excel with match statistics."""
        out_join = os.path.join(self.temp_dir.name, "emp_orders_joined.csv")
        res = data_tools.join_datasets(
            left_path=self.csv_path,
            right_path=self.xlsx_path,
            left_on="id",
            right_on="employee_id",
            how="inner",
            output_path=out_join,
            right_sheet="Orders"
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["merged_rows"], 5)
        self.assertTrue(os.path.exists(out_join))

    def test_7_generate_excel_dashboard(self):
        """Test multi-sheet executive Excel dashboard generation with formulas and formatting."""
        out_dash = os.path.join(self.temp_dir.name, "executive_dashboard.xlsx")
        sheets = [
            {
                "name": "Q3 Department Summary",
                "data": [
                    {"Department": "Engineering", "Headcount": 12, "Budget": 1400000, "Utilization": 0.92},
                    {"Department": "Sales", "Headcount": 8, "Budget": 850000, "Utilization": 0.88},
                    {"Department": "Marketing", "Headcount": 5, "Budget": 450000, "Utilization": 0.79},
                    {"Department": "HR", "Headcount": 3, "Budget": 220000, "Utilization": 0.95}
                ],
                "formulas": [
                    {"cell": "C8", "formula": "=SUM(C4:C7)", "format": "currency"},
                    {"cell": "D8", "formula": "=AVERAGE(D4:D7)", "format": "percent"}
                ],
                "number_formats": {
                    "Budget": "currency",
                    "Utilization": "percent",
                    "Headcount": "integer"
                },
                "charts": [
                    {
                        "type": "bar",
                        "title": "Budget by Department",
                        "category_column": 1,
                        "value_column": 3
                    }
                ]
            }
        ]
        res = data_tools.generate_excel_dashboard(out_dash, "Corporate Resource Dashboard", sheets)
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.exists(out_dash))
        self.assertGreater(os.path.getsize(out_dash), 1000)

    def test_8_generate_data_report(self):
        """Test generating an interactive HTML analytics report."""
        out_html = os.path.join(self.temp_dir.name, "analytics_report.html")
        metrics = [
            {"label": "Total Employees", "value": "8", "subtext": "+2 this quarter"},
            {"label": "Avg Performance", "value": "4.1", "subtext": "Exceeding expectations"}
        ]
        res = data_tools.generate_data_report(
            source_path=self.csv_path,
            title="HR & Talent Performance Report",
            metrics=metrics,
            output_path=out_html
        )
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.exists(out_html))
        with open(out_html, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("HR & Talent Performance Report", html)
        self.assertIn("Total Employees", html)

if __name__ == "__main__":
    unittest.main()
