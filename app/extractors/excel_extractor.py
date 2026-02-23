"""
Excel Extractor - Extract text from Excel files.
"""

from pathlib import Path
from typing import List, Dict, Any
import pandas as pd


def extract_text_from_excel(excel_path: Path) -> List[Dict[str, Any]]:
    """Extract text from Excel file.
    
    Args:
        excel_path: Path to the Excel file
        
    Returns:
        List of dicts with 'page' and 'text'
    """
    pages_data = []
    
    try:
        sheet_names = pd.read_excel(excel_path, sheet_name=None)
        
        for sheet_name, df in sheet_names.items():
            sheet_text = f"\n--- Sheet: {sheet_name} ---\n"
            
            if not df.empty:
                columns = list(df.columns)
                sheet_text += "Columns: " + ", ".join(str(col) for col in columns) + "\n\n"
                
                for row_num, (_, row) in enumerate(df.iterrows(), start=1):
                    row_text = "\t".join(str(val) for val in row.values)
                    sheet_text += f"Row {row_num}: {row_text}\n"
            else:
                sheet_text += "(Empty sheet)\n"
            
            pages_data.append({
                'page': len(pages_data) + 1,
                'text': sheet_text.strip(),
                'total_pages': len(sheet_names)
            })
        
    except Exception as e:
        print(f"Error processing Excel file {excel_path}: {e}")
        return []
    
    return pages_data
