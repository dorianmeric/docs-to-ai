import argparse
from pathlib import Path
from pdf_processor import PDFProcessor
from vector_store import VectorStore
import sys


def ingest_pdfs(pdf_dir: str, recursive: bool = False):
    """
    Ingest all PDFs from a directory into the vector store.
    
    Args:
        pdf_dir: Directory containing PDFs
        recursive: Whether to search subdirectories
    """
    pdf_path = Path(pdf_dir)
    
    if not pdf_path.exists():
        print(f"Error: Directory {pdf_dir} does not exist")
        sys.exit(1)
    
    # Find all PDFs
    if recursive:
        pdf_files = list(pdf_path.rglob("*.pdf"))
    else:
        pdf_files = list(pdf_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        sys.exit(0)
    
    print(f"Found {len(pdf_files)} PDF files")
    
    # Initialize processor and store
    processor = PDFProcessor()
    store = VectorStore()
    
    # Process each PDF
    total_chunks = 0
    successful = 0
    failed = 0
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_file.name}")
        
        try:
            # Process PDF
            chunks = processor.process_pdf(str(pdf_file))
            
            if chunks:
                # Add to vector store
                num_added = store.add_documents(chunks)
                total_chunks += num_added
                successful += 1
                print(f"✓ Added {num_added} chunks")
            else:
                print(f"⚠ No text extracted from {pdf_file.name}")
                failed += 1
                
        except Exception as e:
            print(f"✗ Error processing {pdf_file.name}: {e}")
            failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("INGESTION SUMMARY")
    print("="*60)
    print(f"Total PDFs processed: {len(pdf_files)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total chunks added: {total_chunks}")
    print(f"\nVector store stats:")
    stats = store.get_stats()
    print(f"  Total chunks in store: {stats['total_chunks']}")
    print(f"  Total documents: {len(stats['documents'])}")


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
        help="Search subdirectories recursively"
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
