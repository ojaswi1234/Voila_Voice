import os
import pytest
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from document_tools import create_pdf, create_ppt
from doc_quality import score_pdf, score_pptx

T1_IR = {
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

T3_IR = {
  "format": "pdf",
  "theme": "modern_dark",
  "meta": {"title": "Monitoring"},
  "document": {
    "sections": [
      {"type": "prose", "body": "Temp is 45°C and fan is 1200 RPM"}
    ]
  }
}

T4_IR = {
  "format": "pdf",
  "theme": "cyberpunk",
  "meta": {"title": "Sanitizer Test"},
  "document": {
    "sections": [
      {"type": "prose", "body": "This has a shell injection: $(Get-Date -Format 'yyyy-MM-dd')"}
    ]
  }
}

@pytest.fixture(autouse=True)
def setup_teardown():
    yield
    for f in ["test_t1.pdf", "test_t3.pdf", "test_t4.pdf", "test_t1.pptx"]:
        if os.path.exists(f): os.remove(f)

def test_t1_pdf():
    create_pdf({"path": "test_t1.pdf", "content": "# Process Report\n## Top CPU\n| Name | CPU |\n| chrome | 50% |\nUptime: 5 days"})
    score = score_pdf("test_t1.pdf")
    assert score["hard_pass"], f"Failures: {score['failures']}"
    assert score["score"] >= 70

def test_t3_pdf():
    create_pdf({"path": "test_t3.pdf", "content": "Temp is 45°C and fan is 1200 RPM"})
    score = score_pdf("test_t3.pdf")
    assert score["hard_pass"]
    assert "Has 45°C" in score["subscores"]

def test_t4_pdf():
    create_pdf({"path": "test_t4.pdf", "content": "This has a shell injection: $(Get-Date -Format 'yyyy-MM-dd')"})
    score = score_pdf("test_t4.pdf")
    assert not score["hard_pass"]
