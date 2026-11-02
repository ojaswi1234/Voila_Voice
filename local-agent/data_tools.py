"""data_tools.py - Enterprise Data Engineering & Analytics Suite for CSV and Excel files.

Provides high-performance data profiling, in-memory SQL querying, ETL transformations,
multi-dimensional aggregations/pivots, multi-sheet Excel dashboard creation, and
interactive HTML analytics reports.
"""

import sys
import os
import json
import csv
import math
import time
import re
import sqlite3
import argparse
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 1. ENCODING & FILE LOADING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

COMMON_ENCODINGS = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]

def detect_csv_delimiter(path: str, encoding: str = "utf-8") -> str:
    """Sniff the CSV delimiter using Python csv.Sniffer with safe fallback."""
    try:
        with open(path, "r", encoding=encoding, errors="ignore") as f:
            sample = f.read(8192)
            if not sample:
                return ","
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
    except Exception:
        return ","

def load_dataset(
    path: str,
    sheet_name: Optional[Union[str, int]] = None,
    nrows: Optional[int] = None,
    usecols: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, str]:
    """Load a CSV or Excel file into a pandas DataFrame with automatic format and encoding detection.
    
    Returns (DataFrame, detected_format_info).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls", ".xlsm", ".xlsb"]:
        # Excel loader
        target_sheet = sheet_name if sheet_name is not None else 0
        df = pd.read_excel(path, sheet_name=target_sheet, nrows=nrows, usecols=usecols)
        actual_sheet = target_sheet
        if isinstance(target_sheet, int):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True)
                actual_sheet = wb.sheetnames[target_sheet] if target_sheet < len(wb.sheetnames) else str(target_sheet)
                wb.close()
            except Exception:
                actual_sheet = f"Sheet{target_sheet}"
        return df, f"Excel (sheet='{actual_sheet}')"

    # CSV / TSV / text loader with encoding fallbacks
    delimiter = None
    last_err = None
    for enc in COMMON_ENCODINGS:
        try:
            if delimiter is None:
                delimiter = detect_csv_delimiter(path, encoding=enc)
            df = pd.read_csv(
                path,
                encoding=enc,
                sep=delimiter,
                nrows=nrows,
                usecols=usecols,
                low_memory=False
            )
            return df, f"CSV (encoding='{enc}', delimiter='{repr(delimiter)[1:-1]}')"
        except Exception as e:
            last_err = e
            continue

    raise ValueError(f"Failed to load dataset at {path}. Last error: {last_err}")

def _serialize_val(val: Any) -> Any:
    """Convert numpy/pandas types to standard JSON-serializable types."""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return str(val)

# ─────────────────────────────────────────────────────────────────────────────
# 2. DATA PROFILING & HEALTH INSPECTION
# ─────────────────────────────────────────────────────────────────────────────

def profile_dataset(
    path: str,
    sheet_name: Optional[Union[str, int]] = None,
    sample_size: int = 100000
) -> Dict[str, Any]:
    """Generate a comprehensive data profile and health inspection for a dataset."""
    t0 = time.perf_counter()
    nrows = sample_size if sample_size and sample_size > 0 else None
    df, fmt_info = load_dataset(path, sheet_name=sheet_name, nrows=nrows)

    total_rows = len(df)
    total_cols = len(df.columns)
    memory_mb = round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2)
    duplicate_rows = int(df.duplicated().sum())

    columns_profile = []
    quality_alerts = []

    if duplicate_rows > 0:
        quality_alerts.append({
            "type": "duplicate_rows",
            "severity": "warning",
            "message": f"Dataset contains {duplicate_rows} duplicate rows ({round(duplicate_rows / max(total_rows, 1) * 100, 2)}%)."
        })

    for col in df.columns:
        s = df[col]
        null_count = int(s.isna().sum())
        null_pct = round(null_count / max(total_rows, 1) * 100, 2)
        unique_count = int(s.nunique(dropna=True))
        dtype_str = str(s.dtype)

        col_info: Dict[str, Any] = {
            "name": str(col),
            "dtype": dtype_str,
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
        }

        # Quality warnings on column
        if null_pct > 25.0:
            quality_alerts.append({
                "type": "high_null_percentage",
                "severity": "warning",
                "column": str(col),
                "message": f"Column '{col}' has {null_pct}% missing values ({null_count}/{total_rows})."
            })
        if unique_count == 1 and total_rows > 1:
            quality_alerts.append({
                "type": "constant_column",
                "severity": "info",
                "column": str(col),
                "message": f"Column '{col}' is constant (only 1 unique value)."
            })
        if unique_count == total_rows and total_rows > 1 and "int" in dtype_str:
            col_info["is_potential_key"] = True

        # Numeric statistics
        if pd.api.types.is_numeric_dtype(s):
            col_info["type_category"] = "numeric"
            s_clean = s.dropna()
            if not s_clean.empty:
                q25 = float(s_clean.quantile(0.25))
                q50 = float(s_clean.quantile(0.50))
                q75 = float(s_clean.quantile(0.75))
                iqr = q75 - q25
                lower_bound = q25 - 1.5 * iqr
                upper_bound = q75 + 1.5 * iqr
                outliers = int(((s_clean < lower_bound) | (s_clean > upper_bound)).sum())

                col_info["stats"] = {
                    "min": _serialize_val(s_clean.min()),
                    "max": _serialize_val(s_clean.max()),
                    "mean": _serialize_val(s_clean.mean()),
                    "std": _serialize_val(s_clean.std()),
                    "median": _serialize_val(q50),
                    "q25": _serialize_val(q25),
                    "q75": _serialize_val(q75),
                    "outliers_count": outliers
                }
                if outliers > 0:
                    quality_alerts.append({
                        "type": "outliers_detected",
                        "severity": "info",
                        "column": str(col),
                        "message": f"Column '{col}' has {outliers} statistical outliers (outside 1.5*IQR)."
                    })
        elif pd.api.types.is_datetime64_any_dtype(s):
            col_info["type_category"] = "datetime"
            s_clean = s.dropna()
            if not s_clean.empty:
                col_info["stats"] = {
                    "min_date": str(s_clean.min()),
                    "max_date": str(s_clean.max())
                }
        else:
            col_info["type_category"] = "categorical"
            # Top 5 most frequent values
            top_vals = s.value_counts(dropna=True).head(5).to_dict()
            col_info["top_values"] = {str(k): int(v) for k, v in top_vals.items()}

        columns_profile.append(col_info)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "path": path,
        "format": fmt_info,
        "rows": total_rows,
        "columns_count": total_cols,
        "memory_mb": memory_mb,
        "duplicates_count": duplicate_rows,
        "columns": columns_profile,
        "alerts": quality_alerts,
        "profiling_duration_ms": elapsed_ms
    }

# ─────────────────────────────────────────────────────────────────────────────
# 3. UNIVERSAL IN-MEMORY SQL QUERY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_SQL_PATTERNS = [
    r"\bATTACH\b", r"\bDETACH\b", r"\bPRAGMA\b", r"\bVACUUM\b",
    r"\bLOAD_EXTENSION\b", r"\bWRITEFILE\b", r"\bREADFILE\b"
]

def query_dataset(
    query: str,
    sources: Dict[str, str],
    sheet_names: Optional[Dict[str, Union[str, int]]] = None,
    output_path: Optional[str] = None,
    max_rows: int = 50
) -> Dict[str, Any]:
    """Execute ANSI SQL against one or more CSV/Excel files using an in-memory SQLite sandbox."""
    t0 = time.perf_counter()

    # Safety check
    upper_query = query.upper()
    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, upper_query, re.IGNORECASE):
            return {
                "ok": False,
                "error": "security_violation",
                "message": f"Forbidden SQL operation detected matching: {pattern}"
            }

    sheet_names = sheet_names or {}
    conn = sqlite3.connect(":memory:")

    try:
        loaded_tables = {}
        for table_name, file_path in sources.items():
            # Validate table name identifier
            clean_name = re.sub(r"[^\w]", "_", table_name)
            sheet = sheet_names.get(table_name)
            df, fmt_info = load_dataset(file_path, sheet_name=sheet)

            # Clean column names for sqlite compatibility
            df.columns = [re.sub(r"[^\w]", "_", str(c)).strip("_") for c in df.columns]
            df.to_sql(clean_name, conn, index=False, if_exists="replace")
            loaded_tables[clean_name] = {
                "source": file_path,
                "rows": len(df),
                "columns": list(df.columns)
            }

        # Execute query
        cursor = conn.cursor()
        cursor.execute(query)
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        all_rows = cursor.fetchall()
        total_result_rows = len(all_rows)

        # Convert to records
        preview_rows = all_rows[:max_rows]
        records = [
            {col_names[i]: _serialize_val(row[i]) for i in range(len(col_names))}
            for row in preview_rows
        ]

        result_export_path = None
        if output_path:
            res_df = pd.DataFrame(all_rows, columns=col_names)
            out_ext = os.path.splitext(output_path)[1].lower()
            if out_ext in [".xlsx", ".xls"]:
                res_df.to_excel(output_path, index=False)
            else:
                res_df.to_csv(output_path, index=False, encoding="utf-8")
            result_export_path = output_path

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "ok": True,
            "query": query,
            "tables_loaded": loaded_tables,
            "total_rows": total_result_rows,
            "columns": col_names,
            "records": records,
            "truncated": total_result_rows > max_rows,
            "exported_to": result_export_path,
            "execution_duration_ms": elapsed_ms
        }
    except Exception as e:
        return {
            "ok": False,
            "error": "sql_execution_error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 4. DATA ENGINEERING & TRANSFORMATION PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def transform_dataset(
    source_path: str,
    output_path: str,
    steps: List[Dict[str, Any]],
    sheet_name: Optional[Union[str, int]] = None
) -> Dict[str, Any]:
    """Execute a sequential data transformation/cleaning pipeline on a dataset."""
    t0 = time.perf_counter()
    df, fmt_info = load_dataset(source_path, sheet_name=sheet_name)
    initial_rows, initial_cols = len(df), len(df.columns)
    step_logs = []

    for idx, step in enumerate(steps, 1):
        action = step.get("action", "")
        desc = f"Step {idx}: {action}"

        try:
            if action == "rename_columns":
                mapping = step.get("mapping", {})
                df = df.rename(columns=mapping)
                step_logs.append(f"{desc} (renamed {len(mapping)} columns)")

            elif action == "drop_columns":
                cols = step.get("columns", [])
                existing_cols = [c for c in cols if c in df.columns]
                df = df.drop(columns=existing_cols)
                step_logs.append(f"{desc} (dropped {len(existing_cols)} columns)")

            elif action == "keep_columns":
                cols = step.get("columns", [])
                existing_cols = [c for c in cols if c in df.columns]
                df = df[existing_cols]
                step_logs.append(f"{desc} (retained {len(existing_cols)} columns)")

            elif action == "drop_duplicates":
                subset = step.get("subset", None)
                keep = step.get("keep", "first")
                before = len(df)
                df = df.drop_duplicates(subset=subset, keep=keep)
                step_logs.append(f"{desc} (removed {before - len(df)} duplicate rows)")

            elif action == "fill_na":
                column = step.get("column")
                strategy = step.get("strategy", "zero")
                val = step.get("value", None)

                if column and column in df.columns:
                    target_cols = [column]
                else:
                    target_cols = list(df.columns)

                for c in target_cols:
                    if strategy == "mean" and pd.api.types.is_numeric_dtype(df[c]):
                        df[c] = df[c].fillna(df[c].mean())
                    elif strategy == "median" and pd.api.types.is_numeric_dtype(df[c]):
                        df[c] = df[c].fillna(df[c].median())
                    elif strategy == "mode":
                        mode_val = df[c].mode()
                        if not mode_val.empty:
                            df[c] = df[c].fillna(mode_val.iloc[0])
                    elif strategy == "forward_fill":
                        df[c] = df[c].ffill()
                    elif strategy == "backward_fill":
                        df[c] = df[c].bfill()
                    elif strategy == "value" and val is not None:
                        df[c] = df[c].fillna(val)
                    elif strategy == "empty":
                        df[c] = df[c].fillna("")
                    else:
                        df[c] = df[c].fillna(0)
                step_logs.append(f"{desc} (filled nulls using strategy='{strategy}')")

            elif action == "filter":
                expr = step.get("expression", "")
                if expr:
                    before = len(df)
                    df = df.query(expr)
                    step_logs.append(f"{desc} (filter: '{expr}', preserved {len(df)} of {before} rows)")

            elif action == "cast_types":
                types_map = step.get("types", {})
                for col_name, target_type in types_map.items():
                    if col_name not in df.columns:
                        continue
                    if target_type in ["int", "int64"]:
                        df[col_name] = pd.to_numeric(df[col_name], errors="coerce").fillna(0).astype(int)
                    elif target_type in ["float", "float64"]:
                        df[col_name] = pd.to_numeric(df[col_name], errors="coerce")
                    elif target_type in ["str", "string"]:
                        df[col_name] = df[col_name].astype(str)
                    elif target_type in ["datetime", "date"]:
                        df[col_name] = pd.to_datetime(df[col_name], errors="coerce")
                    elif target_type == "bool":
                        df[col_name] = df[col_name].astype(bool)
                step_logs.append(f"{desc} (cast {len(types_map)} column types)")

            elif action == "calculate_column":
                target_col = step.get("target_column")
                formula = step.get("formula")
                if target_col and formula:
                    df[target_col] = df.eval(formula)
                    step_logs.append(f"{desc} (created column '{target_col}' = {formula})")

            elif action == "string_clean":
                cols = step.get("columns", [])
                do_trim = step.get("trim", True)
                case_mode = step.get("case", None) # 'lower', 'upper', 'title'
                pattern = step.get("regex_replace_pattern", None)
                replacement = step.get("regex_replace_with", "")

                for c in cols:
                    if c in df.columns and pd.api.types.is_string_dtype(df[c]):
                        if do_trim:
                            df[c] = df[c].str.strip()
                        if case_mode == "lower":
                            df[c] = df[c].str.lower()
                        elif case_mode == "upper":
                            df[c] = df[c].str.upper()
                        elif case_mode == "title":
                            df[c] = df[c].str.title()
                        if pattern:
                            df[c] = df[c].str.replace(pattern, replacement, regex=True)
                step_logs.append(f"{desc} (cleaned {len(cols)} string columns)")

            elif action == "sort_by":
                columns = step.get("columns", [])
                ascending = step.get("ascending", True)
                if isinstance(columns, str):
                    columns = [columns]
                existing = [c for c in columns if c in df.columns]
                if existing:
                    df = df.sort_values(by=existing, ascending=ascending)
                    step_logs.append(f"{desc} (sorted by {existing})")

            else:
                step_logs.append(f"{desc} (SKIPPED: unknown action '{action}')")

        except Exception as e:
            return {
                "ok": False,
                "error": "pipeline_step_failed",
                "step_index": idx,
                "step_action": action,
                "message": str(e),
                "steps_completed": step_logs
            }

    # Save output file
    out_ext = os.path.splitext(output_path)[1].lower()
    if out_ext in [".xlsx", ".xls"]:
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False, encoding="utf-8")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "source_path": source_path,
        "output_path": output_path,
        "initial_shape": [initial_rows, initial_cols],
        "final_shape": [len(df), len(df.columns)],
        "steps_executed": step_logs,
        "duration_ms": elapsed_ms
    }

# ─────────────────────────────────────────────────────────────────────────────
# 5. MULTI-DIMENSIONAL AGGREGATIONS & PIVOTS
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_dataset(
    source_path: str,
    group_by: Optional[List[str]] = None,
    aggregations: Optional[Dict[str, Union[str, List[str]]]] = None,
    pivot_index: Optional[str] = None,
    pivot_column: Optional[str] = None,
    pivot_value: Optional[str] = None,
    pivot_aggfunc: str = "sum",
    output_path: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = None
) -> Dict[str, Any]:
    """Calculate multi-metric GroupBy summaries or 2D Pivot Matrices."""
    t0 = time.perf_counter()
    df, fmt_info = load_dataset(source_path, sheet_name=sheet_name)

    if pivot_index and pivot_column and pivot_value:
        # Pivot table flow
        if pivot_index not in df.columns or pivot_column not in df.columns or pivot_value not in df.columns:
            return {
                "ok": False,
                "error": "invalid_pivot_columns",
                "message": f"One or more pivot columns not found in {list(df.columns)}"
            }
        piv = pd.pivot_table(
            df,
            index=pivot_index,
            columns=pivot_column,
            values=pivot_value,
            aggfunc=pivot_aggfunc,
            fill_value=0
        ).reset_index()
        # Flatten MultiIndex columns if needed
        piv.columns = [str(c) for c in piv.columns]
        result_df = piv
        summary_type = f"pivot ({pivot_index} x {pivot_column})"
    elif group_by and aggregations:
        # Standard GroupBy flow
        valid_grp = [c for c in group_by if c in df.columns]
        if not valid_grp:
            return {
                "ok": False,
                "error": "invalid_group_by",
                "message": f"None of group_by columns {group_by} found in {list(df.columns)}"
            }
        grouped = df.groupby(valid_grp).agg(aggregations).reset_index()
        # Flatten MultiIndex columns
        if isinstance(grouped.columns, pd.MultiIndex):
            grouped.columns = [
                f"{c[0]}_{c[1]}" if c[1] and c[1] != "" else c[0]
                for c in grouped.columns
            ]
        result_df = grouped
        summary_type = f"groupby ({', '.join(valid_grp)})"
    else:
        return {
            "ok": False,
            "error": "missing_parameters",
            "message": "Must provide either (group_by + aggregations) or (pivot_index + pivot_column + pivot_value)"
        }

    # Export if requested
    if output_path:
        out_ext = os.path.splitext(output_path)[1].lower()
        if out_ext in [".xlsx", ".xls"]:
            result_df.to_excel(output_path, index=False)
        else:
            result_df.to_csv(output_path, index=False, encoding="utf-8")

    preview_records = [
        {k: _serialize_val(v) for k, v in row.items()}
        for row in result_df.head(50).to_dict(orient="records")
    ]

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "ok": True,
        "summary_type": summary_type,
        "rows_count": len(result_df),
        "columns": list(result_df.columns),
        "records": preview_records,
        "output_path": output_path,
        "duration_ms": elapsed_ms
    }

# ─────────────────────────────────────────────────────────────────────────────
# 6. MULTI-DATASET JOINING
# ─────────────────────────────────────────────────────────────────────────────

def join_datasets(
    left_path: str,
    right_path: str,
    how: str = "inner",
    on: Optional[Union[str, List[str]]] = None,
    left_on: Optional[Union[str, List[str]]] = None,
    right_on: Optional[Union[str, List[str]]] = None,
    output_path: Optional[str] = None,
    left_sheet: Optional[Union[str, int]] = None,
    right_sheet: Optional[Union[str, int]] = None
) -> Dict[str, Any]:
    """Join two CSV/Excel datasets and calculate match statistics."""
    t0 = time.perf_counter()
    left_df, _ = load_dataset(left_path, sheet_name=left_sheet)
    right_df, _ = load_dataset(right_path, sheet_name=right_sheet)

    len_left, len_right = len(left_df), len(right_df)

    try:
        merged = pd.merge(
            left_df,
            right_df,
            how=how,
            on=on,
            left_on=left_on,
            right_on=right_on,
            indicator=True
        )
        match_counts = merged["_merge"].value_counts().to_dict()
        both_count = int(match_counts.get("both", 0))
        left_only = int(match_counts.get("left_only", 0))
        right_only = int(match_counts.get("right_only", 0))
        merged = merged.drop(columns=["_merge"])

        if output_path:
            out_ext = os.path.splitext(output_path)[1].lower()
            if out_ext in [".xlsx", ".xls"]:
                merged.to_excel(output_path, index=False)
            else:
                merged.to_csv(output_path, index=False, encoding="utf-8")

        preview = [
            {k: _serialize_val(v) for k, v in row.items()}
            for row in merged.head(30).to_dict(orient="records")
        ]

        match_rate = round(both_count / max(len_left, 1) * 100, 2)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "ok": True,
            "how": how,
            "left_rows": len_left,
            "right_rows": len_right,
            "merged_rows": len(merged),
            "matched_both": both_count,
            "left_only": left_only,
            "right_only": right_only,
            "match_rate_pct": match_rate,
            "columns": list(merged.columns),
            "preview": preview,
            "output_path": output_path,
            "duration_ms": elapsed_ms
        }
    except Exception as e:
        return {
            "ok": False,
            "error": "join_failed",
            "message": str(e)
        }

# ─────────────────────────────────────────────────────────────────────────────
# 7. EXECUTIVE MULTI-SHEET EXCEL DASHBOARD ARCHITECT
# ─────────────────────────────────────────────────────────────────────────────

def generate_excel_dashboard(
    path: str,
    title: str,
    sheets: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Generate a high-end, multi-sheet Excel workbook with native dynamic formulas,
    styling palettes, auto-fit column widths, and embedded charts.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference

    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    # Corporate styling tokens
    font_title = Font(name="Segoe UI", size=16, bold=True, color="1E293B")
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_body = Font(name="Segoe UI", size=10, color="334155")
    font_summary = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

    fill_header = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_summary = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0")
    )

    created_sheets = []

    for sheet_def in sheets:
        sheet_name = sheet_def.get("name", "Data")[:31] # Max 31 chars in Excel
        ws = wb.create_sheet(title=sheet_name)
        data = sheet_def.get("data", [])
        formulas = sheet_def.get("formulas", []) # [{"cell": "D10", "formula": "=SUM(D2:D9)", "format": "currency"}]
        charts = sheet_def.get("charts", [])
        number_formats = sheet_def.get("number_formats", {}) # {"revenue": "currency", "growth": "percent"}

        if not data:
            ws.cell(row=1, column=1, value="No data provided")
            created_sheets.append(sheet_name)
            continue

        # Extract headers & rows
        if isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [[row.get(h, "") for h in headers] for row in data]
        else:
            headers = [str(x) for x in data[0]]
            rows = data[1:]

        # 1. Title Banner
        ws.cell(row=1, column=1, value=title).font = font_title
        ws.row_dimensions[1].height = 28

        # 2. Table Headers at Row 3
        start_row = 3
        for col_idx, header_text in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header_text)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border
        ws.row_dimensions[start_row].height = 24

        # 3. Populate Data Rows
        for r_idx, row_values in enumerate(rows, start_row + 1):
            is_even = (r_idx % 2 == 0)
            ws.row_dimensions[r_idx].height = 19
            for c_idx, val in enumerate(row_values, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = font_body
                cell.border = thin_border
                if is_even:
                    cell.fill = fill_zebra

                # Apply number formatting
                col_name = headers[c_idx - 1] if c_idx - 1 < len(headers) else ""
                fmt = number_formats.get(col_name, "")
                if fmt == "currency":
                    cell.number_format = "$#,##0.00"
                elif fmt == "percent":
                    cell.number_format = "0.0%"
                elif fmt == "integer":
                    cell.number_format = "#,##0"
                elif fmt == "date":
                    cell.number_format = "YYYY-MM-DD"

        last_data_row = start_row + len(rows)

        # 4. Inject Dynamic Formulas
        for form_info in formulas:
            target_cell = form_info.get("cell")
            formula_str = form_info.get("formula")
            f_format = form_info.get("format", "")
            if target_cell and formula_str:
                c = ws[target_cell]
                c.value = formula_str
                c.font = font_summary
                c.fill = fill_summary
                c.border = thin_border
                if f_format == "currency":
                    c.number_format = "$#,##0.00"
                elif f_format == "percent":
                    c.number_format = "0.0%"
                elif f_format == "integer":
                    c.number_format = "#,##0"

        # 5. Auto-fit column widths
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val_str = str(cell.value or "")
                if not val_str.startswith("="): # don't measure raw formula text
                    max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # Freeze panes at data start
        ws.freeze_panes = f"A{start_row + 1}"

        # 6. Render Native Embedded Charts
        for chart_info in charts:
            ctype = chart_info.get("type", "bar")
            c_title = chart_info.get("title", "Chart")
            cat_col = chart_info.get("category_column", 1)
            val_col = chart_info.get("value_column", 2)
            c_pos = chart_info.get("position", f"{get_column_letter(len(headers) + 2)}3")

            if ctype == "pie":
                chart_obj = PieChart()
            elif ctype == "line":
                chart_obj = LineChart()
            else:
                chart_obj = BarChart()
                chart_obj.type = "col"
                chart_obj.style = 10

            chart_obj.title = c_title
            data_ref = Reference(ws, min_col=val_col, min_row=start_row, max_row=last_data_row)
            cats_ref = Reference(ws, min_col=cat_col, min_row=start_row + 1, max_row=last_data_row)
            chart_obj.add_data(data_ref, titles_from_data=True)
            chart_obj.set_categories(cats_ref)
            chart_obj.width = 15
            chart_obj.height = 10
            ws.add_chart(chart_obj, c_pos)

        created_sheets.append(sheet_name)

    wb.save(path)
    return {
        "ok": True,
        "path": path,
        "title": title,
        "sheets_created": created_sheets,
        "message": f"Successfully generated executive Excel dashboard at {path}"
    }

# ─────────────────────────────────────────────────────────────────────────────
# 8. INTERACTIVE HTML REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_data_report(
    source_path: str,
    title: str,
    summary_notes: Optional[str] = None,
    metrics: Optional[List[Dict[str, str]]] = None,
    charts: Optional[List[Dict[str, Any]]] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """Generate a self-contained, responsive modern HTML analytics dashboard artifact."""
    df, _ = load_dataset(source_path, nrows=500)
    metrics = metrics or []
    summary_notes = summary_notes or f"Automated analytical profile for {os.path.basename(source_path)}"

    if not output_path:
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        output_path = os.path.join(os.path.dirname(source_path), f"{base_name}_report.html")

    # Build metric cards HTML
    metric_cards_html = ""
    for m in metrics:
        metric_cards_html += f"""
        <div class="kpi-card">
            <div class="kpi-label">{m.get('label', '')}</div>
            <div class="kpi-value">{m.get('value', '')}</div>
            <div class="kpi-sub">{m.get('subtext', '')}</div>
        </div>
        """

    # Build table HTML preview
    preview_df = df.head(50)
    table_headers = "".join([f"<th>{c}</th>" for c in preview_df.columns])
    table_rows = ""
    for _, row in preview_df.iterrows():
        cells = "".join([f"<td>{_serialize_val(val)}</td>" for val in row])
        table_rows += f"<tr>{cells}</tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-card: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --border: #334155;
            --success: #10b981;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            margin: 0;
            padding: 30px;
        }}
        .header {{
            margin-bottom: 25px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 15px;
        }}
        h1 {{
            font-size: 26px;
            font-weight: 700;
            margin: 0 0 8px 0;
            color: var(--text-primary);
        }}
        .summary-text {{
            color: var(--text-secondary);
            font-size: 14px;
            line-height: 1.5;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .kpi-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 28px;
            font-weight: 700;
            color: var(--accent);
        }}
        .kpi-sub {{
            font-size: 12px;
            color: var(--success);
            margin-top: 4px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 12px;
        }}
        .table-container {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow-x: auto;
            max-height: 500px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        th {{
            background: #111827;
            color: var(--text-secondary);
            font-weight: 600;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            white-space: nowrap;
        }}
        td {{
            padding: 10px 16px;
            border-bottom: 1px solid var(--border);
            color: #cbd5e1;
            white-space: nowrap;
        }}
        tr:hover td {{
            background: #283548;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="summary-text">{summary_notes}</div>
    </div>

    <div class="kpi-grid">
        {metric_cards_html}
    </div>

    <div class="section-title">Data Sample (First 50 Rows)</div>
    <div class="table-container">
        <table>
            <thead>
                <tr>{table_headers}</tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return {
        "ok": True,
        "output_path": output_path,
        "title": title,
        "message": f"Interactive analytics report generated at {output_path}"
    }

# ─────────────────────────────────────────────────────────────────────────────
# 9. CLI & JSON DISPATCH ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

ACTION_MAP = {
    "profile_dataset": profile_dataset,
    "query_dataset": query_dataset,
    "transform_dataset": transform_dataset,
    "aggregate_dataset": aggregate_dataset,
    "join_datasets": join_datasets,
    "generate_excel_dashboard": generate_excel_dashboard,
    "generate_data_report": generate_data_report,
}

def dispatch_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action", "")
    kwargs = payload.get("kwargs", {})
    if action not in ACTION_MAP:
        return {
            "ok": False,
            "error": "unknown_action",
            "message": f"Action '{action}' is not supported. Supported: {list(ACTION_MAP.keys())}"
        }
    fn = ACTION_MAP[action]
    try:
        return fn(**kwargs)
    except Exception as e:
        return {
            "ok": False,
            "error": "execution_failed",
            "action": action,
            "message": str(e),
            "traceback": traceback.format_exc()
        }

if __name__ == "__main__":
    if not sys.stdin.isatty():
        # JSON-RPC Stdin Mode
        try:
            raw_input = sys.stdin.read().strip()
            if raw_input:
                payload = json.loads(raw_input)
                result = dispatch_payload(payload)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(0 if result.get("ok", False) else 1)
        except Exception as e:
            print(json.dumps({"ok": False, "error": "stdin_parse_error", "message": str(e)}))
            sys.exit(1)

    # CLI Args Mode
    parser = argparse.ArgumentParser(description="Voila Data Engineering & Analytics CLI")
    parser.add_argument("--action", required=True, choices=list(ACTION_MAP.keys()))
    parser.add_argument("--kwargs", type=str, default="{}", help="JSON string of kwargs")
    args = parser.parse_args()

    try:
        kwargs_dict = json.loads(args.kwargs)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "invalid_json_kwargs", "message": str(e)}))
        sys.exit(1)

    res = dispatch_payload({"action": args.action, "kwargs": kwargs_dict})
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("ok", False) else 1)
