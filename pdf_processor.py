import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Optional
import hashlib
import json
from config import CHUNK_SIZE, CHUNK_OVERLAP, PDF_CACHE_DIR, USE_FOLDER_AS_TOPIC, DEFAULT_TOPIC


class PDFProcessor:
    """Handles PDF text extraction and chunking with full folder hierarchy topics."""
    
    def __init__(self):
        self.cache_dir = PDF_CACHE_DIR
    
    def extract_topic_from_path(self, pdf_path: Path, base_dir: Optional[Path] = None) -> Dict[str, any]:
        """
        Extract topic hierarchy from folder structure.
        
        Args:
            pdf_path: Path to the PDF file
            base_dir: Base directory for PDFs (to determine relative path)
            
        Returns:
            Dict with 'topics' (list) and 'topic_path' (joined string)
        """
        if not USE_FOLDER_AS_TOPIC:
            return {"topics": [DEFAULT_TOPIC], "topic_path": DEFAULT_TOPIC}
        
        if not base_dir:
            base_dir = pdf_path.parent.parent
        
        try:
            rel_path = pdf_path.parent.relative_to(base_dir)
            parts = [p for p in rel_path.parts if p]
        except ValueError:
            # PDF not under base_dir
            parts = [pdf_path.parent.name]
        
        if not parts:
            parts = [DEFAULT_TOPIC]
        
        topic_path = " > ".join(parts)
        return {"topics": parts, "topic_path": topic_path}
    
    def extract_text_from_pdf(self, pdf_path: str, base_dir: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Extract text from PDF, maintaining page information.
        """
        pdf_path = Path(pdf_path)
        base_path = Path(base_dir) if base_dir else None
        
        topic_info = self.extract_topic_from_path(pdf_path, base_path)
        topics = topic_info["topics"]
        topic_path = topic_info["topic_path"]
        
        cache_file = self._get_cache_path(pdf_path)
        if cache_file.exists():
            cached_data = json.load(open(cache_file, 'r', encoding='utf-8'))
            for page_data in cached_data:
                page_data['metadata']['topics'] = topics
                page_data['metadata']['topic_path'] = topic_path
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
                        'topics': topics,
                        'topic_path': topic_path,
                        'total_pages': len(doc)
                    }
                })
            doc.close()
            self._cache_extracted_text(pdf_path, pages_data)
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
            return []
        
        return pages_data
    
    def chunk_text(self, pages_data: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """Split text into chunks with overlap, preserving metadata."""
        chunks = []
        for page_data in pages_data:
            text = page_data['text']
            page_num = page_data['page']
            metadata = page_data['metadata']
            if not text.strip():
                continue
            
            for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
                chunk_text = text[i:i + CHUNK_SIZE]
                if len(chunk_text.strip()) < 50:
                    continue
                
                # Unique chunk ID
                chunk_id = hashlib.md5(
                    f"{metadata['topic_path']}-{metadata['filepath']}-{page_num}-{i}".encode()
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
        """Complete pipeline: extract text and chunk it."""
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
