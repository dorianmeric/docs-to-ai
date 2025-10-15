# Topic-Based Organization

## Overview

This system automatically organizes your PDF documents using a folder-based topic structure. Each folder name becomes a **topic tag** that helps categorize and filter your documents.

## How It Works

### Folder Structure → Topic Tags

```
your_pdfs/
├── Machine_Learning/        ← Topic: "Machine_Learning"
│   ├── neural_nets.pdf
│   └── deep_learning.pdf
├── Python/                   ← Topic: "Python"
│   ├── basics.pdf
│   └── advanced.pdf
└── Data_Science/            ← Topic: "Data_Science"
    └── statistics.pdf
```

When you ingest PDFs:
1. The script scans all subdirectories
2. Extracts the parent folder name as the topic
3. Tags all chunks from that PDF with the topic
4. Stores the topic in the vector database metadata

### Handling Duplicate Filenames

The topic system correctly handles PDFs with the same filename in different folders:

```
pdfs/
├── Machine_Learning/
│   └── introduction.pdf     ← Tagged as "Machine_Learning"
└── Python/
    └── introduction.pdf     ← Tagged as "Python"
```

Both files are stored separately with unique identifiers based on:
- Topic name
- Full file path
- Chunk position

## Benefits

### 1. Organized Search Results

Search results show the topic for each match:

```
--- Result 1 ---
Topic: Machine_Learning
Source: neural_networks.pdf (Page 5)
Relevance: 92.3%
Content: Deep learning models consist of...
```

### 2. Filtered Searches

Search within specific topics:

```python
# Search only in Machine Learning documents
results = search_documents(
    query="optimization algorithms",
    topic="Machine_Learning"
)
```

### 3. Better Context

Claude can understand document organization:
- "What Machine Learning documents do you have?"
- "Compare Python and Data Science approaches to the same problem"
- "Find information about neural networks in the Machine Learning topic"

## Configuration

### Enable/Disable Topic Extraction

Edit `config.py`:

```python
# Enable folder-based topics (default: True)
USE_FOLDER_AS_TOPIC = True

# Default topic for PDFs not in topic folders
DEFAULT_TOPIC = "uncategorized"
```

### Topic Naming Best Practices

1. **Use descriptive names**: `Machine_Learning` instead of `ML`
2. **Use underscores**: `Data_Science` instead of `Data Science` (avoids issues)
3. **Be consistent**: Decide on a naming convention and stick to it
4. **Avoid special characters**: Stick to letters, numbers, and underscores

Good examples:
- `Machine_Learning`
- `Python_Programming`
- `Data_Science`
- `Web_Development`
- `DevOps_Tools`

Avoid:
- `ML` (too short)
- `Data Science` (spaces can cause issues)
- `AI/ML` (special characters)
- `temp` or `misc` (not descriptive)

## MCP Tools Supporting Topics

### search_documents

Search with optional topic filter:

```json
{
  "query": "neural networks",
  "topic": "Machine_Learning",
  "max_results": 5
}
```

### list_documents

List all documents, optionally filtered by topic:

```json
{
  "topic": "Python_Programming"
}
```

Shows documents organized by topic:
```
📁 Topic: Python_Programming (3 documents)
  • basics.pdf
  • advanced.pdf
  • best_practices.pdf
```

### list_topics

Get all available topics:

```json
{}
```

Returns:
```
Available topics (3):
  📁 Data_Science: 4 documents
  📁 Machine_Learning: 6 documents
  📁 Python_Programming: 5 documents
```

### get_document_stats

View statistics including topic distribution:

```json
{}
```

Returns:
```
Document Collection Statistics:

Total chunks: 523
Total documents: 15
Total topics: 3
Collection: pdf_documents

Documents per topic:
  📁 Data_Science: 4 documents
  📁 Machine_Learning: 6 documents
  📁 Python_Programming: 5 documents
```

## Example Use Cases

### 1. Research Organization

```
research_papers/
├── Computer_Vision/
│   ├── object_detection.pdf
│   └── image_segmentation.pdf
├── NLP/
│   ├── transformers.pdf
│   └── sentiment_analysis.pdf
└── Reinforcement_Learning/
    └── policy_gradients.pdf
```

Ask Claude:
- "Summarize the Computer Vision research"
- "Compare NLP and Computer Vision approaches"
- "Find all mentions of neural networks across topics"

### 2. Course Materials

```
course_materials/
├── Week_1_Introduction/
│   └── syllabus.pdf
├── Week_2_Basics/
│   ├── lecture_notes.pdf
│   └── exercises.pdf
└── Week_3_Advanced/
    └── advanced_concepts.pdf
```

Ask Claude:
- "What topics are covered in Week 2?"
- "Find information about recursion"
- "Show me all exercises from the course"

### 3. Documentation Library

```
documentation/
├── API_Reference/
│   ├── rest_api.pdf
│   └── graphql.pdf
├── User_Guides/
│   └── getting_started.pdf
└── Architecture/
    └── system_design.pdf
```

Ask Claude:
- "Search the API Reference for authentication methods"
- "What does the User Guide say about installation?"
- "Find information about microservices in Architecture docs"

## Troubleshooting

### No topics detected

**Problem:** All PDFs are in the base directory, no subfolders.

**Solution:** Organize PDFs into topic folders:
```bash
mkdir pdfs/My_Topic
mv pdfs/*.pdf pdfs/My_Topic/
```

### Wrong topic assigned

**Problem:** PDF is in the wrong folder or folder name is incorrect.

**Solution:** 
1. Move the PDF to the correct folder
2. Re-run ingestion with `--reset`:
```bash
python ingest_pdfs.py --pdf-dir ./pdfs --reset
```

### Same filename, different content

**Problem:** Two PDFs with the same name in different topics.

**Solution:** This works automatically! The system uses the full path to distinguish them:
- `Machine_Learning/introduction.pdf` → Unique ID based on path + topic
- `Python/introduction.pdf` → Different unique ID

## Advanced: Custom Topic Logic

You can modify `pdf_processor.py` to implement custom topic extraction logic:

```python
def extract_topic_from_path(self, pdf_path: Path, base_dir: Optional[Path] = None) -> str:
    # Custom logic here
    # Example: Use multiple folder levels
    if len(pdf_path.parts) > 2:
        # Use both parent and grandparent: "ML/Neural_Networks"
        return f"{pdf_path.parent.parent.name}/{pdf_path.parent.name}"
    
    return pdf_path.parent.name
```

This allows for nested topic hierarchies like:
```
pdfs/
└── AI/
    ├── Machine_Learning/
    └── Computer_Vision/
```

Topic tags: `AI/Machine_Learning`, `AI/Computer_Vision`
