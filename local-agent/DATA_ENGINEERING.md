# Data Engineering & Analytics Suite — Voila Local Agent

Enterprise-grade tabular data processing, quality profiling, in-memory SQL querying, ETL transformation, pivot matrices, and executive multi-sheet Excel synthesis for CSV and Excel files.

---

## 1. Quick Start

### Profile a Dataset
```bash
python data_tools.py --action profile_dataset --kwargs '{"path": "C:/data/sales.csv"}'
```

### Run ANSI SQL across CSV and Excel
```bash
python data_tools.py --action query_dataset --kwargs '{
  "query": "SELECT c.tier, SUM(t.amount) as total_rev FROM t JOIN c ON t.cust_id = c.id GROUP BY c.tier ORDER BY total_rev DESC",
  "sources": {"t": "C:/data/txns.xlsx", "c": "C:/data/customers.csv"},
  "sheet_names": {"t": "Transactions"}
}'
```

### Execute an ETL Transformation Pipeline
```bash
python data_tools.py --action transform_dataset --kwargs '{
  "source_path": "C:/data/raw_leads.csv",
  "output_path": "C:/data/clean_leads.csv",
  "steps": [
    {"action": "string_clean", "columns": ["email", "company"], "trim": true, "case": "lower"},
    {"action": "fill_na", "column": "deal_size", "strategy": "median"},
    {"action": "calculate_column", "target_column": "projected_arr", "formula": "deal_size * 12"},
    {"action": "filter", "expression": "projected_arr > 10000"},
    {"action": "sort_by", "columns": "projected_arr", "ascending": false}
  ]
}'
```

### Build an Executive Multi-Sheet Excel Dashboard with Formulas
```bash
python data_tools.py --action generate_excel_dashboard --kwargs '{
  "path": "C:/data/Executive_Q1_Model.xlsx",
  "title": "Corporate Resource & Revenue Allocation",
  "sheets": [
    {
      "name": "Summary KPI",
      "data": [
        {"Department": "Engineering", "Headcount": 15, "Budget": 1800000},
        {"Department": "Sales", "Headcount": 10, "Budget": 1200000}
      ],
      "formulas": [
        {"cell": "B6", "formula": "=SUM(B4:B5)", "format": "integer"},
        {"cell": "C6", "formula": "=SUM(C4:C5)", "format": "currency"}
      ],
      "number_formats": {"Budget": "currency", "Headcount": "integer"},
      "charts": [{"type": "bar", "title": "Budget by Department", "category_column": 1, "value_column": 3}]
    }
  ]
}'
```

---

## 2. Dependencies & Runtime

| Engine | Package | Purpose |
|---|---|---|
| Vectorized Core | `pandas` + `numpy` | High-performance memory structures, vectorized transformations, and statistics |
| Relational Virtual DB | `sqlite3` (stdlib) | Zero-overhead, in-memory ANSI SQL query execution across disparate files |
| Workbook Synthesis | `openpyxl` + `xlsxwriter` | Multi-sheet Excel architecture, styling, conditional formatting, dynamic formulas, charts |

---

## 3. Tool Specifications

### 1. `profile_dataset`
- **Inputs**: `path` (str), `sheet_name` (optional str), `sample_size` (int, default 100000)
- **Outputs**:
  - Dimensions (`rows`, `columns_count`, `memory_mb`, `duplicates_count`)
  - Detected format & encoding (e.g. `CSV (encoding='utf-8', delimiter=',')`)
  - Column Profiles:
    - `null_count`, `null_pct`, `unique_count`, `dtype`, `type_category`
    - Numeric statistics: `min`, `max`, `mean`, `std`, `median`, `q25`, `q75`, `outliers_count`
    - Categorical statistics: `top_values` frequency map
    - Datetime statistics: `min_date`, `max_date`
  - Quality Alerts: warnings for high missingness (>25%), constant columns, duplicate rows, and statistical anomalies.

### 2. `query_dataset`
- **Inputs**:
  - `query` (str): Full ANSI SQL syntax
  - `sources` (dict): Table name mapping to file paths (`{"t1": "path.csv", "t2": "path.xlsx"}`)
  - `sheet_names` (optional dict): Mapping for Excel sources
  - `output_path` (optional str): Export destination for query results (`.csv` or `.xlsx`)
  - `max_rows` (int, default 50): Number of preview rows in JSON response
- **Features**:
  - Full relational power: `JOIN`, `GROUP BY`, `HAVING`, window functions (`ROW_NUMBER() OVER (...)`), `UNION ALL`, `CASE WHEN`.
  - Sandboxed execution: read-only memory database; blocking PRAGMAs, ATTACH, and filesystem extensions.

### 3. `transform_dataset`
- **Inputs**: `source_path` (str), `output_path` (str), `steps` (list of dicts)
- **Supported Steps**:
  - `rename_columns`: `{"old_col": "new_col"}`
  - `drop_columns` / `keep_columns`: list of column names
  - `drop_duplicates`: optional `subset` and `keep` ("first" / "last")
  - `fill_na`: `strategy` $\in$ (`mean`, `median`, `mode`, `forward_fill`, `backward_fill`, `zero`, `empty`, `value`)
  - `cast_types`: `int`, `float`, `str`, `datetime`, `bool`
  - `calculate_column`: formula string evaluated on columns (e.g. `salary * (1 + bonus_pct)`)
  - `string_clean`: `trim`, `case` ("lower", "upper", "title"), `regex_replace_pattern`
  - `filter`: expression string (e.g. `status == 'Active' and score >= 80`)
  - `sort_by`: column list and `ascending` boolean

### 4. `aggregate_dataset`
- **Inputs**: `source_path` (str), `group_by` (list), `aggregations` (dict) OR `pivot_index`, `pivot_column`, `pivot_value`, `pivot_aggfunc`
- **Outputs**: Aggregation summary with preview records and optional output export.

### 5. `join_datasets`
- **Inputs**: `left_path`, `right_path`, `how` (`inner`, `left`, `right`, `outer`), `on` / `left_on` / `right_on`, `output_path`
- **Outputs**: Match statistics (`left_rows`, `right_rows`, `merged_rows`, `matched_both`, `match_rate_pct`).

### 6. `generate_excel_dashboard`
- **Inputs**: `path` (str), `title` (str), `sheets` (list of sheet objects)
- **Features**:
  - Multiple named sheets within one workbook.
  - Native Excel dynamic formulas (`=SUM(B4:B20)`, `=AVERAGE(C4:C20)`, `=COUNTIF(...)`).
  - Auto-fit column widths based on longest string + padding.
  - Corporate palette typography, freeze-panes, zebra striping, and thin borders.
  - Native embedded charts (Bar, Line, Pie).

### 7. `generate_data_report`
- **Inputs**: `source_path` (str), `title` (str), `summary_notes` (str), `metrics` (list of KPI cards), `output_path` (str)
- **Outputs**: Self-contained, responsive dark-mode HTML analytics dashboard artifact.
