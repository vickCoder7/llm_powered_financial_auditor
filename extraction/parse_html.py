# extraction/parse_html.py

import sys
import os

# Ensure current path is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import re
import json
from pathlib import Path
from bs4 import BeautifulSoup

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_sections_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract all text and search for section headers
    full_text = soup.get_text(separator="\n")

    # Look for common 10-K item headers
    pattern = re.compile(r'(Item\s+\d+[A-Z]?\.*)\s+([^\n]{3,100})', re.IGNORECASE)
    matches = list(pattern.finditer(full_text))

    sections = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        section_title = f"{match.group(1).strip()} {match.group(2).strip()}"
        section_text = full_text[start:end].strip()
        sections[section_title] = clean_text(section_text)

    return sections

def save_sections_to_json(sections, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sections, f, indent=2)

if __name__ == "__main__":
    html_path = Path("../data/raw_documents/apple_10k_2023.html")
    output_path = Path("../outputs/structured_data/apple_sections.json")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    sections = extract_sections_from_html(html_content)
    save_sections_to_json(sections, output_path)

    print(f"✅ Parsed {len(sections)} sections from HTML.")
