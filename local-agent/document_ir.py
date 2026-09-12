from pydantic import BaseModel, Field, validator
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
import re
import json

def sanitize_string(value: str) -> str:
    if not isinstance(value, str):
        return value
    # Strip/reject $(, Get-Date, ` shell patterns
    value = re.sub(r"\$\(.*\)", "", value)
    value = re.sub(r"`[^`]*`", "", value)
    value = value.replace("Get-Date", "")
    # Normalize degree: Â° / ┬░ repair if present; prefer proper °
    value = value.replace("Â°", "°").replace("┬░", "°")
    return value

class DocumentMeta(BaseModel):
    title: Optional[str] = "Report"
    subtitle: Optional[str] = ""
    author: Optional[str] = ""
    generated_at: Optional[str] = "AUTO"

    @validator("*", pre=True)
    def sanitize(cls, v):
        return sanitize_string(v)

class DocumentSection(BaseModel):
    type: str
    level: Optional[int] = 1
    text: Optional[str] = ""
    title: Optional[str] = ""
    body: Optional[str] = ""
    columns: Optional[List[str]] = []
    rows: Optional[List[List[str]]] = []
    items: Optional[Union[List[str], List[Dict[str, str]]]] = []

    @validator("*", pre=True)
    def sanitize(cls, v):
        if isinstance(v, str): return sanitize_string(v)
        if isinstance(v, list):
            return [sanitize_string(i) if isinstance(i, str) else i for i in v]
        return v

class DocumentContent(BaseModel):
    sections: List[DocumentSection] = []

class Slide(BaseModel):
    master: str = "content"
    title: Optional[str] = ""
    subtitle: Optional[str] = ""
    author: Optional[str] = ""
    items: Optional[List[str]] = []
    chart_type: Optional[str] = ""
    chart_data: Optional[Dict[str, Any]] = {}
    insight: Optional[str] = ""
    stats: Optional[List[Dict[str, str]]] = []
    bullets: Optional[List[str]] = []
    body: Optional[str] = ""
    content: Optional[str] = ""

    @validator("*", pre=True)
    def sanitize(cls, v):
        if isinstance(v, str): return sanitize_string(v)
        if isinstance(v, list):
            return [sanitize_string(i) if isinstance(i, str) else i for i in v]
        return v

class DesignIR(BaseModel):
    format: str = "pdf"
    theme: str = "corporate_blue"
    page: str = "A4"
    meta: DocumentMeta = Field(default_factory=DocumentMeta)
    document: Optional[DocumentContent] = Field(default_factory=DocumentContent)
    slides: Optional[List[Slide]] = []

def normalize_ir(raw_json: Union[str, dict]) -> DesignIR:
    if isinstance(raw_json, str):
        try:
            data = json.loads(raw_json)
        except:
            # Try to compile markdown to IR best-effort if it fails JSON parse
            data = {"format": "pdf", "meta": {"title": "Generated Report"}, "document": {"sections": [{"type": "prose", "body": raw_json}]}}
    else:
        data = raw_json

    # legacy fallback for slides type
    if "slides" in data and isinstance(data["slides"], list):
        for s in data["slides"]:
            if "type" in s and "master" not in s:
                s["master"] = s["type"]

    ir = DesignIR(**data)
    ir.meta.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return ir
