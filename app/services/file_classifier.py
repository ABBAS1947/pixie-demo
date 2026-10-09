# app/services/file_classifier.py
import json
import re
from typing import List, Dict, Any

from app.services.llm_registry import get_provider
from app.services.untrusted_document import DOCUMENT_GUARD, untrusted_document_text

class FileClassifier:
    """Classifies extracted text and extracts structured data"""

    @classmethod
    async def classify(cls, text: str) -> str:
        """Classify content as 'syllabus', 'notes', or 'other'"""
        messages = [
            {"role": "system", "content": f"{DOCUMENT_GUARD} You are a document classifier. Return only one word: syllabus, notes, or other."},
            {"role": "user", "content": untrusted_document_text(text, limit=3000)}
        ]

        try:
            provider = get_provider("classification")
            result = await provider.complete(messages, temperature=0.1)
            text_result = result["content"].strip().lower().rstrip(". ")
            if text_result in ['syllabus', 'notes', 'other']:
                return text_result
            return 'other'
        except Exception:
            return 'other'

    @classmethod
    async def extract_deadlines(cls, text: str) -> List[Dict[str, Any]]:
        """Extract deadlines from syllabus text"""
        messages = [
            {
                "role": "system",
                "content": (
                    f"{DOCUMENT_GUARD} "
                    "Extract deadlines from the syllabus. Reply ONLY with JSON: "
                    '{"deadlines":[{"title":string,"due_date":"YYYY-MM-DD or ISO 8601",'
                    '"kind":"assignment|exam|project"}]} '
                    'Return {"deadlines":[]} if none.'
                ),
            },
            {"role": "user", "content": untrusted_document_text(text, limit=5000)}
        ]

        try:
            provider = get_provider("extraction")
            result = await provider.complete(messages, json_mode=True, temperature=0.1)
            data = json.loads(result["content"])
            if isinstance(data, dict):
                return data.get("deadlines", [])
            if isinstance(data, list):
                return data  # tolerate a bare array
            return []
        except Exception:
            return []

    @classmethod
    async def generate_note(cls, text: str) -> Dict[str, str]:
        """Generate structured note from content"""
        messages = [
            {"role": "system", "content": f"{DOCUMENT_GUARD} Convert content to structured note. Return JSON with title and content fields."},
            {"role": "user", "content": untrusted_document_text(text, limit=5000)}
        ]

        try:
            provider = get_provider("extraction")
            result = await provider.complete(messages, json_mode=True, temperature=0.3)
            data = json.loads(result["content"])
            if isinstance(data, dict) and ("title" in data or "content" in data):
                return data
            return {'title': 'Untitled Note', 'content': text}
        except Exception:
            return {'title': 'Untitled Note', 'content': text}
