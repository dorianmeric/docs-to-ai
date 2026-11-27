import chromadb
from chromadb.config import Settings
from chromadb.types import Metadata
from sentence_transformers import CrossEncoder
from typing import List, Dict, Optional, Any, Sequence
import json
import re
from app.config import (
    CHROMADB_DIR, 
    CHROMA_COLLECTION_NAME, 
    CHROMA_SPACE,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    DEFAULT_SEARCH_RESULTS,
    USE_RERANKER,
    RERANKER_MODEL,
    RERANKER_TOP_N,
    USE_BM25,
    BM25_WEIGHT,
    BM25_K1,
    BM25_B,
    RRF_K,
    HNSW_EF_SEARCH,
    HNSW_EF_CONSTRUCTION,
)
from app.embeddings import (
    get_embedding_model,
    get_embedding_dimension,
    encode_passages,
    encode_one_query,
)
from app.bm25_index import BM25Index
import sys


class VectorStore:
    """Manages vector database operations using chromadb.

    Implemented as a Singleton to ensure only one instance exists across the application.
    This prevents multiple instances from creating separate database connections.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern: always return the same instance."""
        if cls._instance is None:
            cls._instance = super(VectorStore, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the vector store (only runs once due to singleton pattern)."""
        # Only initialize once
        if VectorStore._initialized:
            return

        CHROMADB_DIR.mkdir(exist_ok=True, parents=True) # create the folder if it doesn't exist yet

        # Initialize chromadb client with persistence
        self.client = chromadb.PersistentClient(
            path=str(CHROMADB_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Initialize embedding model (shared process-wide instance)
        # print(f"Loading embedding model: {EMBEDDING_MODEL}", file=sys.stderr)
        self.embedding_model = get_embedding_model()
        
        # Initialize re-ranker model if enabled
        self.cross_encoder = None
        if USE_RERANKER:
            print(f"Loading re-ranker model: {RERANKER_MODEL}", file=sys.stderr)
            self.cross_encoder = CrossEncoder(RERANKER_MODEL)
            print("Re-ranker is active.", file=sys.stderr)

        # The collection's dimension decides compatibility, so trust the model over
        # a stale EMBEDDING_DIMENSION (e.g. left over from all-MiniLM-L6-v2)
        self.embedding_dimension = self._resolve_embedding_dimension()

        # Sparse (BM25) side of the hybrid retriever, built lazily from the collection
        self.bm25: Optional[BM25Index] = BM25Index(k1=BM25_K1, b=BM25_B) if USE_BM25 else None
        self._bm25_ready = False
        # Bumped on every write so a concurrent rebuild cannot mark itself fresh
        self._bm25_generation = 0

        # Get or create collection (with cosine space + HNSW tuning)
        self.collection = self._ensure_collection()

        if self.bm25 is not None:
            print("Hybrid search is active (BM25 + dense, fused with RRF)", file=sys.stderr)

        print(f"Vector store initialized. Documents chunks in collection: {self.collection.count()}", file=sys.stderr)

        print(
            f"Search pipeline: {'dense + BM25/RRF' if self.bm25 is not None else 'dense'}"
            f"{', cross-encoder re-ranking' if self.cross_encoder else ''}",
            file=sys.stderr
        )

        # Mark as initialized
        VectorStore._initialized = True

    def _resolve_embedding_dimension(self) -> int:
        """Return the model's real embedding size, warning if the env var differs."""
        actual = get_embedding_dimension()
        if actual is None:
            return EMBEDDING_DIMENSION
        if actual != EMBEDDING_DIMENSION:
            print(
                f"[VectorStore] EMBEDDING_DIMENSION={EMBEDDING_DIMENSION} does not match "
                f"{EMBEDDING_MODEL} ({actual}-dim); using {actual}. "
                "Update EMBEDDING_DIMENSION to silence this warning.",
                file=sys.stderr
            )
        return actual

    def _hnsw_configuration(self) -> Dict[str, Any]:
        """Collection configuration: cosine space and a wide HNSW candidate list."""
        return {
            "hnsw": {
                "space": CHROMA_SPACE,
                "ef_search": HNSW_EF_SEARCH,
                "ef_construction": HNSW_EF_CONSTRUCTION,
            }
        }

    def _collection_metadata(self) -> Dict[str, Any]:
        """Metadata recording which model/dimension built this collection.

        ChromaDB cannot change a collection's dimension or distance space in
        place, so recording the model lets us detect a stale index on startup
        instead of failing later with an opaque dimension error.
        """
        return {
            "description": "Document chunks with hierarchical topics",
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimension": self.embedding_dimension,
        }

    def _ensure_collection(self):
        """Open the collection, recreating it when it was built incompatibly."""
        collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            configuration=self._hnsw_configuration(),
            metadata=self._collection_metadata(),
        )

        mismatch = self._describe_mismatch(collection)
        if mismatch:
            print(
                f"[VectorStore] {mismatch}. Recreating collection '{CHROMA_COLLECTION_NAME}' "
                f"from scratch - re-scan your documents to rebuild the index.",
                file=sys.stderr
            )
            recreated = True
            try:
                self.client.delete_collection(CHROMA_COLLECTION_NAME)
            except Exception as e:
                recreated = False
                print(
                    f"[VectorStore] Warning: could not delete collection: {e}. Keeping it as-is; "
                    f"delete {CHROMADB_DIR} manually and re-scan to rebuild the index.",
                    file=sys.stderr
                )
            if recreated:
                collection = self.client.create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    configuration=self._hnsw_configuration(),
                    metadata=self._collection_metadata(),
                )
        else:
            self._apply_hnsw_tuning(collection)

        return collection

    def _describe_mismatch(self, collection) -> Optional[str]:
        """Return a human-readable reason when the stored index can't be reused."""
        metadata = dict(collection.metadata or {})
        stored_model = metadata.get('embedding_model')
        stored_dim = metadata.get('embedding_dimension')

        hnsw_config = (collection.configuration_json or {}).get('hnsw') or {}
        space = hnsw_config.get('space') or metadata.get('hnsw:space')

        if space and space != CHROMA_SPACE:
            return f"existing index uses HNSW space '{space}' instead of '{CHROMA_SPACE}'"
        if stored_model and stored_model != EMBEDDING_MODEL:
            return f"existing index was built with '{stored_model}' instead of '{EMBEDDING_MODEL}'"
        if stored_dim is None or int(stored_dim) != self.embedding_dimension:
            return (
                f"existing index dimension ({stored_dim or 'unknown'}) does not match "
                f"{EMBEDDING_MODEL} ({self.embedding_dimension}-dim)"
            )
        return None

    def _apply_hnsw_tuning(self, collection) -> None:
        """Raise ef_search on an existing collection when it is below target."""
        hnsw_config = (collection.configuration_json or {}).get('hnsw') or {}
        if hnsw_config.get('ef_search') == HNSW_EF_SEARCH:
            return
        try:
            collection.modify(configuration={"hnsw": {"ef_search": HNSW_EF_SEARCH}})
            print(f"[VectorStore] Set HNSW ef_search={HNSW_EF_SEARCH}", file=sys.stderr)
        except Exception as e:
            print(f"[VectorStore] Warning: could not update HNSW ef_search: {e}", file=sys.stderr)
    
    def add_documents(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Add document chunks to the vector store.
        
        Args:
            chunks: List of chunks from DocumentProcessor
            
        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0
        
        # Extract data
        ids = [chunk['id'] for chunk in chunks]
        texts = [chunk['text'] for chunk in chunks]
        
        # Convert topics list to JSON string for chromadb compatibility
        metadatas = []
        for chunk in chunks:
            metadata = chunk['metadata'].copy()
            # Convert topics list to JSON string
            if 'topics' in metadata and isinstance(metadata['topics'], list):
                metadata['topics_json'] = json.dumps(metadata['topics'])
                # Also store first topic for simple filtering
                metadata['primary_topic'] = metadata['topics'][0] if metadata['topics'] else 'uncategorized'
                del metadata['topics']  # Remove the list
            metadatas.append(metadata)
        
        # Generate embeddings
        print(f"Generating embeddings for {len(texts)} chunks...", file=sys.stderr)
        embeddings = encode_passages(texts, show_progress_bar=True)
        
        # Add to collection (using upsert to prevent duplicates)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )

        # Keep the sparse index in sync: append when it is already built (cheap),
        # otherwise let the next search rebuild it from the collection
        if self.bm25 is not None:
            if self._bm25_ready:
                self.bm25.add(ids, texts)
            self._bm25_generation += 1
        
        print(f"Added {len(chunks)} chunks to vector store", file=sys.stderr)
        return len(chunks)

    def _invalidate_bm25(self) -> None:
        """Mark the sparse index stale so the next search rebuilds it."""
        self._bm25_ready = False
        self._bm25_generation += 1

    def _ensure_bm25(self) -> None:
        """Build the BM25 index lazily from the chunks stored in the collection."""
        if self.bm25 is None or self._bm25_ready:
            return
        # Snapshot the generation first: if a write lands while we are reading the
        # collection, the index we build is already stale and must not be marked
        # ready (the next search would then miss the new chunks).
        generation = self._bm25_generation
        try:
            data = self.collection.get(include=['documents'])
        except Exception as e:
            print(f"[VectorStore] Could not build BM25 index: {e}", file=sys.stderr)
            return

        ids = data.get('ids') or []
        documents = data.get('documents') or []
        self.bm25.build(ids, [doc or '' for doc in documents])
        if generation == self._bm25_generation:
            self._bm25_ready = True
        if ids:
            print(f"[VectorStore] BM25 index built over {len(ids)} chunks", file=sys.stderr)

    def _dense_search(self, query: str, n_results: int) -> List[Dict]:
        """Vector search over the ChromaDB collection (cosine distance)."""
        if n_results <= 0 or self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_embeddings=[encode_one_query(query)],
            n_results=n_results
        )

        formatted_results: List[Dict] = []
        ids = results.get('ids') or []
        if not ids or not ids[0]:
            return formatted_results

        distances = results.get('distances')
        documents = results.get('documents') or [[]]
        metadatas = results.get('metadatas') or [[]]

        for i, chunk_id in enumerate(ids[0]):
            metadata = self._deserialize_metadata(metadatas[0][i]) if metadatas[0] else {}
            formatted_results.append({
                'id': chunk_id,
                'text': documents[0][i] if documents[0] else '',
                'metadata': metadata,
                'distance': distances[0][i] if distances and distances[0] else None,
            })

        return formatted_results

    def _fetch_chunks(self, chunk_ids: Sequence[str]) -> Dict[str, Dict]:
        """Fetch text/metadata for chunks that only the sparse side retrieved."""
        fetched: Dict[str, Dict] = {}
        if not chunk_ids:
            return fetched
        try:
            data = self.collection.get(
                ids=list(chunk_ids), include=['documents', 'metadatas']
            )
        except Exception as e:
            print(f"[VectorStore] Could not fetch BM25-only candidates: {e}", file=sys.stderr)
            return fetched

        ids = data.get('ids') or []
        documents = data.get('documents') or []
        metadatas = data.get('metadatas') or []
        for i, chunk_id in enumerate(ids):
            fetched[chunk_id] = {
                'id': chunk_id,
                'text': documents[i] if documents else '',
                'metadata': self._deserialize_metadata(metadatas[i]) if metadatas else {},
                # Unavailable for sparse-only hits; relevance is reported by the re-ranker
                'distance': None,
            }
        return fetched

    def _fuse_rrf(self, dense_results: List[Dict], bm25_hits: Sequence,
                  pool_size: int) -> List[Dict]:
        """Fuse dense and BM25 rankings with Reciprocal Rank Fusion.

        RRF scores each document as ``sum(weight / (k + rank))`` over the ranked
        lists it appears in. It needs no score normalisation, which is why it is
        the standard way to combine a cosine ranking with a BM25 ranking.
        ``BM25_WEIGHT`` is the share of the sparse list (0.5 = equal weight).
        """
        dense_weight = 1.0 - min(max(BM25_WEIGHT, 0.0), 1.0)
        sparse_weight = min(max(BM25_WEIGHT, 0.0), 1.0)
        k = max(1, RRF_K)

        by_id: Dict[str, Dict] = {result['id']: result for result in dense_results}
        scores: Dict[str, float] = {}

        for rank, result in enumerate(dense_results, start=1):
            scores[result['id']] = dense_weight / (k + rank)

        sparse_only: List[str] = []
        for rank, chunk_id in enumerate(bm25_hits, start=1):
            contribution = sparse_weight / (k + rank)
            if chunk_id in scores:
                scores[chunk_id] += contribution
            else:
                scores[chunk_id] = contribution
                sparse_only.append(chunk_id)

        by_id.update(self._fetch_chunks(sparse_only))

        fused: List[Dict] = []
        for chunk_id in sorted(scores, key=lambda cid: scores[cid], reverse=True)[:pool_size]:
            result = by_id.get(chunk_id)
            if result is None:
                continue  # deleted between the query and the fusion step
            entry = dict(result)
            entry['rrf_score'] = scores[chunk_id]
            fused.append(entry)

        return fused
    
    def _deserialize_metadata(self, metadata: Metadata | Dict[str, Any]) -> Dict[str, Any]:
        """Convert topics_json back to topics list."""
        # Convert to mutable dict
        result: Dict[str, Any] = dict(metadata)

        if 'topics_json' in result:
            try:
                result['topics'] = json.loads(str(result['topics_json']))
            except:
                result['topics'] = [result.get('primary_topic', 'uncategorized')]
        elif 'topics' not in result:
            # Handle old format or missing topics
            result['topics'] = [result.get('primary_topic', result.get('topic', 'uncategorized'))]
        return result
    
    def search(
        self, 
        query: str, 
        n_results: int = DEFAULT_SEARCH_RESULTS,
        phrase_search: bool = False,
        date_from: Optional[float] = None,
        date_to: Optional[float] = None,
        regex_pattern: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for relevant document chunks, with optional re-ranking.
        
        Args:
            query: Search query
            n_results: Number of results to return
            phrase_search: If True, treat query as exact phrase (quote handling)
            date_from: Filter results by minimum last_modified timestamp
            date_to: Filter results by maximum last_modified timestamp
            regex_pattern: Filter results by regex pattern in text
            
        Returns:
            List of search results with text, metadata, and relevance scores
        """
        # Wide candidate pool so the re-ranker (and RRF fusion) have room to work
        search_n_results = max(RERANKER_TOP_N if self.cross_encoder else n_results * 3, n_results)

        dense_results = self._dense_search(query, search_n_results)
        formatted_results = dense_results

        if self.bm25 is not None:
            self._ensure_bm25()
            bm25_hits = [chunk_id for chunk_id, _score in self.bm25.search(query, search_n_results)]
            if bm25_hits:
                formatted_results = self._fuse_rrf(dense_results, bm25_hits, search_n_results)
        
        if phrase_search:
            phrase_query = query.strip('"').lower()
            filtered = []
            for r in formatted_results:
                if phrase_query in r['text'].lower():
                    filtered.append(r)
            formatted_results = filtered
        
        if date_from is not None or date_to is not None:
            filtered = []
            for r in formatted_results:
                last_mod = r['metadata'].get('last_modified', 0)
                if date_from is not None and last_mod < date_from:
                    continue
                if date_to is not None and last_mod > date_to:
                    continue
                filtered.append(r)
            formatted_results = filtered
        
        if regex_pattern:
            try:
                compiled_regex = re.compile(regex_pattern, re.IGNORECASE)
                filtered = []
                for r in formatted_results:
                    if compiled_regex.search(r['text']):
                        filtered.append(r)
                formatted_results = filtered
            except re.error:
                pass
        
        if self.cross_encoder and formatted_results:
            print(f"Re-ranking top {len(formatted_results)} results...", file=sys.stderr)
            
            pairs = [[query, result['text']] for result in formatted_results]
            
            scores = self.cross_encoder.predict(pairs, show_progress_bar=False)
            
            for result, score in zip(formatted_results, scores):
                result['relevance_score'] = float(score)
                
            formatted_results.sort(key=lambda x: x['relevance_score'], reverse=True)

        return formatted_results[:n_results]
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """
        Retrieve a specific document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document dict or None if not found
        """
        result = self.collection.get(ids=[doc_id])

        if result['ids'] and result['metadatas'] and result['documents']:
            metadata = self._deserialize_metadata(result['metadatas'][0])
            return {
                'id': result['ids'][0],
                'text': result['documents'][0],
                'metadata': metadata
            }
        
        return None
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """
        Get list of all unique documents in the store with their topics.
        
        Returns:
            List of dicts with 'filename', 'topics', 'filepath', and 'filetype'
        """
        # Get all documents
        try:
            all_docs = self.collection.get()
        except Exception as e: # if the collection is not found
            return []
        
        # Extract unique documents (by filepath)
        documents = {}
        if all_docs['metadatas']:
            for metadata in all_docs['metadatas']:
                filepath = metadata.get('filepath', '')
                if filepath and filepath not in documents:
                    # Deserialize topics
                    metadata = self._deserialize_metadata(metadata)
                    topics = metadata.get('topics', ['uncategorized'])
                    if isinstance(topics, str):
                        topics = [topics]
                    documents[filepath] = {
                        'filename': metadata.get('filename', 'Unknown'),
                        'topics': topics,
                        'filepath': filepath,
                        'filetype': metadata.get('filetype', '.pdf'),
                        'file_size': metadata.get('file_size', 0),
                        'last_modified': metadata.get('last_modified', 0)
                    }
        
        # Sort by first topic, then filename
        sorted_docs = sorted(documents.values(), key=lambda x: (x['topics'][0] if x['topics'] else '', x['filename']))
        return sorted_docs
    
    def list_topics(self) -> List[str]:
        """
        Get list of all unique topics in the store.
        
        Returns:
            List of topic names (flattened from all hierarchies)
        """
        # Get all documents
        all_docs = self.collection.get()
        
        # Extract unique topics (flatten all topic lists)
        topics = set()
        if all_docs['metadatas']:
            for metadata in all_docs['metadatas']:
                # Deserialize topics
                metadata = self._deserialize_metadata(metadata)
                doc_topics = metadata.get('topics', ['uncategorized'])
                if isinstance(doc_topics, str):
                    topics.add(doc_topics)
                else:
                    topics.update(doc_topics)
        
        return sorted(list(topics))
    
    def get_stats(self) -> Dict:
        """Get statistics about the vector store."""
        documents = self.list_documents()
        topics = self.list_topics()
        
        # Count documents per topic (a document can appear in multiple topics)
        topic_counts = {}
        for doc in documents:
            for topic in doc['topics']:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        # Count by filetype
        filetype_counts = {}
        for doc in documents:
            filetype = doc.get('filetype', '.pdf')
            filetype_counts[filetype] = filetype_counts.get(filetype, 0) + 1
        
        return {
            'total_chunks': self.collection.count(),
            'total_documents': len(documents),
            'total_topics': len(topics),
            'documents': documents,
            'topics': topics,
            'documents_per_topic': topic_counts,
            'documents_per_filetype': filetype_counts,
            'collection_name': CHROMA_COLLECTION_NAME,
            'embedding_model': EMBEDDING_MODEL,
            'embedding_dimension': self.embedding_dimension,
            'distance_space': CHROMA_SPACE,
            'hybrid_search': self.bm25 is not None,
            'reranker': RERANKER_MODEL if self.cross_encoder else None,
        }
    
    def delete_document(self, filepath: str) -> int:
        """
        Delete all chunks from a specific document by filepath.
        
        Args:
            filepath: Full path of the document to delete
            
        Returns:
            Number of chunks deleted
        """
        # Get all documents
        all_docs = self.collection.get()

        # Find IDs matching the filepath
        ids_to_delete = []
        if all_docs['metadatas'] and all_docs['ids']:
            for i, metadata in enumerate(all_docs['metadatas']):
                if metadata.get('filepath') == filepath:
                    ids_to_delete.append(all_docs['ids'][i])
        
        # Delete
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
            self._invalidate_bm25()
            print(f"Deleted {len(ids_to_delete)} chunks from {filepath}", file=sys.stderr)
        
        return len(ids_to_delete)
    
    def delete_topic(self, topic: str) -> int:
        """
        Delete all chunks from a specific topic.
        
        Args:
            topic: Name of the topic to delete
            
        Returns:
            Number of chunks deleted
        """
        # Get all documents
        all_docs = self.collection.get()

        # Find IDs where topic appears in the topics list
        ids_to_delete = []
        if all_docs['metadatas'] and all_docs['ids']:
            for i, metadata in enumerate(all_docs['metadatas']):
                # Deserialize topics
                metadata = self._deserialize_metadata(metadata)
                doc_topics = metadata.get('topics', [])
                if isinstance(doc_topics, str):
                    doc_topics = [doc_topics]
                if topic in doc_topics:
                    ids_to_delete.append(all_docs['ids'][i])
        
        # Delete
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
            self._invalidate_bm25()
            print(f"Deleted {len(ids_to_delete)} chunks from topic '{topic}'", file=sys.stderr)
        
        return len(ids_to_delete)
    
    def reset(self):
        """Delete all documents from the collection."""
        self.client.delete_collection(CHROMA_COLLECTION_NAME)
        self.collection = self.client.create_collection(
            name=CHROMA_COLLECTION_NAME,
            configuration=self._hnsw_configuration(),
            metadata=self._collection_metadata(),
        )
        self._invalidate_bm25()
        print("Vector store reset", file=sys.stderr)


if __name__ == "__main__":
    # Test the vector store
    store = VectorStore()
    
    # Print stats
    stats = store.get_stats()
    print(f"\nVector Store Stats:", file=sys.stderr)
    print(f"Total chunks: {stats['total_chunks']}", file=sys.stderr)
    print(f"Total documents: {stats['total_documents']}", file=sys.stderr)
    print(f"Total topics: {stats['total_topics']}", file=sys.stderr)
    print(f"Documents: {stats['documents']}", file=sys.stderr)
    
    # Test search
    results = []
    if stats['total_chunks'] > 0:
        results = store.search("test query", n_results=3)
    print(f"\nTest search returned {len(results)} results", file=sys.stderr)

