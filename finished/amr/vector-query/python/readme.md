# Azure Managed Redis Vector Storage & Search Exercise

This exercise demonstrates how to build a Python console application for storing and querying vector embeddings in Azure Managed Redis. You'll learn how to work with vector data structures, perform similarity searches, and manage vector metadata.

## Learning Objectives

By completing this exercise, you will:

- Connect to Azure Managed Redis using the redis-py library
- Store vector embeddings and associated metadata in Redis
- Retrieve vectors and their metadata from Redis
- Implement cosine similarity search to find semantically similar vectors
- Build an interactive console application for vector operations
- Understand practical applications of vector storage for recommendation systems and semantic search

## Prerequisites

Before you start this exercise, you need:

- An Azure subscription. If you don't already have one, you can [sign up for one](https://azure.microsoft.com/).
- [Visual Studio Code](https://code.visualstudio.com/) on one of the [supported platforms](https://code.visualstudio.com/docs/supporting/requirements#_platforms).
- [Python 3.12](https://www.python.org/downloads/) or greater.
- The latest version of the [Azure CLI](/cli/azure/install-azure-cli?view=azure-cli-latest).
- The Azure CLI **redisenterprise** extension. You can install it by running `az extension add --name redisenterprise`.

## Exercise Overview

This exercise guides you through:

1. **Download and Setup**: Get the starter files and configure your Python environment
2. **Deploy Azure Managed Redis**: Use deployment scripts to create an Azure Managed Redis resource
3. **Complete the Application**: Add code to implement vector storage and search functionality
4. **Run the Application**: Use the interactive console menu to test vector operations

## Application Features

The completed console application includes:

### Vector Storage Operations
- **Store vectors**: Save vector embeddings with optional metadata
- **Retrieve vectors**: Fetch stored vectors and their associated information
- **List vectors**: View all stored vectors in Redis

### Vector Search Operations
- **Similarity search**: Find the most similar vectors to a query vector using cosine similarity
- **Configurable results**: Return top-k similar vectors

### Data Management
- **Load sample data**: Pre-populate Redis with sample product vectors for testing
- **Delete vectors**: Remove individual vectors from storage
- **Clear all vectors**: Remove all vector data

### Menu-Driven Interface
An easy-to-use console interface with numbered options for all operations

## Key Concepts

### Vector Embeddings
Vector embeddings are numerical representations of data in multi-dimensional space. They enable semantic similarity comparisons and are commonly used for:
- Recommendation systems
- Semantic search
- Content similarity matching
- Machine learning applications

### Cosine Similarity
The application uses cosine similarity to compare vectors. This metric measures the angle between vectors, producing a score between -1 and 1:
- Score of 1: Vectors are identical
- Score of 0: Vectors are orthogonal (unrelated)
- Score of -1: Vectors are opposite

### Vector Metadata
Along with the vector itself, metadata (product ID, name, category, etc.) is stored to provide context for search results.

## File Structure

```
finished/amr/vector-query/python/
├── main.py                 # Main application with vector operations
├── requirements.txt        # Python package dependencies
├── pyproject.toml          # Project configuration
├── azdeploy.ps1           # PowerShell deployment script
├── azdeploy.sh            # Bash deployment script
├── .gitignore             # Git ignore rules
├── .python-version        # Python version specification
└── readme.md              # This file
```

## Running the Exercise

### Step 1: Configure the Python Environment

```bash
python -m venv .venv
```

Activate the virtual environment:
- **Windows**: `.venv\Scripts\activate`
- **macOS/Linux**: `source .venv/bin/activate`

### Step 2: Deploy Azure Managed Redis

Run the appropriate deployment script:

**PowerShell:**
```powershell
./azdeploy.ps1
```

**Bash:**
```bash
bash azdeploy.sh
```

Follow the menu prompts to:
1. Create the Azure Managed Redis resource
2. Check deployment status
3. Retrieve endpoint and access key

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Run the Application

```bash
python main.py
```

## Application Menu Options

1. **Load sample vectors** - Populates Redis with 5 sample product vectors
2. **Store a new vector** - Allows you to enter a custom vector and metadata
3. **Retrieve a vector** - Fetch and display a specific vector and its metadata
4. **Search for similar vectors** - Find vectors most similar to a query vector
5. **List all vectors** - View summary of all stored vectors
6. **Delete a vector** - Remove a specific vector
7. **Clear all vectors** - Remove all vectors from Redis
8. **Exit** - Close the application

## Example Workflow

1. Start the application and connect to Redis
2. Load sample vectors (Option 1)
3. List all vectors to see what was loaded (Option 5)
4. Retrieve a specific vector to examine its details (Option 3)
5. Search for similar vectors using the query vector from a sample product (Option 4)
6. View the search results and their similarity scores

## Code Sections

The application includes labeled code sections for educational purposes:

- **CONNECTION CODE SECTION**: Redis connection setup
- **VECTOR STORAGE CODE SECTION**: Vector storage with metadata
- **VECTOR RETRIEVAL CODE SECTION**: Vector fetching and display
- **SIMILARITY SEARCH CODE SECTION**: Cosine similarity calculation and search
- **DELETE CODE SECTION**: Vector deletion operations
- **LIST VECTORS CODE SECTION**: Vector enumeration
- **SAMPLE DATA CODE SECTION**: Sample vector generation

## Troubleshooting

### Connection Issues
- Verify the `.env` file contains valid `REDIS_HOST` and `REDIS_KEY` values
- Ensure your Azure Managed Redis resource shows a **Provisioning State** of **Succeeded**
- Check that public network access is enabled on the resource

### Environment Variable Issues
- Confirm the `.env` file exists in the project root
- Verify the variable names are exactly `REDIS_HOST` and `REDIS_KEY`
- Ensure there are no leading/trailing spaces in the values

### Python Package Issues
- Make sure you've activated the virtual environment
- Verify all packages are installed: `pip list`
- Try reinstalling: `pip install --upgrade -r requirements.txt`

### Vector Dimension Mismatch
- All vectors must have the same number of dimensions
- When searching, use a query vector with the same dimensions as stored vectors
- Sample vectors use 8 dimensions

## Next Steps

After completing this exercise, you can:

- Experiment with different vector dimensions
- Add real embeddings from machine learning models
- Integrate with OpenAI or other embedding APIs
- Build recommendation systems on top of vector search
- Implement filtering with metadata combined with vector search

## Cleaning Up Resources

To remove the Azure Managed Redis resource and avoid ongoing charges:

```bash
az group delete --name rg-exercises --yes
```

## Additional Resources

- [Azure Managed Redis Documentation](https://learn.microsoft.com/azure/cosmos-db/redis/)
- [redis-py Documentation](https://redis-py.readthedocs.io/)
- [Vector Search in Redis](https://redis.io/docs/stack/search/reference/)
- [Cosine Similarity](https://en.wikipedia.org/wiki/Cosine_similarity)
