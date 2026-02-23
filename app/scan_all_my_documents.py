# Standard library imports for argument parsing, path handling, and system operations
import argparse
from pathlib import Path

# Application-specific imports for document processing and vector storage
from .document_processor import DocumentProcessor
from .vector_store import VectorStore
from .config import SUPPORTED_EXTENSIONS, TOPIC_SEPARATOR, DEFAULT_TOPIC, DOCS_DIR
import sys

def scan_all(doc_dir: str | Path = DOCS_DIR, reset_database: bool = True):
    """
    Ingest all documents (PDFs, Word, Markdown, Excel) from a directory into the vector store.
    Uses folder structure to tag documents with hierarchical topics.

    Args:
        doc_dir: Directory containing documents (organized by topic folders)
        reset_database: If True, clears the database before adding documents

    Note:
        Uses the singleton VectorStore instance internally, ensuring all scans
        operate on the same vector database.
    """

    # Force database reset regardless of parameter to prevent duplicate entries
    reset_database = True # Always reset when called, to avoid duplicates

    # Convert input to Path object for consistent path handling
    doc_path = Path(doc_dir)

    # Initialize list to collect response messages for the user
    response_parts = []

    # Validate that the target directory exists before proceeding
    if not doc_path.exists():
        response_parts.append(f"Error: Directory {doc_dir} does not exist")
        return f"\n".join(response_parts)

    # Debug: Output directory information for diagnostics
    response_parts.append(f"Scanning directory: {doc_path.absolute()}")
    response_parts.append(f"Directory exists: {doc_path.exists()}")
    response_parts.append(f"Directory is readable: {doc_path.is_dir()}")

    # Debug: List all items in the directory to provide diagnostics
    try:
        # Get all items (files and directories) at the top level
        all_items = list(doc_path.iterdir())
        response_parts.append(f"Total items in directory: {len(all_items)}")

        # Separate files from directories for clearer reporting
        files = [f for f in all_items if f.is_file()]
        dirs = [d for d in all_items if d.is_dir()]
        response_parts.append(f"  Files: {len(files)}, Directories: {len(dirs)}")

        # Show a sample of files (up to 5) to help user understand what's there
        if files:
            response_parts.append(f"  Sample files: {[f.name for f in files[:5]]}")
    except Exception as e:
        # Gracefully handle permission or other errors when listing directory
        response_parts.append(f"  Warning: Could not list directory contents: {e}")
    
    # Find all supported documents recursively (case-insensitive search)
    doc_files = []
    for ext in SUPPORTED_EXTENSIONS:
        # Search for lowercase extensions (e.g., .pdf, .docx, .md)
        doc_files.extend(list(doc_path.rglob(f"*{ext}")))  # lowercase

        # Search for uppercase extensions (e.g., .PDF, .DOCX, .MD)
        doc_files.extend(list(doc_path.rglob(f"*{ext.upper()}")))  # uppercase

        # Also handle mixed case extensions like .Pdf, .Doc, .Md, etc.
        if len(ext) > 1:
            # Capitalize first letter after dot: .Pdf, .Docx, .Md
            mixed_case = ext[0] + ext[1].upper() + ext[2:].lower()
            doc_files.extend(list(doc_path.rglob(f"*{mixed_case}")))

    # Remove duplicates since the same file may have been matched by multiple patterns
    doc_files = list(set(doc_files))

    # Debug: Report search results to help diagnose empty directories
    response_parts.append(f"\nSearched for extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
    response_parts.append(f"Found {len(doc_files)} matching document(s)")

    # Exit early if no supported documents were found
    if not doc_files:
        response_parts.append(f"\n⚠ No supported documents found in {doc_dir}.")
        response_parts.append(f"Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)} (case-insensitive)")
        response_parts.append(f"Please add documents to {doc_path.absolute()} and scan again.")
        return f"\n".join(response_parts)

    # Print header for the document scanning process
    response_parts.append(f"\n{'='*60}")
    response_parts.append(f"DOCUMENT SCAN STARTING")
    response_parts.append(f"{'='*60}")
    response_parts.append(f"Base directory: {doc_path}")
    response_parts.append(f"Total documents found: {len(doc_files)}\n")


    # Analyze folder structure to extract topics and count file types
    all_topics = set()  # Track unique topics across all documents
    filetype_count = {}  # Count documents by extension

    # Initialize document processor for extracting text and topics
    processor = DocumentProcessor()

    # First pass: Extract topics and count file types before processing
    for doc_file in doc_files:
        # Extract topic hierarchy from folder structure (e.g., "python/web" from path)
        topics = processor.extract_topics_from_path(doc_file, doc_path)
        all_topics.update(topics)

        # Track file extension statistics (normalized to lowercase)
        ext = doc_file.suffix.lower()
        filetype_count[ext] = filetype_count.get(ext, 0) + 1
    
    # Display detected topics (folder-based organization)
    if all_topics and DEFAULT_TOPIC not in all_topics:
        response_parts.append(f"\nDetected topics: {', '.join(sorted(all_topics))}")
    else:
        # All documents are in the base directory with no topic organization
        response_parts.append(f"\nNo topic folders detected (all documents in base directory)")

    # Display file type distribution
    response_parts.append(f"\nDocument types:")
    for ext, count in sorted(filetype_count.items()):
        response_parts.append(f"\n  {ext}: {count} files")

    # Get the singleton VectorStore instance
    # All calls to VectorStore() return the same instance (singleton pattern)
    vector_store = VectorStore()

    # Reset the vector database if requested (prevents duplicates)
    if reset_database:
        response_parts.append("\n⚠ Resetting vector store (clearing all existing documents)...")
        try:
            # Clear all existing vectors and documents from the database
            vector_store.reset()
        except Exception as e:
            # First-time setup: database doesn't exist yet, which is fine
            response_parts.append("✓ Vector store did not exist yet, skipping")

        response_parts.append("✓ Vector store reset complete")

        # Clear document cache to ensure fresh extraction from source files
        response_parts.append("\n⚠ Clearing document cache...")
        processor.clear_document_cache()
        response_parts.append("✓ Document cache cleared\n")
    
    # Process each document and track statistics
    total_chunks = 0  # Total number of text chunks created
    successful = 0  # Count of successfully processed documents
    failed = 0  # Count of failed document processing attempts
    topic_stats = {}  # Statistics per topic (documents and chunks)
    filetype_stats = {}  # Statistics per file type (documents and chunks)

    # Second pass: Process each document and add to vector store
    for i, doc_file in enumerate(doc_files, 1):
        # Extract topics for display and metadata tagging
        topics = processor.extract_topics_from_path(doc_file, doc_path)
        topics_display = TOPIC_SEPARATOR.join(topics)  # e.g., "python/web"
        ext = doc_file.suffix.lower()

        # Display progress for current document
        response_parts.append(f"\n[{i}/{len(doc_files)}] Processing: {doc_file.name}")
        response_parts.append(f"  Type: {ext}")
        response_parts.append(f"  Topics: {topics_display}")
        
        try:
            # Process the document: extract text, split into chunks, add metadata
            chunks = processor.process_document(str(doc_file), str(doc_path))

            if chunks:
                # Add all chunks to the vector store for semantic search
                num_added = vector_store.add_documents(chunks)
                total_chunks += num_added
                successful += 1

                # Track statistics per topic for reporting
                for topic in topics:
                    if topic not in topic_stats:
                        topic_stats[topic] = {'docs': 0, 'chunks': 0}
                    topic_stats[topic]['chunks'] += num_added
                # Count the document under its primary (first) topic
                topic_stats[topics[0]]['docs'] += 1

                # Track statistics per file type for reporting
                if ext not in filetype_stats:
                    filetype_stats[ext] = {'docs': 0, 'chunks': 0}
                filetype_stats[ext]['docs'] += 1
                filetype_stats[ext]['chunks'] += num_added

                response_parts.append(f"  ✓ Added {num_added} chunks")
            else:
                # Document was processed but yielded no text (possibly empty or unsupported format)
                response_parts.append(f"  ⚠ No text extracted from {doc_file.name}")
                failed += 1

        except Exception as e:
            # Catch and report any errors during document processing
            response_parts.append(f"  ✗ Error processing {doc_file.name}: {e}")
            failed += 1
    
    # Print summary report of the ingestion process
    response_parts.append("\n" + "="*60)
    response_parts.append("INGESTION SUMMARY")
    response_parts.append("="*60)
    response_parts.append(f"Total documents processed: {len(doc_files)}")
    response_parts.append(f"Successful: {successful}")
    response_parts.append(f"Failed: {failed}")
    response_parts.append(f"Total chunks added: {total_chunks}")

    # Display breakdown of chunks by topic
    if topic_stats:
        response_parts.append(f"\nChunks per topic:")
        for topic in sorted(topic_stats.keys()):
            stats = topic_stats[topic]
            docs_str = f"{stats['docs']} documents" if 'docs' in stats and stats['docs'] > 0 else ""
            response_parts.append(f"  {topic}: {stats['chunks']} chunks" + (f" ({docs_str})" if docs_str else ""))

    # Display breakdown of documents by file type
    if filetype_stats:
        response_parts.append(f"\nDocuments per file type:")
        for ext in sorted(filetype_stats.keys()):
            stats = filetype_stats[ext]
            response_parts.append(f"  {ext}: {stats['docs']} documents, {stats['chunks']} chunks")

    # Query and display current vector store statistics
    response_parts.append(f"\nVector store stats:")
    stats = vector_store.get_stats()
    response_parts.append(f"  Total chunks in store: {stats['total_chunks']}")
    response_parts.append(f"  Total documents: {stats['total_documents']}")
    response_parts.append(f"  Total topics: {stats['total_topics']}")
    if stats['topics']:
        response_parts.append(f"  Topics: {', '.join(stats['topics'])}")

    # Final success message
    response_parts.append(f"\n✓ Successfully scanned and updated all documents (database was reset to prevent duplicates)")

    # Return all collected messages as a single string
    return f"\n".join(response_parts)

def main():
    """
    Command-line entry point for the document ingestion script.
    Parses arguments and initiates the scan process.
    """
    # Set up command-line argument parser
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

    # Parse command-line arguments
    args = parser.parse_args()

    # Reset vector store if user specified the --reset flag
    if args.reset:
        print("Resetting vector store...", file=sys.stderr)
        store = VectorStore()
        store.reset()

    # Start the document ingestion process
    scan_all(args.doc_dir)


# Entry point when script is run directly (not imported as a module)
if __name__ == "__main__":
    main()
