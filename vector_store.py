import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
from config import (
    CHROMA_DB_DIR, 
    CHROMA_COLLECTION_NAME, 
    EMBEDDING_MODEL,
    DEFAULT_SEARCH_RESULTS
)


class VectorStore:
    """Manages vector database operations using ChromaDB."""
    
    def __init__(self):
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize embedding model
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"description": "PDF document chunks"}
        )
        
        print(f"Vector store initialized. Documents in collection: {self.collection.count()}")
    
    def add_documents(self, chunks: List[Dict[str, any]]) -> int:
        """
        Add document chunks to the vector store.
        
        Args:
            chunks: List of chunks from PDFProcessor
            
        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0
        
        # Extract data
        ids = [chunk['id'] for chunk in chunks]
        texts = [chunk['text'] for chunk in chunks]
        metadatas = [chunk['metadata'] for chunk in chunks]
        
        # Generate embeddings
        print(f"Generating embeddings for {len(texts)} chunks...")
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        
        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"Added {len(chunks)} chunks to vector store")
        return len(chunks)
    
    def search(self, query: str, n_results: int = DEFAULT_SEARCH_RESULTS) -> List[Dict]:
        """
        Search for relevant document chunks.
        
        Args:
            query: Search query
            n_results: Number of results to return
            
        Returns:
            List of search results with text, metadata, and relevance scores
        """
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])[0]
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results
        )
        
        # Format results
        formatted_results = []
        
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': results['distances'][0][i] if 'distances' in results else None
                })
        
        return formatted_results
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """
        Retrieve a specific document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document dict or None if not found
        """
        result = self.collection.get(ids=[doc_id])
        
        if result['ids']:
            return {
                'id': result['ids'][0],
                'text': result['documents'][0],
                'metadata': result['metadatas'][0]
            }
        
        return None
    
    def list_documents(self) -> List[str]:
        """
        Get list of all unique documents in the store.
        
        Returns:
            List of document filenames
        """
        # Get all documents
        all_docs = self.collection.get()
        
        # Extract unique filenames
        filenames = set()
        if all_docs['metadatas']:
            for metadata in all_docs['metadatas']:
                if 'filename' in metadata:
                    filenames.add(metadata['filename'])
        
        return sorted(list(filenames))
    
    def get_stats(self) -> Dict:
        """Get statistics about the vector store."""
        return {
            'total_chunks': self.collection.count(),
            'documents': self.list_documents(),
            'collection_name': CHROMA_COLLECTION_NAME
        }
    
    def delete_document(self, filename: str) -> int:
        """
        Delete all chunks from a specific document.
        
        Args:
            filename: Name of the document to delete
            
        Returns:
            Number of chunks deleted
        """
        # Get all documents
        all_docs = self.collection.get()
        
        # Find IDs matching the filename
        ids_to_delete = []
        if all_docs['metadatas']:
            for i, metadata in enumerate(all_docs['metadatas']):
                if metadata.get('filename') == filename:
                    ids_to_delete.append(all_docs['ids'][i])
        
        # Delete
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
            print(f"Deleted {len(ids_to_delete)} chunks from {filename}")
        
        return len(ids_to_delete)
    
    def reset(self):
        """Delete all documents from the collection."""
        self.client.delete_collection(CHROMA_COLLECTION_NAME)
        self.collection = self.client.create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"description": "PDF document chunks"}
        )
        print("Vector store reset")


if __name__ == "__main__":
    # Test the vector store
    store = VectorStore()
    
    # Print stats
    stats = store.get_stats()
    print(f"\nVector Store Stats:")
    print(f"Total chunks: {stats['total_chunks']}")
    print(f"Documents: {stats['documents']}")
    
    # Test search
    if stats['total_chunks'] > 0:
        results = store.search("test query", n_results=3)
        print(f"\nTest search returned {len(results)} results")
