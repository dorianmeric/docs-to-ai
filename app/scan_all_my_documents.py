import argparse
from pathlib import Path
from app.document_processor import DocumentProcessor
from app.vector_store import VectorStore
from app.config import SUPPORTED_EXTENSIONS, TOPIC_SEPARATOR, DEFAULT_TOPIC, DOCS_DIR
import sys
from mcp.types import Tool, TextContent


def scan_all_my_documents(doc_dir: str = DOCS_DIR, reset_database: bool = True):
    """
    Ingest all documents (PDFs, Word, Markdown, Excel) from a directory into the vector store.
    Uses folder structure to tag documents with hierarchical topics.
    
    Args:
        doc_dir: Directory containing documents (organized by topic folders)
        reset_database: If True, clears the database before adding documents
    """

    reset_database = True # Always reset when called, to avoid duplicates

    doc_path = Path(doc_dir)
    
    response_parts = []

    if not doc_path.exists():
        response_parts.append(f"Error: Directory {doc_dir} does not exist")
        return [TextContent(
            type="text",
            text="\n".join(response_parts)
        )]

    # Debug: Check if directory is readable
    response_parts.append(f"Scanning directory: {doc_path.absolute()}")
    response_parts.append(f"Directory exists: {doc_path.exists()}")
    response_parts.append(f"Directory is readable: {doc_path.is_dir()}")

    # Debug: List all files in directory (first level)
    try:
        all_items = list(doc_path.iterdir())
        response_parts.append(f"Total items in directory: {len(all_items)}")
        files = [f for f in all_items if f.is_file()]
        dirs = [d for d in all_items if d.is_dir()]
        response_parts.append(f"  Files: {len(files)}, Directories: {len(dirs)}")
        if files:
            response_parts.append(f"  Sample files: {[f.name for f in files[:5]]}")
    except Exception as e:
        response_parts.append(f"  Warning: Could not list directory contents: {e}")
    
    # Find all supported documents (case-insensitive)
    doc_files = []
    for ext in SUPPORTED_EXTENSIONS:
        # Find both lowercase and uppercase variants
        # e.g., .pdf, .PDF, .Pdf, etc.
        doc_files.extend(list(doc_path.rglob(f"*{ext}")))  # lowercase
        doc_files.extend(list(doc_path.rglob(f"*{ext.upper()}")))  # uppercase
        # Also handle mixed case like .Pdf, .Doc, etc.
        if len(ext) > 1:
            # Capitalize first letter after dot: .Pdf, .Docx, etc.
            mixed_case = ext[0] + ext[1].upper() + ext[2:].lower()
            doc_files.extend(list(doc_path.rglob(f"*{mixed_case}")))

    # Remove duplicates (in case same file matched multiple patterns)
    doc_files = list(set(doc_files))

    # Debug: Show what extensions were found
    response_parts.append(f"\nSearched for extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
    response_parts.append(f"Found {len(doc_files)} matching document(s)")

    if not doc_files:
        response_parts.append(f"\n⚠ No supported documents found in {doc_dir}.")
        response_parts.append(f"Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)} (case-insensitive)")
        response_parts.append(f"Please add documents to {doc_path.absolute()} and scan again.")
        return [TextContent(
            type="text",
            text="\n".join(response_parts)
        )]

    response_parts.append(f"\n{'='*60}")
    response_parts.append(f"DOCUMENT SCAN STARTING")
    response_parts.append(f"{'='*60}")
    response_parts.append(f"Base directory: {doc_path}")
    response_parts.append(f"Total documents found: {len(doc_files)}\n")


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
        response_parts.append(f"\nDetected topics: {', '.join(sorted(all_topics))}")
    else:
        response_parts.append(f"\nNo topic folders detected (all documents in base directory)")
    
    response_parts.append(f"\nDocument types:")
    for ext, count in sorted(filetype_count.items()):
        response_parts.append(f"\n  {ext}: {count} files")
    
    # Initialize store
    vector_store = VectorStore()
    
    # Reset database if requested
    if reset_database:
        response_parts.append(f"\n  {ext}: {count} files")
        response_parts.append("\n⚠ Resetting vector store (clearing all existing documents)...")
        vector_store.reset()
        response_parts.append("✓ Vector store reset complete")
        
        # Clear document cache to ensure fresh extraction
        response_parts.append("\n⚠ Clearing document cache...")
        processor.clear_document_cache()
        response_parts.append("✓ Document cache cleared\n")
    
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
        
        response_parts.append(f"\n[{i}/{len(doc_files)}] Processing: {doc_file.name}")
        response_parts.append(f"  Type: {ext}")
        response_parts.append(f"  Topics: {topics_display}")
        
        try:
            # Process document with base directory for topic extraction
            chunks = processor.process_document(str(doc_file), str(doc_path))
            
            if chunks:
                # Add to vector store
                num_added = vector_store.add_documents(chunks)
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
                
                response_parts.append(f"  ✓ Added {num_added} chunks")
            else:
                response_parts.append(f"  ⚠ No text extracted from {doc_file.name}")
                failed += 1
                
        except Exception as e:
            response_parts.append(f"  ✗ Error processing {doc_file.name}: {e}")
            failed += 1
    
    # Summary
    response_parts.append("\n" + "="*60)
    response_parts.append("INGESTION SUMMARY")
    response_parts.append("="*60)
    response_parts.append(f"Total documents processed: {len(doc_files)}")
    response_parts.append(f"Successful: {successful}")
    response_parts.append(f"Failed: {failed}")
    response_parts.append(f"Total chunks added: {total_chunks}")
    
    if topic_stats:
        response_parts.append(f"\nChunks per topic:")
        for topic in sorted(topic_stats.keys()):
            stats = topic_stats[topic]
            docs_str = f"{stats['docs']} documents" if 'docs' in stats and stats['docs'] > 0 else ""
            response_parts.append(f"  {topic}: {stats['chunks']} chunks" + (f" ({docs_str})" if docs_str else ""))
    
    if filetype_stats:
        response_parts.append(f"\nDocuments per file type:")
        for ext in sorted(filetype_stats.keys()):
            stats = filetype_stats[ext]
            response_parts.append(f"  {ext}: {stats['docs']} documents, {stats['chunks']} chunks")
    
    response_parts.append(f"\nVector store stats:")
    stats = vector_store.get_stats()
    response_parts.append(f"  Total chunks in store: {stats['total_chunks']}")
    response_parts.append(f"  Total documents: {stats['total_documents']}")
    response_parts.append(f"  Total topics: {stats['total_topics']}")
    if stats['topics']:
        response_parts.append(f"  Topics: {', '.join(stats['topics'])}")

    response_parts.append(f"\n✓ Successfully scanned and updated all documents (database was reset to prevent duplicates)")

    return [TextContent(
                type="text",
                text="\n".join(response_parts)
            )]

def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents (PDF, Word, Markdown, Excel) into the vector store"
    )
    parser.add_argument(
        "--doc-dir",
        type=str,
        required=False,
        help="Directory containing documents (organized by topic folders)",
        default="./my-docs"
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
    scan_all_my_documents(args.doc_dir)


if __name__ == "__main__":
    main()
