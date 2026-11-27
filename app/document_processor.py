from pathlib import Path
from typing import List, Dict, Optional, Any
import hashlib
import json
import sys
import re

from .config import (
    CHUNK_SIZE, CHUNK_OVERLAP, DOC_CACHE_DIR, USE_FOLDER_AS_TOPIC, DEFAULT_TOPIC, 
    CHUNKING_STRATEGY, CHUNK_BY_TOKEN, TOKENIZER_MODEL, PRESERVE_HEADINGS, 
    MAX_HEADING_CHUNK_SIZE, MIN_CHUNK_SIZE,
    SEMANTIC_CHUNK_PERCENTILE, SEMANTIC_CHUNK_MIN_SIZE, SEMANTIC_CHUNK_MAX_SIZE,
    SEMANTIC_CHUNK_BUFFER_SIZE
)

from .errors import explain
from .extractors import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_markdown,
    extract_text_from_excel,
    extract_text_from_pptx,
    extract_text_from_html,
    extract_text_from_txt,
    extract_text_from_csv,
)

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


_ENCODINGS: Dict[str, Any] = {}
_ENCODING_FAILURES = 0
_ENCODING_MAX_FAILURES = 3
# Rough English/code ratio used when tiktoken data cannot be fetched (e.g. the
# container runs offline and the BPE files were not baked into the image).
CHARS_PER_TOKEN = 4


def _get_encoding():
    """Return the configured tiktoken encoding, or None when unavailable.

    tiktoken fetches its BPE data on first use, which can fail on an offline
    machine. Loading is retried a few times before the process gives up, so a
    transient failure does not silently change chunk sizing for its lifetime.
    """
    global _ENCODING_FAILURES
    if TOKENIZER_MODEL in _ENCODINGS:
        return _ENCODINGS[TOKENIZER_MODEL]
    if not TIKTOKEN_AVAILABLE or _ENCODING_FAILURES >= _ENCODING_MAX_FAILURES:
        return None
    try:
        _ENCODINGS[TOKENIZER_MODEL] = tiktoken.get_encoding(TOKENIZER_MODEL)
    except Exception as e:
        _ENCODING_FAILURES += 1
        if _ENCODING_FAILURES >= _ENCODING_MAX_FAILURES:
            print(
                f"WARNING: tokenizer '{TOKENIZER_MODEL}' could not be loaded after "
                f"{_ENCODING_FAILURES} attempts ({e}). Token counts are now estimated "
                f"at {CHARS_PER_TOKEN} characters per token; run "
                "'python -m app.download_models' (or mount TIKTOKEN_CACHE_DIR) to "
                "cache the tokenizer data.",
                file=sys.stderr
            )
        return None
    _ENCODING_FAILURES = 0
    return _ENCODINGS[TOKENIZER_MODEL]


