# Complete Example: Using the Topic-Based PDF Query System

This guide walks through a complete example of setting up and using the PDF document query system with topic-based organization.

## Scenario

You're a data scientist who wants to organize and search through your collection of technical PDFs covering:
- Machine Learning papers and tutorials
- Python programming guides
- Data Science methodologies
- Statistics textbooks

## Step 1: Organize Your PDFs

Create a folder structure that reflects your topics:

```bash
cd doc-to-ai
mkdir -p pdfs/Machine_Learning
mkdir -p pdfs/Python_Programming
mkdir -p pdfs/Data_Science
mkdir -p pdfs/Statistics
```

Move your PDFs into the appropriate folders:

```
pdfs/
├── Machine_Learning/
│   ├── neural_networks_intro.pdf
│   ├── deep_learning_basics.pdf
│   ├── cnn_architectures.pdf
│   └── transformers_explained.pdf
├── Python_Programming/
│   ├── python_basics.pdf
│   ├── advanced_python.pdf
│   ├── pandas_tutorial.pdf
│   └── numpy_guide.pdf
├── Data_Science/
│   ├── data_analysis_workflow.pdf
│   ├── feature_engineering.pdf
│   └── model_evaluation.pdf
└── Statistics/
    ├── probability_theory.pdf
    ├── statistical_inference.pdf
    └── hypothesis_testing.pdf
```

## Step 2: Install and Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run setup
python setup.py
```

Expected output:
```
====================================
PDF DOCUMENT QUERY SYSTEM - SETUP
====================================

Creating directories...
  ✓ C:\...\doc-to-ai\chroma_db
  ✓ C:\...\doc-to-ai\pdf_cache
  ✓ C:\...\doc-to-ai\pdfs

Creating .env file...
  ✓ .env created from .env.example

Checking dependencies...
  ✓ chromadb
  ✓ sentence_transformers
  ✓ fitz
  ✓ mcp

Downloading embedding model...
  Downloading all-MiniLM-L6-v2...
  ✓ Model downloaded and cached

====================================
SETUP COMPLETE!
====================================
```

## Step 3: Ingest PDFs

```bash
python ingest_pdfs.py --pdf-dir ./pdfs
```

Expected output:
```
Found 14 PDF files
Base directory: C:\...\doc-to-ai\pdfs

Detected topics: Data_Science, Machine_Learning, Python_Programming, Statistics

[1/14] Processing: neural_networks_intro.pdf
  Topic: Machine_Learning
Loading embedding model: all-MiniLM-L6-v2
Generating embeddings for 35 chunks...
  ✓ Added 35 chunks

[2/14] Processing: deep_learning_basics.pdf
  Topic: Machine_Learning
Generating embeddings for 42 chunks...
  ✓ Added 42 chunks

[3/14] Processing: cnn_architectures.pdf
  Topic: Machine_Learning
Generating embeddings for 28 chunks...
  ✓ Added 28 chunks

... (processing continues)

============================================================
INGESTION SUMMARY
============================================================
Total PDFs processed: 14
Successful: 14
Failed: 0
Total chunks added: 467

Documents per topic:
  Data_Science: 3 documents, 98 chunks
  Machine_Learning: 4 documents, 145 chunks
  Python_Programming: 4 documents, 132 chunks
  Statistics: 3 documents, 92 chunks

Vector store stats:
  Total chunks in store: 467
  Total documents: 14
  Total topics: 4
  Topics: Data_Science, Machine_Learning, Python_Programming, Statistics
```

## Step 4: Test the System

```bash
python test_system.py
```

Expected output:
```
============================================================
PDF DOCUMENT QUERY SYSTEM - TEST SUITE
============================================================

============================================================
Testing PDF Processor
============================================================
✓ PDFProcessor initialized

⚠ No test.pdf found. Place a test PDF in the root directory to test extraction.

============================================================
Testing Vector Store
============================================================
✓ VectorStore initialized

Current stats:
  Total chunks: 467
  Documents: 14

Documents in store:
  - cnn_architectures.pdf (Machine_Learning)
  - data_analysis_workflow.pdf (Data_Science)
  - deep_learning_basics.pdf (Machine_Learning)
  ... (more documents)

Testing search...
✓ Search returned 3 results

