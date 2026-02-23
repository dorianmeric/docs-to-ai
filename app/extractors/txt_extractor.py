"""
TXT Extractor - Extract text from plain text files.
"""

from pathlib import Path
from typing import List, Dict, Any


def extract_text_from_txt(txt_path: Path) -> List[Dict[str, Any]]:
    """Extract text from plain text file."""
    pages_data = []
    
    try:
        with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        lines = content.splitlines()
        chunks = []
        current_chunk = []
        
        for line in lines:
            current_chunk.append(line)
            if len('\n'.join(current_chunk)) > 2000:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        for i, chunk in enumerate(chunks, start=1):
            pages_data.append({
                'page': i,
                'text': chunk,
                'total_pages': len(chunks)
            })
        
        if not pages_data:
            pages_data.append({
                'page': 1,
                'text': '',
                'total_pages': 1
            })
            
    except Exception as e:
        print(f"Error processing text file {txt_path}: {e}")
        return []
    
    return pages_data
