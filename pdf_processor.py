import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Optional
import hashlib
import json
from config import CHUNK_SIZE, CHUNK_OVERLAP, PDF_CACHE_DIR, USE_FOLDER_AS_TOPIC, DEFAULT_TOPIC


class PDFProcessor:
    """Handles PDF text extraction and chunking."""
    
    def __init__(self):
        self.cache_dir = PDF_CACHE_DIR
    
    def extract_topic_from_path(self, pdf_path: Path, base_dir: Optional[Path] = None) -> str:
        """
        Extract topic from folder structure.
        
        Args:
            pdf_path: Path to the PDF file
            base_dir: Base directory for PDFs (to determine topic from relative path)
            
        Returns:
            Topic name (folder name or default)
        """
        if not USE_FOLDER_AS_TOPIC:
            return DEFAULT_TOPIC
        
        # Get parent folder name
        parent_folder = pdf_path.parent.name
        
        # If base_dir provided and PDF is directly in base_dir, use default topic
        if base_dir and pdf_path.parent == base_dir:
            return DEFAULT_TOPIC
        
        # If parent folder is empty or root-like, use default
        if not parent_folder or parent_folder in ['/', '\\', '.']:
            return DEFAULT_TOPIC
        
        return parent_folder
    
    def extract_text_from_pdf(self, pdf_path: str, base_dir: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Extract text from PDF, maintaining page information.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of dicts with 'page', 'text', and 'metadata'
        """
        pdf_path = Path(pdf_path)
        base_path = Path(base_dir) if base_dir else None
        
        # Extract topic from folder structure
        topic = self.extract_topic_from_path(pdf_path, base_path)
        
        # Check cache
        cache_file = self._get_cache_path(pdf_path)
        if cache_file.exists():
            cached_data = json.load(open(cache_file, 'r', encoding='utf-8'))
            # Update topic in cached data in case folder structure changed
            for page_data in cached_data:
                page_data['metadata']['topic'] = topic
            return cached_data
        
        pages_data = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                pages_data.append({
                    'page': page_num + 1,
                    'text': text,
                    'metadata': {
                        'filename': pdf_path.name,
                        'filepath': str(pdf_path),
                        'topic': topic,
                        'total_pages': len(doc)
                    }
                })
            
            doc.close()
            
            # Cache the result
            self._cache_extracted_text(pdf_path, pages_data)
            
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            return []
        
        return pages_data
    
    def chunk_text(self, pages_data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Split text into chunks with overlap.
        
        Args:
            pages_data: List of page data from extract_text_from_pdf
            
        Returns:
            List of chunks with metadata
        """
        chunks = []
        
        for page_data in pages_data:
            text = page_data['text']
            page_num = page_data['page']
            metadata = page_data['metadata']
            
            # Skip empty pages
            if not text.strip():
                continue
            
            # Split into chunks
            for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
                chunk_text = text[i:i + CHUNK_SIZE]
                
                # Skip very small chunks
                if len(chunk_text.strip()) < 50:
                    continue
                
                # Include topic in chunk ID to ensure uniqueness across topics
                chunk_id = hashlib.md5(
                    f"{metadata['topic']}-{metadata['filepath']}-{page_num}-{i}".encode()
                ).hexdigest()
                
                chunks.append({
                    'id': chunk_id,
                    'text': chunk_text,
                    'metadata': {
                        **metadata,
                        'page': page_num,
                        'chunk_start': i,
                        'chunk_end': i + len(chunk_text)
                    }
                })
        
        return chunks
    
    def process_pdf(self, pdf_path: str, base_dir: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Complete pipeline: extract text and chunk it.
        
        Args:
            pdf_path: Path to PDF file
            base_dir: Base directory for PDFs (to extract topic from folder structure)
            
        Returns:
            List of text chunks with metadata
        """
        pages_data = self.extract_text_from_pdf(pdf_path, base_dir)
        chunks = self.chunk_text(pages_data)
        return chunks
    
    def _get_cache_path(self, pdf_path: Path) -> Path:
        """Generate cache file path for a PDF."""
        pdf_hash = hashlib.md5(str(pdf_path).encode()).hexdigest()
        return self.cache_dir / f"{pdf_hash}.json"
    
    def _cache_extracted_text(self, pdf_path: Path, pages_data: List[Dict]):
        """Cache extracted text to avoid reprocessing."""
        cache_file = self._get_cache_path(pdf_path)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Test the processor
    processor = PDFProcessor()
    
    # Example usage
    test_pdf = "test.pdf"  # Replace with actual PDF path
    if Path(test_pdf).exists():
        chunks = processor.process_pdf(test_pdf)
        print(f"Extracted {len(chunks)} chunks from {test_pdf}")
        if chunks:
            print(f"\nFirst chunk preview:")
            print(chunks[0]['text'][:200])
    else:
        print(f"Test file {test_pdf} not found")