Top result preview:
  File: neural_networks_intro.pdf
  Page: 5
  Text: Neural networks are computational models inspired by...

============================================================
TEST SUMMARY
============================================================
✓ PASS: PDF Processor
✓ PASS: Vector Store
✓ PASS: Integration

Passed: 3/3

🎉 All tests passed!
```

## Step 5: Configure Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "doc-to-ai": {
      "command": "python",
      "args": ["C:/D/code/ai-tools/Claude-Controlled/doc-to-ai/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop.

## Step 6: Use with Claude

### Example Conversation 1: Discovery

**You:** "What documents do you have access to?"

**Claude (using `list_documents`):**
```
I have access to 14 PDF documents organized into 4 topics:

📁 Topic: Data_Science (3 documents)
  • data_analysis_workflow.pdf
  • feature_engineering.pdf
  • model_evaluation.pdf

📁 Topic: Machine_Learning (4 documents)
  • cnn_architectures.pdf
  • deep_learning_basics.pdf
  • neural_networks_intro.pdf
  • transformers_explained.pdf

📁 Topic: Python_Programming (4 documents)
  • advanced_python.pdf
  • numpy_guide.pdf
  • pandas_tutorial.pdf
  • python_basics.pdf

📁 Topic: Statistics (3 documents)
  • hypothesis_testing.pdf
  • probability_theory.pdf
  • statistical_inference.pdf
```

### Example Conversation 2: General Search

**You:** "Search for information about convolutional neural networks"

**Claude (using `search_documents`):**
```
Found 5 relevant chunks for query: 'convolutional neural networks'

--- Result 1 ---
Topic: Machine_Learning
Source: cnn_architectures.pdf (Page 3)
Relevance: 94.2%

Content:
Convolutional Neural Networks (CNNs) are specialized deep learning 
architectures designed for processing grid-like data, particularly images. 
The key innovation is the convolutional layer, which applies filters to 
detect local patterns such as edges, textures, and shapes...

--- Result 2 ---
Topic: Machine_Learning
Source: deep_learning_basics.pdf (Page 12)
Relevance: 89.7%

Content:
CNNs revolutionized computer vision by learning hierarchical features 
automatically. Unlike traditional methods, CNNs don't require manual 
feature engineering. The architecture typically consists of convolutional 
layers, pooling layers, and fully connected layers...

... (more results)
```

### Example Conversation 3: Topic-Specific Search

**You:** "Find information about dataframes in the Python_Programming topic"

**Claude (using `search_documents` with topic filter):**
```
Found 3 relevant chunks for query: 'dataframes' (filtered to topic: 'Python_Programming')

--- Result 1 ---
Topic: Python_Programming
Source: pandas_tutorial.pdf (Page 8)
Relevance: 96.5%

Content:
Pandas DataFrames are the central data structure for data manipulation in 
Python. A DataFrame is a two-dimensional labeled data structure with columns 
of potentially different types. You can think of it as a spreadsheet or SQL 
table...

--- Result 2 ---
Topic: Python_Programming
Source: pandas_tutorial.pdf (Page 15)
Relevance: 91.3%

Content:
Creating DataFrames can be done in multiple ways. The most common methods 
include: from dictionaries, from lists, from numpy arrays, or by reading 
external files. Here's an example: df = pd.DataFrame({'A': [1,2,3], 
'B': [4,5,6]})...

--- Result 3 ---
Topic: Python_Programming
Source: numpy_guide.pdf (Page 22)
Relevance: 85.8%

Content:
While NumPy arrays are the foundation, Pandas DataFrames build on this by 
adding labeled axes and more sophisticated data manipulation capabilities. 
You can convert between NumPy arrays and DataFrames easily using df.values 
or pd.DataFrame(array)...
```

### Example Conversation 4: Cross-Topic Comparison

**You:** "Compare what the Machine Learning and Statistics topics say about hypothesis testing"

**Claude (using multiple `search_documents` calls):**

```
I'll search both topics for information about hypothesis testing.

[Searches Machine_Learning topic...]
[Searches Statistics topic...]

Based on the documents, here's how each topic approaches hypothesis testing:

