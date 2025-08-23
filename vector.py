# vector.py - Clean, unified approach with smart caching
import os
import json
import hashlib
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
LOCAL_MODEL_PATH = "./localmodel"

# Use /tmp for writable storage on HF Spaces
CHROMA_DB_PATH = "/tmp/chroma_store" if os.path.exists("/tmp") else "./chroma_store"
CACHE_FILE = "/tmp/vector_cache.json" if os.path.exists("/tmp") else "./vector_cache.json"

# Global variable to store the initialized vector store
_global_vector_store = None

def fetch_data_from_db():
    """Fetches data from the database and returns as DataFrame."""
    if not DB_URL:
        raise ValueError("DATABASE_URL not found in environment variables")

    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        result = session.execute(text("SELECT id, question, answer FROM questions_and_answers"))
        rows = result.mappings().all()
        return pd.DataFrame(rows)
    finally:
        session.close()

def get_data_hash(df):
    """Create hash of data to detect changes"""
    data_string = df.to_string()
    return hashlib.md5(data_string.encode()).hexdigest()

def save_cache_info(data_hash, doc_count, timestamp):
    """Save cache metadata"""
    cache_info = {
        "data_hash": data_hash,
        "doc_count": doc_count,
        "timestamp": timestamp,
        "cache_valid": True
    }
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_info, f)
        print(f"Cache info saved to {CACHE_FILE}")
    except Exception as e:
        print(f"Warning: Could not save cache info to {CACHE_FILE}: {e}")

def load_cache_info():
    """Load cache metadata"""
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not load cache info: {e}")
        return None

def should_rebuild_cache(df):
    """Check if we need to rebuild the vector store"""
    current_hash = get_data_hash(df)
    cache_info = load_cache_info()
    
    if not cache_info:
        print("No cache info found - building fresh")
        return True
    
    if not os.path.exists(CHROMA_DB_PATH):
        print("No cached vector store found - building fresh") 
        return True
    
    if cache_info.get("data_hash") != current_hash:
        print("Data changed - rebuilding vector store")
        return True
        
    if len(df) != cache_info.get("doc_count", 0):
        print("Document count changed - rebuilding")
        return True
    
    print("Cache is valid - using existing vector store")
    return False

# Keep the old function name for backward compatibility
def init_vector_store(df: pd.DataFrame, db_location=None):
    """Initialize vector store - backward compatibility wrapper"""
    return init_vector_store_smart(df)

def init_vector_store_smart(df: pd.DataFrame):
    """Smart initialization - use cache when possible"""
    
    embeddings = HuggingFaceEndpointEmbeddings(
        model='sentence-transformers/all-mpnet-base-v2', 
        huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN"), 
        task='feature-extraction'
    )
    
    # Check if we can reuse existing store
    if not should_rebuild_cache(df):
        try:
            # Try to load existing persistent store
            store = Chroma(
                collection_name="questions_and_answers",
                persist_directory=CHROMA_DB_PATH,
                embedding_function=embeddings
            )
            
            # Verify it works
            existing_data = store.get()
            existing_count = len(existing_data["ids"]) if existing_data["ids"] else 0
            if existing_count > 0:
                print(f"Loaded existing vector store with {existing_count} documents")
                return store
            else:
                print("Existing store is empty - rebuilding")
        except Exception as e:
            print(f"Failed to load cached store: {e} - rebuilding")
    
    # Build fresh store
    print("Building new vector store...")
    
    # Try persistent first, fallback to in-memory
    try:
        store = Chroma(
            collection_name="questions_and_answers",
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings
        )
        print("Using persistent storage")
    except Exception as e:
        print(f"Persistent storage failed ({e}) - using in-memory")
        store = Chroma(
            collection_name="questions_and_answers", 
            embedding_function=embeddings
        )
    
    # Add documents if we have data
    if not df.empty:
        documents = []
        ids = []
        for _, row in df.iterrows():
            doc = Document(
                page_content=f"{row['question']} {row['answer']}",
                metadata={"id": row["id"]}
            )
            documents.append(doc)
            ids.append(str(row["id"]))
        
        if documents:
            store.add_documents(documents=documents, ids=ids)
            print(f"Added {len(documents)} documents to vector store")
            
            # Save cache info only if using persistent storage
            try:
                data_hash = get_data_hash(df)
                save_cache_info(data_hash, len(documents), datetime.now().isoformat())
            except Exception as e:
                print(f"Warning: Could not save cache info: {e}")
    
    return store

