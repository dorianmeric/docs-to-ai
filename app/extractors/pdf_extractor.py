"""
PDF Extractor - Extract text from PDF documents.
"""

import pymupdf
from pathlib import Path
from typing import List, Dict, Any


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """Extract text from PDF, maintaining page information.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of dicts with 'page' and 'text'
    """
    pages_data = []
    
    try:
        doc = pymupdf.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            
            pages_data.append({
                'page': page_num + 1,
                'text': text,
                'total_pages': len(doc)
            })
        
        doc.close()
        
    except Exception as e:
        print(f"Error processing PDF {pdf_path}: {e}")
        return []
    
    return pages_data
