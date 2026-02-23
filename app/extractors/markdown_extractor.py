"""
Markdown Extractor - Extract text from Markdown files.
"""

import re
from pathlib import Path
from typing import List, Dict, Any


def extract_text_from_markdown(md_path: Path) -> List[Dict[str, Any]]:
    """Extract text from markdown file.
    
    Args:
        md_path: Path to the markdown file
        
    Returns:
        List of dicts with 'page' and 'text'
    """
    pages_data = []
    
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        text = re.sub(r'```[^`]*```', '', markdown_content, flags=re.DOTALL)
        text = re.sub(r'`[^`]*`', '', text)
        text = re.sub(r'^#+\s+(.*)$', r'\1', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        pages_data.append({
            'page': 1,
            'text': text.strip(),
            'total_pages': 1
        })
        
    except Exception as e:
        print(f"Error processing markdown file {md_path}: {e}")
        return []
    
    return pages_data
