import argparse
from pathlib import Path
from document_processor import DocumentProcessor
from vector_store import VectorStore
from config import SUPPORTED_EXTENSIONS, TOPIC_SEPARATOR
import sys


def add_docs_to_database(doc_dir: str):
    """
    Ingest all documents (PDFs and Word) from a directory into the vector store.
    Uses folder structure to tag documents with hierarchical topics.
    
    Args:
        doc_dir: Directory containing documents (organized by topic folders)
    """
    doc_path = Path(doc_dir)
    
    if not doc_path.exists():
        print(f"Error: Directory {doc_dir} does not exist")
        sys.exit(1)
    
    # Find all supported documents
    doc_files = []
    for ext in SUPPORTED_EXTENSIONS:
        doc_files.extend(list(doc_path.rglob(f"*{ext}")))
    
    if not doc_files:
        print(f"No supported documents found in {doc_dir}")
        print(f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
        sys.exit(0)
    
    print(f"Found {len(doc_files)} document files")
    print(f"Base directory: {doc_path}")
    
    # Analyze folder structure and topics
    all_topics = set()
    filetype_count = {}
    
    processor = DocumentProcessor()
    
    for doc_file in doc_files:
        topics = processor.extract_topics_from_path(doc_file, doc_path)
        all_topics.update(topics)
        
        ext = doc_file.suffix.lower()
        filetype_count[ext] = filetype_count.get(ext, 0) + 1
    
    if all_topics and DEFAULT_TOPIC not in all_topics:
        print(f"\nDetected topics: {', '.join(sorted(all_topics))}")
    else:
        print(f"\nNo topic folders detected (all documents in base directory)")
    
    print(f"\nDocument types:")
    for ext, count in sorted(filetype_count.items()):
        print(f"  {ext}: {count} files")
    
    # Initialize store
    store = VectorStore()
    
    # Process each document
    total_chunks = 0
    successful = 0
    failed = 0
    topic_stats = {}
    filetype_stats = {}
    
    for i, doc_file in enumerate(doc_files, 1):
        # Extract topics for display
        topics = processor.extract_topics_from_path(doc_file, doc_path)
        topics_display = TOPIC_SEPARATOR.join(topics)
        ext = doc_file.suffix.lower()
        
        print(f"\n[{i}/{len(doc_files)}] Processing: {doc_file.name}")
        print(f"  Type: {ext}")
        print(f"  Topics: {topics_display}")
        
        try:
            # Process document with base directory for topic extraction
            chunks = processor.process_document(str(doc_file), str(doc_path))
            
            if chunks:
                # Add to vector store
                num_added = store.add_documents(chunks)
                total_chunks += num_added
                successful += 1
                
                # Track per-topic stats
                for topic in topics:
                    if topic not in topic_stats:
                        topic_stats[topic] = {'docs': 0, 'chunks': 0}
                    topic_stats[topic]['chunks'] += num_added
                topic_stats[topics[0]]['docs'] += 1  # Count doc under first topic
                
                # Track per-filetype stats
                if ext not in filetype_stats:
                    filetype_stats[ext] = {'docs': 0, 'chunks': 0}  
                filetype_stats[ext]['docs'] += 1
                filetype_stats[ext]['chunks'] += num_added
                
                print(f"  ✓ Added {num_added} chunks")
            else:
                print(f"  ⚠ No text extracted from {doc_file.name}")
                failed += 1
                
        except Exception as e:
            print(f"  ✗ Error processing {doc_file.name}: {e}")
            failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("INGESTION SUMMARY")
    print("="*60)
    print(f"Total documents processed: {len(doc_files)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total chunks added: {total_chunks}")
    
    if topic_stats:
        print(f"\nChunks per topic:")
        for topic in sorted(topic_stats.keys()):
            stats = topic_stats[topic]
            docs_str = f"{stats['docs']} documents" if 'docs' in stats and stats['docs'] > 0 else ""
            print(f"  {topic}: {stats['chunks']} chunks" + (f" ({docs_str})" if docs_str else ""))
    
    if filetype_stats:
        print(f"\nDocuments per file type:")
        for ext in sorted(filetype_stats.keys()):
            stats = filetype_stats[ext]
            print(f"  {ext}: {stats['docs']} documents, {stats['chunks']} chunks")
    
    print(f"\nVector store stats:")
    stats = store.get_stats()
    print(f"  Total chunks in store: {stats['total_chunks']}")
    print(f"  Total documents: {stats['total_documents']}")
    print(f"  Total topics: {stats['total_topics']}")
    if stats['topics']:
        print(f"  Topics: {', '.join(stats['topics'])}")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents (PDF, Word) into the vector store"
    )
    parser.add_argument(
        "--doc-dir",
        type=str,
        required=True,
        help="Directory containing documents (organized by topic folders)",
        default="./docs"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the vector store before ingestion"
    )
    
    args = parser.parse_args()
    
    # Reset if requested
    if args.reset:
        print("Resetting vector store...")
        store = VectorStore()
        store.reset()
    
    # Ingest documents
    add_docs_to_database(args.doc_dir)


if __name__ == "__main__":
    # Import here to avoid circular dependency
    from config import DEFAULT_TOPIC
    main()
