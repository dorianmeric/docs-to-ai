"""
HTML Extractor - Extract text from HTML files.
"""

from pathlib import Path
from typing import List, Dict, Any
from bs4 import BeautifulSoup


def extract_text_from_html(html_path: Path) -> List[Dict[str, Any]]:
    """Extract text from HTML file."""
    pages_data = []
    
    try:
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator='\n')
        
        lines = (line.strip() for line in text.splitlines())
        chunks = []
        current_chunk = []
        
        for line in lines:
            if line:
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
        print(f"Error processing HTML file {html_path}: {e}")
        return []
    
    return pages_data
