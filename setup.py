"""
Setup script for the PDF Document Query System.
Run this after installing requirements to set up the environment.
"""

import os
from pathlib import Path
from config import CHROMA_DB_DIR, DOC_CACHE_DIR


def create_directories():
    """Create necessary directories."""
    print("Creating directories...")
    
    directories = [
        CHROMA_DB_DIR,
        DOC_CACHE_DIR,
        Path("docs")  # Default documents directory
    ]
    
    for directory in directories:
        directory.mkdir(exist_ok=True)
        print(f"  ✓ {directory}")


def create_env_file():
    """Create .env file if it doesn't exist."""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists() and env_example.exists():
        print("\nCreating .env file...")
        with open(env_example, 'r') as src:
            content = src.read()
        with open(env_file, 'w') as dst:
            dst.write(content)
        print("  ✓ .env created from .env.example")
    else:
        print("\n.env file already exists")


def check_dependencies():
    """Check if required dependencies are installed."""
    print("\nChecking dependencies...")
    
    required_packages = [
        'chromadb',
        'sentence_transformers',
        'fitz',  # PyMuPDF
        'docx',  # python-docx
        'mcp'
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} (missing)")
            missing.append(package)
    
    if missing:
        print(f"\n⚠ Missing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    return True


def download_embedding_model():
    """Download the embedding model."""
    print("\nDownloading embedding model...")
    
    try:
        from sentence_transformers import SentenceTransformer
        from config import EMBEDDING_MODEL
        
        print(f"  Downloading {EMBEDDING_MODEL}...")
        model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"  ✓ Model downloaded and cached")
        return True
    except Exception as e:
        print(f"  ✗ Error downloading model: {e}")
        return False


def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "="*60)
    print("SETUP COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("\n1. Add your documents:")
    print("   - Organize PDFs and Word docs in folders by topic")
    print("   - Place documents in the 'docs' directory")
    print("   - Folder hierarchy becomes topic tags")
    print("   - Example: docs/Project_Name/Legal_Docs/contract.pdf")
    print("     → Topics: ['Project_Name', 'Legal_Docs']")
    
    print("\n2. Ingest your documents:")
    print("   python ingest_documents.py --doc-dir ./docs")
    
    print("\n3. Test the system:")
    print("   python test_system.py")
    
    print("\n4. Configure Claude Desktop:")
    print("   Add this to your claude_desktop_config.json:")
    print("   {")
    print('     "mcpServers": {')
    print('       "doc-to-ai": {')
    print('         "command": "python",')
    current_dir = Path.cwd()
    print(f'         "args": ["{current_dir / "mcp_server.py"}"]')
    print('       }')
    print('     }')
    print("   }")
    
    print("\n5. Restart Claude Desktop to load the MCP server")
    print("\nFor more information, see README.md")


def main():
    """Run setup."""
    print("="*60)
    print("PDF DOCUMENT QUERY SYSTEM - SETUP")
    print("="*60 + "\n")
    
    # Create directories
    create_directories()
    
    # Create .env file
    create_env_file()
    
    # Check dependencies
    if not check_dependencies():
        print("\n⚠ Please install dependencies first:")
        print("   pip install -r requirements.txt")
        return
    
    # Download embedding model
    download_embedding_model()
    
    # Print next steps
    print_next_steps()


if __name__ == "__main__":
    main()
