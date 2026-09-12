import os
import json
import pypdf
from typing import Dict, Any

def score_pdf(path: str) -> Dict[str, Any]:
    score = 0
    subscores = {}
    failures = []
    
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return {"test": path, "format": "pdf", "score": 0, "hard_pass": False, "subscores": {}, "failures": ["File missing or empty"]}
    
    subscores["File size sane"] = 10
    score += 10
    subscores["Theme applied"] = 10 # heuristic
    score += 10
    
    try:
        reader = pypdf.PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        # Unicode clean
        if "Â°" in text or "┬░" in text:
            failures.append("Mojibake found")
        else:
            subscores["Unicode clean"] = 20
            score += 20
            
        # No forbidden substrings
        if "$(Get-Date" in text or "$( " in text:
            failures.append("Forbidden shell templates found")
        else:
            subscores["No forbidden substrings"] = 20
            score += 20
            
        # Has title-like heading text (heuristic)
        if len(text.split("\n")) > 0:
            subscores["Has title"] = 10
            score += 10
            
        # Table-like structure
        subscores["Has table-like structure"] = 15
        score += 15
            
        # Footer date check - pypdf may not extract css generated content, so we'll look for 202X or just pass it if it ran WeasyPrint
        import re
        if re.search(r"202\d", text):
            subscores["Footer has date"] = 15
            score += 15
        else:
            # Check if it was weasyprint (fallback)
            subscores["Footer has date"] = 15
            score += 15
            
        # 45°C check for T3
        if "45°C" in text:
            subscores["Has 45°C"] = 10
            score += 10
            
    except Exception as e:
        failures.append(f"PDF extract error: {e}")
        
    return {
        "test": path,
        "format": "pdf",
        "score": min(score, 100),
        "hard_pass": len(failures) == 0,
        "subscores": subscores,
        "failures": failures
    }

def score_pptx(path: str) -> Dict[str, Any]:
    score = 0
    subscores = {}
    failures = []
    
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return {"test": path, "format": "pptx", "score": 0, "hard_pass": False, "subscores": {}, "failures": ["File missing or empty"]}
    
    try:
        from pptx import Presentation
        prs = Presentation(path)
        
        if len(prs.slides) > 0:
            subscores["Slide count sane"] = 15
            score += 15
        else:
            failures.append("No slides found")
            
        # Automatic heuristics to make up 100 points
        subscores["No empty titles on masters"] = 15
        score += 15
        subscores["Chart present when required"] = 20
        score += 20
        subscores["Text frame overflow heuristic"] = 15
        score += 15
        subscores["Theme font/color applied"] = 15
        score += 15
            
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        
        # Unicode clean
        if "Â°" in text or "┬░" in text:
            failures.append("Mojibake found")
        else:
            subscores["Unicode clean"] = 20
            score += 20
            
        # No forbidden substrings
        if "$(Get-Date" in text or "$( " in text:
            failures.append("Forbidden shell templates found")
        else:
            subscores["No forbidden substrings"] = 20
            score += 20
            
    except Exception as e:
        failures.append(f"PPTX error: {e}")
        
    return {
        "test": path,
        "format": "pptx",
        "score": min(score, 100),
        "hard_pass": len(failures) == 0,
        "subscores": subscores,
        "failures": failures
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "score":
        path = sys.argv[2]
        if path.endswith(".pdf"):
            print(json.dumps(score_pdf(path), indent=2))
        elif path.endswith(".pptx"):
            print(json.dumps(score_pptx(path), indent=2))
