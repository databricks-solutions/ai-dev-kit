# Multi-Format Document Input

## When to Use

Use these patterns when building agents that accept PDF, JPEG, or PNG documents as input — common for document extraction, classification, and analysis agents.

## Auto-Detect File Format

Detect format from base64 header bytes:

```python
import base64

FORMAT_SIGNATURES = {
    b"%PDF": ("application/pdf", "document"),
    b"\xff\xd8\xff": ("image/jpeg", "image_url"),
    b"\x89PNG": ("image/png", "image_url"),
}

def detect_media_type(data_b64: str) -> tuple[str, str]:
    raw = base64.b64decode(data_b64[:32])
    for sig, (media_type, block_type) in FORMAT_SIGNATURES.items():
        if raw.startswith(sig):
            return media_type, block_type
    raise ValueError(f"Unsupported format. First bytes: {raw[:8]}")
```

## Build Content Blocks

Each format requires a different content block structure:

```python
def build_content_block(data_b64: str) -> dict:
    media_type, block_type = detect_media_type(data_b64)

    if block_type == "document":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data_b64,
            }
        }
    else:
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{data_b64}"
            }
        }
```

## Skills-Based Agent Architecture

For agents handling multiple document types, store extraction "skills" as YAML in a UC Volume:

```
/Volumes/catalog/schema/skills/
  _classifier.yaml       # classification + validation prompt
  invoice_2024.yaml      # extraction prompt for invoices
  receipt_standard.yaml   # extraction prompt for receipts
```

### Two-Phase LLM Flow

1. **Phase 1 (Classify + Validate):** Short fixed prompt returns `{doc_type, is_valid, rejection_reasons}`
2. **Phase 2 (Extract):** Load skill YAML for `doc_type`, run extraction with skill-specific prompt

```python
import yaml
from pathlib import Path

def process_document(doc_b64: str, skills_dir: str) -> dict:
    classifier = yaml.safe_load(Path(skills_dir, "_classifier.yaml").read_text())
    classification = call_llm(classifier["prompt"], doc_b64)

    if not classification["is_valid"]:
        return {"status": "rejected", "reasons": classification["rejection_reasons"]}

    skill_file = Path(skills_dir, f"{classification['doc_type']}.yaml")
    if not skill_file.exists():
        return {"status": "error", "message": f"No skill for {classification['doc_type']}"}

    skill = yaml.safe_load(skill_file.read_text())
    extraction = call_llm(skill["prompt"], doc_b64)
    return {"status": "success", "data": extraction}
```

### Benefits

- Add document types by uploading YAML — no redeployment needed
- Business users can edit prompts directly
- Failed documents short-circuit (no wasted extraction tokens)
- Each skill is versioned independently

## Robust JSON Parsing from LLM Output

LLMs sometimes wrap JSON in markdown fences or add preamble text:

```python
import json

def parse_llm_json(raw_response: str) -> dict:
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)
```
