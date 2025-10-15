"""
Test script for the PDF document query system.
Run this to verify all components are working correctly.
"""

from pathlib import Path
from pdf_processor import PDFProcessor
from vector_store import VectorStore
import sys


def test_pdf_processor():
    """Test PDF processing."""
    print("="*60)
    print("Testing PDF Processor")
    print("="*60)
    
    processor = PDFProcessor()
    print("✓ PDFProcessor initialized")
    
    # Check if test PDF exists
    test_pdf = Path("test.pdf")
    if test_pdf.exists():
        print(f"\nProcessing test file: {test_pdf}")
        chunks = processor.process_pdf(str(test_pdf))
        print(f"✓ Extracted {len(chunks)} chunks")
        
        if chunks:
            print(f"\nFirst chunk preview:")
            print(chunks[0]['text'][:200])
            print(f"\nMetadata: {chunks[0]['metadata']}")
    else:
        print(f"\n⚠ No test.pdf found. Place a test PDF in the root directory to test extraction.")
    
    return True


def test_vector_store():
    """Test vector store operations."""
    print("\n" + "="*60)
    print("Testing Vector Store")
    print("="*60)
    
    store = VectorStore()
    print("✓ VectorStore initialized")
    
    stats = store.get_stats()
    print(f"\nCurrent stats:")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Documents: {len(stats['documents'])}")
    
    if stats['documents']:
        print(f"\nDocuments in store:")
        for doc in stats['documents']:
            print(f"  - {doc}")
        
        # Test search
        print(f"\nTesting search...")
        results = store.search("test query", n_results=3)
        print(f"✓ Search returned {len(results)} results")
        
        if results:
            print(f"\nTop result preview:")
            print(f"  File: {results[0]['metadata'].get('filename')}")
            print(f"  Page: {results[0]['metadata'].get('page')}")
            print(f"  Text: {results[0]['text'][:100]}...")
    else:
        print("\n⚠ No documents in vector store. Run ingest_pdfs.py to add documents.")
    
    return True


def test_integration():
    """Test full integration."""
    print("\n" + "="*60)
    print("Integration Test")
    print("="*60)
    
    # Check if we have a test PDF
    test_pdf = Path("test.pdf")
    if not test_pdf.exists():
        print("⚠ Skipping integration test - no test.pdf found")
        return True
    
    print(f"\nRunning full pipeline on {test_pdf}...")
    
    # Process PDF
    processor = PDFProcessor()
    chunks = processor.process_pdf(str(test_pdf))
    print(f"✓ Extracted {len(chunks)} chunks")
    
    if not chunks:
        print("✗ No chunks extracted")
        return False
    
    # Add to vector store
    store = VectorStore()
    num_added = store.add_documents(chunks)
    print(f"✓ Added {num_added} chunks to vector store")
    
    # Test search
    test_query = chunks[0]['text'][:50]  # Use part of first chunk as query
    print(f"\nSearching for: '{test_query}'")
    results = store.search(test_query, n_results=3)
    print(f"✓ Found {len(results)} results")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PDF DOCUMENT QUERY SYSTEM - TEST SUITE")
    print("="*60 + "\n")
    
    tests = [
        ("PDF Processor", test_pdf_processor),
        ("Vector Store", test_vector_store),
        ("Integration", test_integration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            print(f"\n✗ {test_name} failed with error: {e}")
            results.append((test_name, False, str(e)))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"       Error: {error}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