**Statistics Perspective:**
The Statistics documents provide the formal mathematical foundation. From 
hypothesis_testing.pdf, they define hypothesis testing as a statistical method 
for making inferences about population parameters. The focus is on p-values, 
significance levels, Type I and Type II errors, and the classical Neyman-Pearson 
framework.

**Machine Learning Perspective:**
The Machine Learning documents take a more practical, computational approach. 
From model_evaluation.pdf, they discuss hypothesis testing in the context of 
comparing model performance, using techniques like cross-validation and 
statistical tests to determine if one model significantly outperforms another.

Key differences:
1. Statistics: Formal, theoretical, focuses on inference
2. Machine Learning: Applied, focuses on model selection and validation

Both emphasize the importance of avoiding false conclusions, but the ML 
documents are more concerned with overfitting and generalization, while 
Statistics documents focus on proper experimental design and sampling.
```

### Example Conversation 5: List Available Topics

**You:** "What topics are available?"

**Claude (using `list_topics`):**
```
Available topics (4):

  📁 Data_Science: 3 documents
  📁 Machine_Learning: 4 documents
  📁 Python_Programming: 4 documents
  📁 Statistics: 3 documents
```

### Example Conversation 6: Get Statistics

**You:** "Give me detailed statistics about the document collection"

**Claude (using `get_document_stats`):**
```
Document Collection Statistics:

Total chunks: 467
Total documents: 14
Total topics: 4
Collection: pdf_documents

Documents per topic:
  📁 Data_Science: 3 documents
  📁 Machine_Learning: 4 documents
  📁 Python_Programming: 4 documents
  📁 Statistics: 3 documents
```

## Step 7: Adding More Documents

When you get new PDFs:

```bash
# Add new PDF to existing topic
cp new_paper.pdf pdfs/Machine_Learning/

# Or create a new topic
mkdir pdfs/Deep_Learning
cp papers/*.pdf pdfs/Deep_Learning/

# Re-run ingestion (only processes new files if not using --reset)
python ingest_pdfs.py --pdf-dir ./pdfs
```

Output:
```
Found 16 PDF files (2 new)
Detected topics: Data_Science, Deep_Learning, Machine_Learning, Python_Programming, Statistics

[15/16] Processing: new_paper.pdf
  Topic: Machine_Learning
  ✓ Added 38 chunks

[16/16] Processing: gan_tutorial.pdf
  Topic: Deep_Learning
  ✓ Added 52 chunks

Total chunks added: 90
```

## Advanced Usage

### Searching Multiple Topics

**You:** "Find information about neural networks but only in Machine_Learning and Deep_Learning topics"

**Claude:** Would search each topic separately and combine results.

### Document-Specific Queries

**You:** "What does cnn_architectures.pdf say about ResNet?"

**Claude:** Would search all results and filter to those from that specific document.

### Comparative Analysis

**You:** "Create a comparison table of the different Python libraries covered in the Python_Programming documents"

**Claude:** Would extract information from multiple documents in that topic and organize it.

## Tips for Best Results

1. **Organize logically**: Use clear, descriptive folder names
2. **Keep topics focused**: Don't mix unrelated content in one topic
3. **Use consistent naming**: Stick to underscores, avoid spaces
4. **Regular updates**: Re-ingest when you add new PDFs
5. **Test searches**: Use specific queries to verify content is findable

## Troubleshooting Common Issues

### Issue: Search returns too many irrelevant results

**Solution:** Use topic filtering
```
Instead of: "search for optimization"
Try: "search for optimization in the Machine_Learning topic"
```

### Issue: Can't find document you just added

**Solution:** Make sure you re-ingested
```bash
python ingest_pdfs.py --pdf-dir ./pdfs
```

### Issue: Topics not showing up correctly

**Solution:** Check folder structure
```bash
# Verify structure
ls -R pdfs/

# Should show topic folders with PDFs inside
```

## Next Steps

- Read **TOPICS.md** for advanced topic configuration
- Check **README.md** for full feature documentation
- Experiment with different query types
- Add more documents and topics as needed

## Summary

This example demonstrated:
✓ Organizing PDFs by topic
✓ Ingesting documents into the vector store
✓ Testing the system
✓ Connecting to Claude Desktop
✓ Querying documents through Claude
✓ Using topic filters for targeted searches
✓ Adding new documents

You now have a fully functional topic-based PDF query system integrated with Claude!
