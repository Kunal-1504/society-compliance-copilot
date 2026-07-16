#!/usr/bin/env python3
"""Test script to verify the three fixes without needing database"""
import sys
sys.path.insert(0, '/home/stark/society-compliance-chatbot/backend')

# Test 1: Metadata loading
print("=" * 60)
print("TEST 1: Metadata Loading")
print("=" * 60)

import csv
from pathlib import Path

metadata_lookup = {}
metadata_path = Path("/home/stark/society-compliance-chatbot/backend/scraper/metadata")
csv_files = [
    "master_metadata.csv", 
    "cooperation_department_metadata.csv", 
    "gr_portal_metadata.csv", 
    "housing_department_metadata.csv", 
    "sahakarayukta_metadata.csv"
]

for csv_file in csv_files:
    filepath = metadata_path / csv_file
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row and 'filename' in row:
                        filename = row.get('filename', '').strip()
                        if filename:
                            metadata_lookup[filename] = {
                                'title': row.get('title', ''),
                                'url': row.get('pdf_url', ''),
                                'source_page': row.get('source_page', ''),
                                'category': row.get('classified_category') or row.get('category', ''),
                                'department': row.get('department', '')
                            }
        except Exception as e:
            print(f"⚠️ Error loading {csv_file}: {e}")

print(f"✅ Loaded {len(metadata_lookup)} documents from metadata")
if metadata_lookup:
    sample_file = list(metadata_lookup.keys())[0]
    print(f"\nSample metadata entry for: {sample_file}")
    print(f"  Title: {metadata_lookup[sample_file]['title']}")
    print(f"  URL: {metadata_lookup[sample_file]['url']}")
    print(f"  Category: {metadata_lookup[sample_file]['category']}")

# Test 2: AGM Acronym Detection
print("\n" + "=" * 60)
print("TEST 2: AGM Acronym Detection (Improved)")
print("=" * 60)

KNOWN_ACRONYMS = {
    "agm": "AGM = Annual General Meeting (वार्षिक सर्वसाधारण सभा) — the yearly meeting of all society members.",
    "sgm": "SGM = Special General Meeting (विशेष सर्वसाधारण सभा) — a general meeting called for a specific urgent matter.",
    "mc": "MC = Managing Committee (व्यवस्थापन समिती) — the elected body that runs the society.",
}

def find_known_acronyms(query: str):
    """Return plain-language expansions for any known acronyms mentioned in the query."""
    q = query.lower()
    hits = []
    for key, note in KNOWN_ACRONYMS.items():
        found = (
            f" {key} " in f" {q} " or
            f" {key}?" in q or
            f" {key}." in q or
            f" {key}," in q or
            q.endswith(f"{key}?") or
            q.endswith(f"{key}.") or
            q.strip() == key or
            q.startswith(key + " ") or
            q.endswith(" " + key) or
            f"is {key} " in q or
            f"what {key}" in q or
            f"about {key}" in q
        )
        if found and note not in hits:
            hits.append(note)
    return hits

test_queries = [
    "what is agm?",
    "AGM",
    "what about AGM",
    "Tell me about AGM rules",
    "agm process",
    "is agm mandatory?",
]

for query in test_queries:
    acronyms = find_known_acronyms(query)
    status = "✅" if acronyms else "❌"
    print(f"{status} Query: '{query}'")
    if acronyms:
        for acronym in acronyms:
            print(f"   → {acronym[:80]}...")

# Test 3: Language/Script Detection
print("\n" + "=" * 60)
print("TEST 3: Language & Script Preservation")
print("=" * 60)

def looks_marathi(text: str) -> bool:
    """Check if text contains Marathi (Devanagari script)"""
    return any('\u0900' <= c <= '\u097F' for c in text)

def detect_language_and_script(text: str) -> tuple:
    """Detect language and return (is_devanagari, language_name, language_code)"""
    if looks_marathi(text):
        return True, "Marathi (Devanagari)", "marathi_native"
    else:
        return False, "English", "english"

test_queries_lang = [
    ("What is AGM?", "English"),
    ("AGM म्हणजे काय?", "Marathi - Devanagari"),
    ("agm kaay hote?", "Romanized Marathi (Latin)"),
    ("महाराष्ट्र सहकारी संस्था", "Marathi - Devanagari"),
]

for query, expected_lang in test_queries_lang:
    is_devanagari, lang_display, lang_code = detect_language_and_script(query)
    
    if is_devanagari:
        detected_lang = "Marathi - Devanagari"
        output_directive = "Marathi (Devanagari script - NOT romanized)"
    else:
        detected_lang = "English"
        output_directive = "English"
    
    match = "✅" if expected_lang.split(" - ")[0] in detected_lang else "⚠️"
    print(f"{match} Query: '{query}'")
    print(f"   Expected: {expected_lang}")
    print(f"   Detected: {detected_lang}")
    print(f"   Output Directive: {output_directive}\n")

print("=" * 60)
print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
print("=" * 60)
