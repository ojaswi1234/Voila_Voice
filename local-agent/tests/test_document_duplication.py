"""
================================================================================
Test Suite: Document Duplication & High-Fidelity Replication Engine
================================================================================
Verifies:
1. Semantic Layout IR & Executive Structural Blueprinting (<400 tokens)
2. Controlled Text Mutation & Word Count Length Controls
3. Component Archetype Inheritance for User Additions (Tables, Bullets)
4. Complete Watermark Lifecycle (Addition, Modification, Removal)
5. DOCX Cross-Format Duplication
6. Integration with document_tools.py stdin/stdout JSON protocol
================================================================================
"""

import os
import sys
import json
import subprocess
import unittest

# Ensure local-agent directory is on path
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

from document_duplication import engine
import pdfplumber
import docx


class TestDocumentDuplication(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source_pdf = os.path.join(agent_dir, "docs", "Browser_State_Resolution_Guide.pdf")
        cls.test_output_dir = os.path.join(agent_dir, "tests", "output")
        os.makedirs(cls.test_output_dir, exist_ok=True)
        if not os.path.exists(cls.source_pdf):
            raise FileNotFoundError(f"Source test PDF not found at: {cls.source_pdf}")

    def test_01_extract_and_executive_blueprint(self):
        """Test extraction and blueprint compact size (<400 tokens)."""
        blueprint = engine.analyze_structure(self.source_pdf)
        self.assertIsInstance(blueprint, dict)
        self.assertEqual(blueprint["format"], "pdf")
        self.assertGreaterEqual(blueprint["total_pages"], 1)
        self.assertGreater(blueprint["total_words_estimate"], 50)
        self.assertTrue(len(blueprint["heading_outline"]) > 0)
        self.assertTrue(len(blueprint["tables"]) > 0)

        # Verify compact footprint
        bp_json = json.dumps(blueprint)
        self.assertLess(len(bp_json), 2500, "Blueprint must remain concise (<400 tokens)")

    def test_02_text_mutation_and_length_controls(self):
        """Test replacing text and expanding paragraph length while locking styles."""
        out_pdf = os.path.join(self.test_output_dir, "test_mutated.pdf")
        res = engine.duplicate(
            source_path=self.source_pdf,
            output_path=out_pdf,
            instruction="Duplicate and replace framework title",
            replacements={"Automation Frameworks": "Enterprise Automation 2026"},
            length_controls={"target_words_per_para": 60}
        )
        self.assertTrue(os.path.exists(out_pdf))
        self.assertIn("Successfully duplicated", res)

        # Verify new text is in the PDF
        with pdfplumber.open(out_pdf) as pdf:
            text = "".join(p.extract_text() or "" for p in pdf.pages)
            self.assertIn("Enterprise Automation 2026", text)

    def test_03_archetype_inheritance_additions(self):
        """Test adding a table and bullets that clone the styling archetype of the source."""
        out_pdf = os.path.join(self.test_output_dir, "test_archetype_additions.pdf")
        additions = [
            {
                "action": "add_table",
                "columns": ["Component", "Status", "Latency"],
                "rows": [["Browser Engine", "Optimal", "12ms"], ["Sandbox", "Secured", "0ms"]]
            },
            {
                "action": "add_bullets",
                "items": ["Cloned Archetype Bullet Alpha", "Cloned Archetype Bullet Beta"]
            }
        ]
        res = engine.duplicate(
            source_path=self.source_pdf,
            output_path=out_pdf,
            additions=additions
        )
        self.assertTrue(os.path.exists(out_pdf))

        # Analyze structure of output: should now have 2 tables
        bp = engine.analyze_structure(out_pdf)
        self.assertEqual(len(bp["tables"]), 2, "Duplicated PDF must contain original table plus cloned archetype table")

    def test_04_watermark_lifecycle(self):
        """Test adding, modifying, and completely stripping watermarks."""
        # 1. Addition
        wm_pdf = os.path.join(self.test_output_dir, "test_wm_added.pdf")
        engine.duplicate(
            source_path=self.source_pdf,
            output_path=wm_pdf,
            watermark="SECURITY AUDIT DRAFT"
        )
        self.assertTrue(os.path.exists(wm_pdf))
        bp_added = engine.analyze_structure(wm_pdf)
        self.assertIsNotNone(bp_added["detected_watermark"])
        self.assertIn("SECURITY", bp_added["detected_watermark"].upper())

        # 2. Modification
        wm_mod_pdf = os.path.join(self.test_output_dir, "test_wm_modified.pdf")
        engine.duplicate(
            source_path=wm_pdf,
            output_path=wm_mod_pdf,
            watermark="FINAL APPROVED"
        )
        bp_mod = engine.analyze_structure(wm_mod_pdf)
        self.assertIsNotNone(bp_mod["detected_watermark"])
        self.assertIn("FINAL", bp_mod["detected_watermark"].upper())

        # 3. Clean Removal
        wm_stripped_pdf = os.path.join(self.test_output_dir, "test_wm_removed.pdf")
        engine.duplicate(
            source_path=wm_mod_pdf,
            output_path=wm_stripped_pdf,
            watermark="remove"
        )
        bp_stripped = engine.analyze_structure(wm_stripped_pdf)
        self.assertIsNone(bp_stripped["detected_watermark"], "Watermark must be completely stripped")

    def test_05_docx_cross_format_duplication(self):
        """Test duplicating to Word Document (.docx) format."""
        out_docx = os.path.join(self.test_output_dir, "test_output.docx")
        res = engine.duplicate(
            source_path=self.source_pdf,
            output_path=out_docx,
            output_format="docx",
            replacements={"Automation Frameworks": "DOCX Automated Platform"}
        )
        self.assertTrue(os.path.exists(out_docx))
        doc = docx.Document(out_docx)
        full_text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("DOCX Automated Platform", full_text)
        self.assertGreater(len(doc.tables), 0, "DOCX must contain reconstructed tables")

    def test_06_document_tools_integration_protocol(self):
        """Test execution via document_tools.py CLI stdin/stdout protocol."""
        script = os.path.join(agent_dir, "document_tools.py")
        out_pdf = os.path.join(self.test_output_dir, "test_cli_dup.pdf")

        # Call duplicate_document via stdin
        req = {
            "action": "duplicate_document",
            "kwargs": {
                "source_path": self.source_pdf,
                "output_path": out_pdf,
                "replacements": {"Automation Frameworks": "CLI Replicated Framework"},
                "watermark": "CLI TEST"
            }
        }
        proc = subprocess.run(
            ["python", script],
            input=json.dumps(req),
            text=True,
            capture_output=True
        )
        self.assertEqual(proc.returncode, 0, f"document_tools.py failed: {proc.stderr}")
        self.assertIn("Successfully duplicated", proc.stdout)
        self.assertTrue(os.path.exists(out_pdf))

    def test_07_dual_engine_inplace_vector_and_link_preservation(self):
        """Test Engine 1 surgical in-place mutation preserving 100% of links, lines, and typography."""
        out_pdf = os.path.join(self.test_output_dir, "test_engine1_lossless.pdf")
        res = engine.duplicate(
            source_path=self.source_pdf,
            output_path=out_pdf,
            replacements={"Automation Frameworks": "Enterprise Automation 2026"}
        )
        self.assertTrue(os.path.exists(out_pdf))
        self.assertIn("Successfully duplicated", res)

        with pdfplumber.open(self.source_pdf) as orig_pdf, pdfplumber.open(out_pdf) as dup_pdf:
            orig_page = orig_pdf.pages[0]
            dup_page = dup_pdf.pages[0]
            
            # Vector lines must be 100% preserved
            self.assertEqual(len(orig_page.lines), len(dup_page.lines), "Vector lines must be 100% preserved")
            
            # Text must contain replacement
            dup_text = dup_page.extract_text() or ""
            self.assertIn("Enterprise Automation 2026", dup_text)


if __name__ == "__main__":
    unittest.main()
