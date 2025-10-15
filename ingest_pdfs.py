import argparse
from pathlib import Path
from pdf_processor import PDFProcessor
from vector_store import VectorStore
import sys


def ingest_pdfs(pdf_dir: str, recursive: bool = False):
    """
    Ingest all PDFs from a directory into the vector store.
    Uses full folder hierarchy from the base directory to tag documents with topics.
    
    Args:
        pdf_dir: Directory containing PDFs (organized by topic folders)
        recursive: Whether to search subdirectories (default True for topic support)
    """
    pdf_path = Path(pdf_dir)
    
    if not pdf_path.exists():
        print(f"Error: Directory {pdf_dir} does not exist")
        sys.exit(1)
    
    # Find all PDFs (always recursive to support topic folders)
    pdf_files = list(pdf_path.rglob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        sys.exit(0)
    
    print(f"Found {len(pdf_files)} PDF files")
    print(f"Base directory: {pdf_path}")
    
    # Analyze folder structure
    topics = set()
    for pdf_file in pdf_files:
        rel_path = pdf_file.parent.relative_to(pdf_path)
        folder_chain = [part for part in rel_path.parts if part]
        topics.update(folder_chain)
    
    if topics:
        print(f"\nDetected topics: {', '.join(sorted(topics))}")
    else:
        print(f"\nNo topic folders detected (all PDFs in base directory)")
    
    # Initialize processor and store
    processor = PDFProcessor()
    store = VectorStore()
    
    # Process each PDF
    total_chunks = 0
    successful = 0
    failed = 0
    topic_stats = {}
    
    for i, pdf_file in enumerate(pdf_files, 1):
        # Extract all folder levels as topics
        rel_path = pdf_file.parent.relative_to(pdf_path)
        topic_hierarchy = [part for part in rel_path.parts if part]
        topic_display = " > ".join(topic_hierarchy) if topic_hierarchy else "Base Folder"
        
        print(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_file.name}")
        print(f"  Topics: {topic_hierarchy}")
        
        try:
            # Process PDF with base directory for topic extraction
            chunks = processor.process_pdf(str(pdf_file), str(pdf_path))
            
            if chunks:
                # Add topic tags to chunks (if the processor supports metadata)
                for chunk in chunks:
                    chunk['metadata']['topics'] = topic_hierarchy
                
                # Add to vector store
                num_added = store.add_documents(chunks)
                total_chunks += num_added
                successful += 1
                
                # Track per-topic stats
                for topic in topic_hierarchy:
                    if topic not in topic_stats:
                        topic_stats[topic] = {'docs': 0, 'chunks': 0}
                    topic_stats[topic]['docs'] += 1
                    topic_stats[topic]['chunks'] += num_added
                
                print(f"  ✓ Added {num_added} chunks")
            else:
                print(f"  ⚠ No text extracted from {pdf_file.name}")
                failed += 1
                
        except Exception as e:
            print(f"  ✗ Error processing {pdf_file.name}: {e}")
            failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("INGESTION SUMMARY")
    print("="*60)
    print(f"Total PDFs processed: {len(pdf_files)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total chunks added: {total_chunks}")
    
    if topic_stats:
        print(f"\nDocuments per topic:")
        for topic in sorted(topic_stats.keys()):
            stats = topic_stats[topic]
            print(f"  {topic}: {stats['docs']} documents, {stats['chunks']} chunks")
    
    print(f"\nVector store stats:")
    stats = store.get_stats()
    print(f"  Total chunks in store: {stats['total_chunks']}")
    print(f"  Total documents: {stats['total_documents']}")
    print(f"  Total topics: {stats['total_topics']}")
    if stats['topics']:
        print(f"  Topics: {', '.join(stats['topics'])}")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest PDF documents into the vector store"
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        required=True,
        help="Directory containing PDF files"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Search subdirectories recursively (default: True)"
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
    
    # Ingest PDFs
    ingest_pdfs(args.pdf_dir, args.recursive)


if __name__ == "__main__":
    main()
