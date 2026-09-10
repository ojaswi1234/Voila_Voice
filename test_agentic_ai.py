import sys, os, json
sys.path.append('local-agent')
import document_tools, pptx
from pptx.util import Inches, Pt

# ── Test 1: Card quality check ─────────────────────────────────────────────
print("=== Test 1: Card roundness + shadow (all new layouts) ===")
SLIDES_CARD = [
    {"type": "title_slide", "title": "Agentic AI & Vectorless RAG", "subtitle": "A Deep Technical Overview", "author": "Voila AI"},
    {"type": "agenda", "title": "Agenda", "items": ["What is Agentic AI?", "Vectorless RAG explained", "Architecture comparison", "Performance benchmarks", "Use cases", "Roadmap"]},
    {"type": "metrics", "title": "Performance at a Glance", "metrics": [
        {"value": "94.7%", "label": "Accuracy", "sublabel": "vs 87% traditional RAG"},
        {"value": "3.2x", "label": "Faster retrieval"},
        {"value": "0 vectors", "label": "Storage overhead"},
        {"value": "12ms", "label": "P95 latency"},
    ]},
    {"type": "comparison", "title": "Vectorless vs Traditional RAG",
     "left_title": "Traditional RAG",
     "right_title": "Vectorless RAG",
     "content_left": "- Requires embedding model\n- Vector DB (Pinecone/Weaviate)\n- High storage cost\n- Complex index refresh\n- Embedding drift over time",
     "content_right": "- Direct semantic graph traversal\n- No separate vector store\n- Near-zero storage overhead\n- Real-time updates\n- No drift — always fresh"},
    {"type": "timeline", "title": "Research Timeline", "steps": [
        {"label": "2020", "description": "RAG paper (Lewis et al.)"},
        {"label": "2022", "description": "Vector DB explosion"},
        {"label": "2023", "description": "Agentic frameworks"},
        {"label": "2024", "description": "Vectorless approaches"},
        {"label": "2025+", "description": "Production at scale"},
    ]},
    {"type": "quote", "content": "The agent doesn't just retrieve — it reasons about what to retrieve, when, and how to compose the answer.", "author": "Yann LeCun (paraphrased)"},
    {"type": "content", "title": "How Vectorless RAG Works", "content": "- Text chunks stored as plain BM25/TF-IDF indices\n- Agent dynamically rewrites queries for multi-hop reasoning\n- Graph-based context window management replaces similarity search\n- No embedding model required at inference time\n- Works on any structured/unstructured corpus"},
    {"type": "section", "content": "Live Demo"},
    {"type": "title_slide", "title": "Q & A", "subtitle": "github.com/voila-ai/rag"},
]

result = document_tools.create_ppt({
    "path": "test_agentic_ai_cards.pptx",
    "title": "Agentic AI & Vectorless RAG",
    "slides": SLIDES_CARD,
    "theme": "illustrated_light",
    "auto_images": False
})
print(result)

# Verify card shapes
prs = pptx.Presentation("test_agentic_ai_cards.pptx")
print(f"Slide count: {len(prs.slides)}")
for i, slide in enumerate(prs.slides):
    print(f"  Slide {i+1}: {len(slide.shapes)} shapes")

# ── Test 2: Smart Image Search + Injection ─────────────────────────────────
print("\n=== Test 2: Smart Openverse image search on 'Agentic AI & Vectorless RAG' ===")
import os, shutil

# Clear cache
cache_dir = os.path.join('local-agent', 'image_cache')
if os.path.exists(cache_dir):
    shutil.rmtree(cache_dir)
os.makedirs(cache_dir, exist_ok=True)

SLIDES_IMG = [
    {"type": "title_slide", "title": "Agentic AI & Vectorless RAG", "subtitle": "Visual Overview", "author": "Voila AI"},
    {"type": "image", "title": "Neural Network Architecture", "content": "neural network deep learning architecture"},
    {"type": "image", "title": "Knowledge Graph", "content": "knowledge graph data visualization"},
    {"type": "image", "title": "AI Agent System", "content": "artificial intelligence robot automation"},
    {"type": "content", "title": "Summary", "content": "- Agentic AI enables multi-step reasoning\n- Vectorless RAG eliminates embedding bottlenecks\n- Production-ready with existing infrastructure"},
]

result2 = document_tools.create_ppt({
    "path": "test_agentic_ai_images.pptx",
    "title": "Agentic AI & Vectorless RAG — Visual",
    "slides": SLIDES_IMG,
    "theme": "ocean_depth",
    "auto_images": True
})
print(result2)

prs2 = pptx.Presentation("test_agentic_ai_images.pptx")
print(f"Slide count: {len(prs2.slides)}")
for i, slide in enumerate(prs2.slides):
    shape_types = [s.shape_type for s in slide.shapes]
    has_picture = 13 in shape_types  # 13 = PICTURE
    print(f"  Slide {i+1}: {len(slide.shapes)} shapes | Has image: {has_picture}")

print("\n=== Cache cleared after creation ===")
cache_files = os.listdir(cache_dir) if os.path.exists(cache_dir) else []
print(f"Cache files remaining: {len(cache_files)}")