def token_count(text: str) -> int:
    """Number of tokens in ``text`` (estimated when tiktoken is unavailable)."""
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is None:
        return max(1, len(text) // CHARS_PER_TOKEN)
    return len(encoding.encode(text, disallowed_special=()))


class DocumentProcessor:
    """Handles document text extraction and chunking for PDFs and Word documents."""
    
    def __init__(self):
        self.cache_dir = DOC_CACHE_DIR
        # Chunk sizes are measured in tokens (the 512-1024 token sweet spot)
        # when token chunking is enabled, and in characters otherwise.
        self.token_units = CHUNK_BY_TOKEN or CHUNKING_STRATEGY == 'by_token'

    def _measure(self, text: str) -> int:
        """Length of ``text`` in the configured unit (tokens or characters).

        The unit never changes with tokenizer availability: in token mode a
        missing tokenizer yields an estimate, so chunks stay the same size.
        """
        if self.token_units:
            return token_count(text)
        return len(text)
    
    def extract_topics_from_path(self, doc_path: Path, base_dir: Optional[Path] = None) -> List[str]:
        """
        Extract all topics from folder hierarchy.
        
        Args:
            doc_path: Path to the document file
            base_dir: Base directory for documents (to determine topic hierarchy)
            
        Returns:
            List of topic names from folder hierarchy
        """
        if not USE_FOLDER_AS_TOPIC:
            return [DEFAULT_TOPIC]
        
        # If no base directory, just use parent folder
        if not base_dir:
            parent_name = doc_path.parent.name
            if parent_name and parent_name not in ['/', '\\\\', '.']:
                return [parent_name]
            return [DEFAULT_TOPIC]
        
        base_path = Path(base_dir).resolve()
        doc_path_resolved = doc_path.resolve()
        
        # If document is directly in base directory
        if doc_path_resolved.parent == base_path:
            return [DEFAULT_TOPIC]
        
        # Get relative path from base to document's parent folder
        try:
            relative_path = doc_path_resolved.parent.relative_to(base_path)
        except ValueError:
            # Document is not under base directory
            return [doc_path.parent.name if doc_path.parent.name else DEFAULT_TOPIC]
        
        # Extract all folder names in the path as topics
        topics = [part for part in relative_path.parts if part and part not in ['.', '..']]
        
        return topics if topics else [DEFAULT_TOPIC]
    
    def extract_text_from_document(self, doc_path: str, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract text from document (PDF, Word, Markdown, or Excel), maintaining structure.
        
        Args:
            doc_path: Path to the document file
            base_dir: Base directory for documents (to extract topics from folder structure)
            
        Returns:
            List of dicts with 'page', 'text', and 'metadata'
        """
        doc_file = Path(doc_path)
        base_path = Path(base_dir) if base_dir else None

        # Extract topics from folder hierarchy
        topics = self.extract_topics_from_path(doc_file, base_path)

        # Get file metadata
        file_size = doc_file.stat().st_size
        last_modified = doc_file.stat().st_mtime

        # Check cache
        cache_file = self._get_cache_path(doc_file)
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as handle:
                    cached_data = json.load(handle)
                # Update topics in cached data in case folder structure changed
                for page_data in cached_data:
                    page_data['metadata']['topics'] = topics
                    page_data['metadata']['file_size'] = file_size
                    page_data['metadata']['last_modified'] = last_modified
                return cached_data
            except (json.JSONDecodeError, OSError, KeyError) as exc:
                # A damaged cache entry must not stop the scan: drop it and re-extract
                print(
                    f"Cached text for '{doc_file.name}' is unreadable ({type(exc).__name__}). "
                    "Fix: nothing to do, the file is being re-extracted and the cache rewritten.",
                    file=sys.stderr
                )
                cache_file.unlink(missing_ok=True)

        # Determine file type and extract text
        extension = doc_file.suffix.lower()

        if extension == '.pdf':
            pages_data = extract_text_from_pdf(doc_file)
        elif extension in ['.docx', '.doc']:
            pages_data = extract_text_from_docx(doc_file)
        elif extension == '.md':
            pages_data = extract_text_from_markdown(doc_file)
        elif extension in ['.xlsx', '.xls', '.xlsam', '.xlsb']:
            pages_data = extract_text_from_excel(doc_file)
        elif extension == '.pptx':
            pages_data = extract_text_from_pptx(doc_file)
        elif extension in ['.html', '.htm']:
            pages_data = extract_text_from_html(doc_file)
        elif extension == '.txt':
            pages_data = extract_text_from_txt(doc_file)
        elif extension == '.csv':
            pages_data = extract_text_from_csv(doc_file)
        else:
            print(f"Unsupported file type: {extension}", file=sys.stderr)
            return []


        print(f"\n⚠ File: {doc_file}, Found file_size = {file_size} bytes, last_modified = {last_modified} (after caching check)", file=sys.stderr)

        # Add metadata to each page
        result = []
        for page_data in pages_data:
            result.append({
                'page': page_data['page'],
                'text': page_data['text'],
                'metadata': {
                    'filename': doc_file.name,
                    'filepath': str(doc_file),
                    'topics': topics,
                    'filetype': extension,
                    'file_size': file_size,
                    'last_modified': last_modified,
                    'total_pages': page_data['total_pages']
                }
            })

        # Cache the result
        self._cache_extracted_text_safe(doc_file, result)
        
        return result
    
    def _create_chunk(self, text: str, metadata: Dict[str, Any], page_num: int, chunk_index: int) -> Dict[str, Any]:
        """Helper to create a chunk dictionary with a unique ID."""
        return {
            'id': self._chunk_id(metadata, page_num, chunk_index),
            'text': text,
            'metadata': {
                **metadata,
                'page': page_num,
                'chunk_index': chunk_index,
            }
        }

    @staticmethod
    def _chunk_id(metadata: Dict[str, Any], page_num: int, chunk_index: int) -> str:
        """Stable chunk ID derived from topic path, file, page and position."""
        topics_str = '-'.join(metadata.get('topics') or ['uncategorized'])
        return hashlib.md5(
            f"{topics_str}-{metadata['filepath']}-{page_num}-{chunk_index}".encode()
        ).hexdigest()

    def _renumber(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Give a page's chunks sequential indexes (and therefore stable IDs)."""
        for index, chunk in enumerate(chunks):
            metadata = chunk['metadata']
            metadata['chunk_index'] = index
            chunk['id'] = self._chunk_id(metadata, metadata['page'], index)
        return chunks

    def _chunk_with_fixed_size(self, text: str, metadata: Dict[str, Any], page_num: int) -> List[Dict[str, Any]]:
        """Split text into fixed-size chunks, measured in the configured unit."""
        if not self.token_units:
            return self._chunk_char_fixed(text, metadata, page_num)
        if _get_encoding() is None:
            return self._chunk_by_estimated_tokens(text, metadata, page_num)
        return self._chunk_by_token(text, metadata, page_num)

    def _chunk_by_estimated_tokens(self, text: str, metadata: Dict[str, Any],
                                   page_num: int) -> List[Dict[str, Any]]:
        """Token chunking without a tokenizer: slice at CHARS_PER_TOKEN chars/token."""
        return self._chunk_char_fixed(
            text, metadata, page_num,
            size=max(1, CHUNK_SIZE * CHARS_PER_TOKEN),
            overlap=max(0, CHUNK_OVERLAP * CHARS_PER_TOKEN),
        )

    def _chunk_char_fixed(self, text: str, metadata: Dict[str, Any], page_num: int,
                          size: Optional[int] = None,
                          overlap: Optional[int] = None) -> List[Dict[str, Any]]:
        """Split text into fixed-size character chunks with overlap."""
        chunks = []
        if not text.strip():
            return []

        size = CHUNK_SIZE if size is None else size
        overlap = CHUNK_OVERLAP if overlap is None else overlap
        step = max(1, size - overlap)

        for i in range(0, len(text), step):
            chunk_text = text[i:i + size]
            if self._measure(chunk_text) < MIN_CHUNK_SIZE:
                continue
            
            chunk = self._create_chunk(chunk_text, metadata, page_num, i)
            chunk['metadata']['chunk_start'] = i
            chunk['metadata']['chunk_end'] = i + len(chunk_text)
            chunks.append(chunk)
            
        return chunks

    def _chunk_by_paragraph(self, text: str, metadata: Dict[str, Any], page_num: int) -> List[Dict[str, Any]]:
        """Split text by paragraphs and group them into chunks."""
        chunks = []
        if not text.strip():
            return []

        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        current_parts: List[str] = []
        current_size = 0
        chunk_index = 0

        def flush():
            """Emit the paragraphs accumulated so far as one chunk."""
            nonlocal current_parts, current_size, chunk_index
            if not current_parts:
                return
            chunks.append(self._create_chunk('\n'.join(current_parts), metadata, page_num, chunk_index))
            chunk_index += 1
            current_parts = []
            current_size = 0

        for p in paragraphs:
            p_size = self._measure(p)

            # A paragraph larger than the target size is split on its own
            if p_size > CHUNK_SIZE:
                flush()
                sub_chunks = self._chunk_with_fixed_size(p, metadata, page_num)
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
                continue

            # Adding this paragraph would overflow the chunk: start a new one
            if current_parts and current_size + p_size > CHUNK_SIZE:
                flush()

            current_parts.append(p)
            current_size += p_size

        flush()

        return chunks

    def _chunk_by_token(self, text: str, metadata: Dict[str, Any], page_num: int) -> List[Dict[str, Any]]:
        """Split text into token-based chunks with overlap."""
        chunks = []
        if not text.strip():
            return []

        enc = _get_encoding()
        if enc is None:
            return self._chunk_by_estimated_tokens(text, metadata, page_num)
        
        tokens = enc.encode(text, disallowed_special=())
        step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)

        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i:i + CHUNK_SIZE]
            chunk_text = enc.decode(chunk_tokens)
            
            if token_count(chunk_text) < MIN_CHUNK_SIZE:
                continue
            
            chunk = self._create_chunk(chunk_text, metadata, page_num, i)
            chunk['metadata']['chunk_start'] = i
            chunk['metadata']['chunk_end'] = i + len(chunk_tokens)
            chunk['metadata']['is_token_based'] = True
            chunks.append(chunk)
        
        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences for semantic chunking.

        Uses a lightweight regex splitter so no extra NLP dependency is needed.
        Falls back to line splitting when no sentence punctuation is present.
        """
        # Split after ., !, ? (optionally followed by quotes/brackets) when
        # followed by whitespace. Keeps the punctuation with the sentence.
        parts = re.split(r'(?<=[.!?])["\')\]]*\s+', text)
        sentences = [s.strip() for s in parts if s and s.strip()]

        if len(sentences) <= 1:
            # No sentence boundaries found (e.g. tables, code) - fall back to lines
            sentences = [line.strip() for line in text.split('\n') if line.strip()]

        return sentences

    def _chunk_semantic(self, text: str, metadata: Dict[str, Any], page_num: int) -> List[Dict[str, Any]]:
        """Split text into semantically coherent chunks using embedding similarity.

        Consecutive sentences are embedded and the cosine distance between
        neighbouring windows is computed. Boundaries are placed where the
        distance exceeds the configured percentile threshold (i.e. the most
        dissimilar transitions), so each chunk stays on a single topic. Chunks
        are then clamped to the min/max size bounds.
        """
        chunks = []
        if not text.strip():
            return []

        sentences = self._split_sentences(text)
        if not sentences:
            return []

        # Semantic chunk bounds are always expressed in tokens (512-1024 is the
        # practical sweet spot before retrieval quality drops off)
        max_size = max(1, SEMANTIC_CHUNK_MAX_SIZE)
        min_size = max(0, SEMANTIC_CHUNK_MIN_SIZE)

        if len(sentences) == 1:
            # Single sentence: emit directly, or hard-split if it exceeds the max size
            if token_count(sentences[0]) <= max_size:
                chunk = self._create_chunk(sentences[0], metadata, page_num, 0)
                chunk['metadata']['is_semantic_chunk'] = True
                return [chunk]
            return self._chunk_with_fixed_size(text, metadata, page_num)

        try:
            import numpy as np
            from .embeddings import encode_passages

            embeddings = np.asarray(encode_passages(sentences))

            # Combine each sentence with its neighbours to smooth the signal
            buffer = max(0, SEMANTIC_CHUNK_BUFFER_SIZE)
            if buffer > 0:
                windows = []
                for i in range(len(embeddings)):
                    start = max(0, i - buffer)
                    end = min(len(embeddings), i + buffer + 1)
                    windows.append(embeddings[start:end].mean(axis=0))
                embeddings = np.asarray(windows)

            # Cosine distance between consecutive sentence windows (higher = more dissimilar)
            distances = 1.0 - np.sum(embeddings[:-1] * embeddings[1:], axis=1)

            # Split at the most dissimilar boundaries: those above the given
            # percentile of the distance distribution (e.g. 95 -> top 5%).
            threshold = float(np.percentile(distances, SEMANTIC_CHUNK_PERCENTILE))
            split_indices = {i + 1 for i, dist in enumerate(distances) if dist > threshold}
        except Exception as e:
            print(f"Semantic chunking unavailable ({e}); falling back to paragraph chunking", file=sys.stderr)
            return self._chunk_by_paragraph(text, metadata, page_num)

        # Group sentences into chunks, respecting the split boundaries and size bounds
        chunk_index = 0
        current: List[str] = []
        current_len = 0

        def flush():
            nonlocal current, current_len, chunk_index
            if not current:
                return
            chunk_text = ' '.join(current).strip()
            if chunk_text:
                chunk = self._create_chunk(chunk_text, metadata, page_num, chunk_index)
                chunk['metadata']['is_semantic_chunk'] = True
                chunks.append(chunk)
                chunk_index += 1
            current = []
            current_len = 0

        for i, sentence in enumerate(sentences):
            sentence_len = token_count(sentence)
            # Hard split if adding this sentence would exceed the max size
            if current and current_len + sentence_len > max_size:
                flush()
            current.append(sentence)
            current_len += sentence_len
            # Soft split at a detected semantic boundary once the min size is met
            if i + 1 in split_indices and current_len >= min_size:
                flush()

        flush()

        # Merge any trailing chunk that is too small into the previous one
        if len(chunks) > 1 and token_count(chunks[-1]['text']) < min_size:
            tail = chunks.pop()
            merged = chunks[-1]['text'] + ' ' + tail['text']
            chunks[-1]['text'] = merged

        return chunks

    def _extract_heading_structure(self, text: str) -> List[Dict[str, Any]]:
        """Extract heading structure from text (markdown-style or HTML)."""
        sections = []
        
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$|^(.+?)\n(=+|-+)$', re.MULTILINE)
        
        lines = text.split('\n')
        current_section = {'heading': '', 'content': [], 'level': 0}
        
        for line in lines:
            heading_match = heading_pattern.match(line)
            
            if heading_match:
                if current_section['content']:
                    sections.append(current_section)
                    current_section = {'heading': '', 'content': [], 'level': 0}
                
                if heading_match.group(1):
                    level = len(heading_match.group(1))
                    heading = heading_match.group(2)
                else:
                    heading = heading_match.group(3)
                    level = 1 if heading_match.group(4) == '=' else 2
                
                current_section = {'heading': heading.strip(), 'content': [], 'level': level}
            else:
                current_section['content'].append(line)
        
        if current_section['content']:
            sections.append(current_section)
        
        return sections

    def _chunk_by_heading(self, text: str, metadata: Dict[str, Any], page_num: int) -> List[Dict[str, Any]]:
        """Split text by headings/sections while preserving structure."""
        chunks = []
        if not text.strip():
            return []
        
        sections = self._extract_heading_structure(text)
        
        if not sections:
            return self._chunk_with_fixed_size(text, metadata, page_num)
        
        chunk_index = 0
        for section in sections:
            section_text = '\n'.join(section['content'])
            heading = section['heading']
            
            if not section_text.strip():
                continue
            
            if self._measure(section_text) <= MAX_HEADING_CHUNK_SIZE:
                chunk = self._create_chunk(section_text, metadata, page_num, chunk_index)
                chunk['metadata']['heading'] = heading
                chunk['metadata']['heading_level'] = section['level']
                chunk['metadata']['is_semantic_chunk'] = True
                chunks.append(chunk)
                chunk_index += 1
            else:
                sub_chunks = self._chunk_with_fixed_size(section_text, metadata, page_num)
                for sc in sub_chunks:
                    sc['metadata']['heading'] = heading
                    sc['metadata']['heading_level'] = section['level']
                    sc['metadata']['is_semantic_chunk'] = True
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
        
        return chunks

    def chunk_text(self, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Split text into chunks based on the configured strategy.
        
        Args:
            pages_data: List of page data from extract_text_from_document
            
        Returns:
            List of chunks with metadata
        """
        all_chunks = []
        
        use_token_chunking = CHUNK_BY_TOKEN or CHUNKING_STRATEGY == 'by_token'
        
        for page_data in pages_data:
            text = page_data['text']
            metadata = page_data['metadata']
            page_num = page_data['page']

            # Explicit strategies always win; PRESERVE_HEADINGS only decides how
            # the remaining (legacy) fixed-size path behaves.
            if CHUNKING_STRATEGY == 'semantic':
                chunks = self._chunk_semantic(text, metadata, page_num)
            elif CHUNKING_STRATEGY == 'by_paragraph':
                chunks = self._chunk_by_paragraph(text, metadata, page_num)
            elif CHUNKING_STRATEGY == 'by_token':
                chunks = self._chunk_by_token(text, metadata, page_num)
            elif CHUNKING_STRATEGY == 'semantic_heading':
                chunks = self._chunk_by_heading(text, metadata, page_num)
            elif CHUNKING_STRATEGY == 'fixed_size':
                chunks = self._chunk_with_fixed_size(text, metadata, page_num)
            elif PRESERVE_HEADINGS:
                chunks = self._chunk_by_heading(text, metadata, page_num)
            elif use_token_chunking:
                chunks = self._chunk_by_token(text, metadata, page_num)
            else:
                chunks = self._chunk_with_fixed_size(text, metadata, page_num)
            
            all_chunks.extend(self._renumber(chunks))
            
        return all_chunks
    
    def process_document(self, doc_path: str, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Complete pipeline: extract text and chunk it.
        
        Args:
            doc_path: Path to document file (PDF, Word, Markdown, or Excel)
            base_dir: Base directory for documents (to extract topics from folder structure)
            
        Returns:
            List of text chunks with metadata
        """
        pages_data = self.extract_text_from_document(doc_path, base_dir)
        chunks = self.chunk_text(pages_data)
        return chunks
    
    def clear_document_cache(self):
        """Clear all cached document extractions (deletes contents, keeps folder)."""
        import shutil
        if self.cache_dir.exists():
            # Delete all files and subdirectories inside the cache folder
            for item in self.cache_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            print("Document cache cleared (contents deleted, folder preserved)", file=sys.stderr)
    
    def _get_cache_path(self, doc_path: Path) -> Path:
        """Generate cache file path for a document."""
        doc_hash = hashlib.md5(str(doc_path).encode()).hexdigest()
        return self.cache_dir / f"{doc_hash}.json"

    def _cache_extracted_text_safe(self, doc_path: Path, pages_data: List[Dict]) -> None:
        """Cache extracted text, and tolerate an unwritable cache folder."""
        try:
            self._cache_extracted_text(doc_path, pages_data)
        except OSError as exc:
            print(
                f"Could not write the extracted-text cache for '{doc_path.name}'",
                file=sys.stderr
            )
            print(explain(exc, context="cache write"), file=sys.stderr)
    
    def _cache_extracted_text(self, doc_path: Path, pages_data: List[Dict]):
        """Cache extracted text to avoid reprocessing."""
        cache_file = self._get_cache_path(doc_path)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Test the processor
    processor = DocumentProcessor()
    
    # Example usage
    test_doc = "test.pdf"  # Replace with actual document path
    if Path(test_doc).exists():
        chunks = processor.process_document(test_doc)
        print(f"Extracted {len(chunks)} chunks from {test_doc}", file=sys.stderr)
        if chunks:
            print(f"\nFirst chunk preview:")
            print(f"Topics: {chunks[0]['metadata']['topics']}")
            print(chunks[0]['text'][:200])
    else:
        print(f"Test file {test_doc} not found")

