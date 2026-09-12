import os
import sys
import json

TASK_A_IR = {
  "format": "pdf",
  "theme": "corporate_blue",
  "meta": {"title": "Process Report", "author": "System Agent"},
  "document": {
    "sections": [
      {"type": "table", "title": "Top CPU", "columns": ["Name", "CPU"], "rows": [["chrome", "50%"]]},
      {"type": "stat_row", "items": [{"label": "Uptime", "value": "5 days"}]}
    ]
  }
}

TASK_D_IR = {
  "format": "pdf",
  "theme": "modern_dark",
  "meta": {"title": "Build Pipeline Report"},
  "slides": [
    {"master": "title", "title": "Pipeline Report", "subtitle": "Sept 2025"},
    {"master": "chart", "title": "Pass Count", "chart_type": "line", "chart_data": {"1": 100, "2": 90}},
    {"master": "stats", "title": "Failures", "stats": [{"label": "Timeout", "value": "10"}]}
  ]
}

TASK_E_IR = {
  "format": "pdf",
  "theme": "cyberpunk",
  "meta": {"title": "Monitoring"},
  "document": {
    "sections": [
      {"type": "prose", "body": "Temp is 45°C and fan is 1200 RPM"}
    ]
  }
}

def run_regressions():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from document_tools import create_pdf, create_ppt
    from doc_quality import score_pdf, score_pptx

    tasks = [
        ("taskA.pdf", TASK_A_IR, create_pdf, score_pdf),
        ("taskD.pdf", TASK_D_IR, create_pdf, score_pdf),
        ("taskD.pptx", TASK_D_IR, create_ppt, score_pptx),
        ("taskE.pdf", TASK_E_IR, create_pdf, score_pdf),
        ("taskE.pptx", TASK_E_IR, create_ppt, score_pptx),
    ]

    failed = False
    for path, ir, create_fn, score_fn in tasks:
        print(f"Generating {path}...")
        kwargs = {"path": os.path.join(os.path.dirname(__file__), path), "ir": ir}
        create_fn(kwargs)
        
        score_res = score_fn(kwargs["path"])
        print(f"Score for {path}: {score_res['score']}/100")
        if not score_res["hard_pass"] or score_res["score"] < 70:
            print(f"FAILED: {path} - {score_res['failures']}")
            failed = True
        else:
            print(f"PASSED: {path}")
            
    if failed:
        sys.exit(1)
    else:
        print("All regressions passed.")
        sys.exit(0)

if __name__ == "__main__":
    run_regressions()
