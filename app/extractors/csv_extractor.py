"""
CSV Extractor - Extract text from CSV files.
"""

from pathlib import Path
from typing import List, Dict, Any
import pandas as pd


def extract_text_from_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """Extract text from CSV file with proper table handling."""
    pages_data = []
    
    try:
        df = pd.read_csv(csv_path)
        
        if not df.empty:
            csv_text = f"Columns: {', '.join(str(col) for col in df.columns)}\n\n"
            
            for idx, row in df.iterrows():
                row_text = " | ".join(f"{col}: {row[col]}" for col in df.columns)
                csv_text += f"Row {idx + 1}: {row_text}\n"
            
            pages_data.append({
                'page': 1,
                'text': csv_text.strip(),
                'total_pages': 1
            })
        else:
            pages_data.append({
                'page': 1,
                'text': '(Empty CSV file)',
                'total_pages': 1
            })
            
    except Exception as e:
        print(f"Error processing CSV file {csv_path}: {e}")
        return []
    
    return pages_data
