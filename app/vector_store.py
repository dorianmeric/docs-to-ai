import chromadb
from chromadb.config import Settings
from chromadb.types import Metadata
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Optional, Any
import json
from app.config import (
    CHROMADB_DIR, 
    CHROMA_COLLECTION_NAME, 
    EMBEDDING_MODEL,
    DEFAULT_SEARCH_RESULTS,
    USE_RERANKER,
    RERANKER_MODEL,
    RERANKER_TOP_N
)
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

        # Initialize embedding model
        # print(f"Loading embedding model: {EMBEDDING_MODEL}", file=sys.stderr)
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        
        # Initialize re-ranker model if enabled
        self.cross_encoder = None
        if USE_RERANKER:
            print(f"Loading re-ranker model: {RERANKER_MODEL}", file=sys.stderr)
            self.cross_encoder = CrossEncoder(RERANKER_MODEL)
            print("Re-ranker is active.", file=sys.stderr)

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"description": "Document chunks with hierarchical topics"}
        )

        print(f"Vector store initialized. Documents chunks in collection: {self.collection.count()}", file=sys.stderr)

        # Mark as initialized
        VectorStore._initialized = True
    
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
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        
        # Add to collection (using upsert to prevent duplicates)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"Added {len(chunks)} chunks to vector store", file=sys.stderr)
        return len(chunks)
    
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
    
    def search(self, query: str, n_results: int = DEFAULT_SEARCH_RESULTS) -> List[Dict]:
        """
        Search for relevant document chunks, with optional re-ranking.
        
        Args:
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List of search results with text, metadata, and relevance scores
        """
        # Determine number of results to fetch for initial search
        search_n_results = RERANKER_TOP_N if self.cross_encoder else n_results
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])[0]
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=search_n_results
        )
        
        # Format results
        formatted_results = []
        if results['ids'] and results['ids'][0] and results['metadatas'] and results['documents']:
            distances = results.get('distances')
            for i in range(len(results['ids'][0])):
                metadata = self._deserialize_metadata(results['metadatas'][0][i])
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': metadata,
                    'distance': distances[0][i] if distances and distances[0] else None
                })
        
        # Re-rank if enabled
        if self.cross_encoder and formatted_results:
            print(f"Re-ranking top {len(formatted_results)} results...", file=sys.stderr)
            
            # Create pairs of [query, passage]
            pairs = [[query, result['text']] for result in formatted_results]
            
            # Predict scores
            scores = self.cross_encoder.predict(pairs, show_progress_bar=False)
            
            # Add scores to results and sort
            for result, score in zip(formatted_results, scores):
                result['relevance_score'] = float(score)
                
            # Sort by new relevance score
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
            'collection_name': CHROMA_COLLECTION_NAME
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
            print(f"Deleted {len(ids_to_delete)} chunks from topic '{topic}'", file=sys.stderr)
        
        return len(ids_to_delete)
    
    def reset(self):
        """Delete all documents from the collection."""
        self.client.delete_collection(CHROMA_COLLECTION_NAME)
        self.collection = self.client.create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"description": "Document chunks with hierarchical topics"}
        )
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