def get_vector_store():
    """Get the global vector store instance - use this in your routes"""
    global _global_vector_store
    if _global_vector_store is None:
        print("Warning: Vector store not initialized, creating new instance...")
        df = fetch_data_from_db()
        _global_vector_store = init_vector_store_smart(df)
    return _global_vector_store

def set_global_vector_store(store):
    """Set the global vector store - call this from main()"""
    global _global_vector_store
    _global_vector_store = store

def sync_documents(df: pd.DataFrame, store: Chroma):
    """Sync DB rows into vector store: add new rows, remove deleted ones."""
    try:
        existing_data = store.get()
        existing_ids = set(existing_data["ids"]) if existing_data["ids"] else set()
    except Exception as e:
        print(f"Warning: Could not get existing IDs: {e}")
        existing_ids = set()

    db_ids = set(df["id"].astype(str).tolist())

    new_docs, new_ids = [], []
    for _, row in df.iterrows():
        row_id = str(row["id"])
        if row_id not in existing_ids:
            doc = Document(
                page_content=f"{row['question']} {row['answer']}",
                metadata={"id": row["id"]}
            )
            new_docs.append(doc)
            new_ids.append(row_id)

    if new_docs:
        print(f"Adding {len(new_docs)} new documents to Chroma...")
        try:
            store.add_documents(documents=new_docs, ids=new_ids)
        except Exception as e:
            print(f"Error adding documents: {e}")

    ids_to_delete = existing_ids - db_ids
    if ids_to_delete:
        print(f"Deleting {len(ids_to_delete)} documents from Chroma...")
        try:
            store.delete(ids=list(ids_to_delete))
        except Exception as e:
            print(f"Error deleting documents: {e}")

    if not new_docs and not ids_to_delete:
        print("No changes detected. Vector store is up-to-date.")

def retrieve(query: str, store: Chroma):
    """Retrieve documents from vector store"""
    print("Starting retrieval")
    try:
        retriever = store.as_retriever(
            search_type="mmr",
            search_kwargs={'fetch_k': 15, 'k': 6, 'lambda_mult': 0.5}
        )
        return retriever.invoke(query)
    except Exception as e:
        print(f"Error during retrieval: {e}")
        # Fallback to simple similarity search
        try:
            return store.similarity_search(query, k=6)
        except Exception as e2:
            print(f"Fallback retrieval also failed: {e2}")
            return []

def run_sync():
    """Sync vector store with database"""
    try:
        df = fetch_data_from_db()
        sync_store = get_vector_store()
        sync_documents(df, store=sync_store)
        return {"message": "done", "status": 1}
    except Exception as e:
        return {"message": str(e), "status": 0}

def main():
    """Initialize vector store with smart caching"""
    try:
        print("=== Initializing vector store with smart caching ===")
        df = fetch_data_from_db()
        print(f"Fetched {len(df)} records from database")
        
        # Use smart initialization
        store = init_vector_store_smart(df)
        set_global_vector_store(store)
        
        print("=== Vector store ready! ===")
        
    except Exception as e:
        print(f"ERROR during vector store initialization: {e}")
        # Don't raise - let the app start but log the error
        print("App will continue but vector store may not work properly")

# Initialize vector store when module is imported (runs on HF Spaces)
if __name__ != '__main__':  # Only auto-init when imported, not when run directly
    try:
        print("=== Auto-initializing vector store on module import ===")
        main()
    except Exception as e:
        print(f"Failed to auto-initialize vector store: {e}")
        print("Vector store will be initialized on first request")

# For testing - only run when called directly
if __name__ == '__main__':
    main()