# llm_module/retriever.py

import math
import re

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
    """
    Split text into chunks of chunk_size characters with overlap characters of overlap.
    Ensures splitting happens at whitespace/word boundaries to preserve word integrity.
    """
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:])
            break
            
        # Try to find a space near the end to split cleanly
        space_idx = text.rfind(" ", start, end)
        if space_idx > start + (chunk_size // 2):
            end = space_idx
            
        chunk = text[start:end].strip()
        if len(chunk) > 50:  # Avoid tiny fragment chunks
            chunks.append(chunk)
            
        start = end - overlap
        if start >= end:
            start = end + 1
            
    return chunks


class BM25Retriever:
    """
    A pure-Python, zero-dependency implementation of the Okapi BM25 retrieval model.
    Perfect for sub-document searches within a single financial document.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = []
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_lens = []
        self.doc_freqs = {}
        self.term_freqs = []
        
    def _tokenize(self, text: str) -> list:
        # Simple word tokenization (lowercase, alphanumeric words)
        return re.findall(r"\b\w+\b", text.lower())
        
    def fit(self, documents: list):
        """Index a list of documents (chunks) and compute corpus-wide frequencies."""
        self.documents = documents
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            return
            
        self.doc_lens = []
        self.term_freqs = []
        self.doc_freqs = {}
        
        total_len = 0
        for doc in documents:
            tokens = self._tokenize(doc)
            doc_len = len(tokens)
            self.doc_lens.append(doc_len)
            total_len += doc_len
            
            # Count terms in this document
            tfs = {}
            for token in tokens:
                tfs[token] = tfs.get(token, 0) + 1
            self.term_freqs.append(tfs)
            
            # Increment document frequency for each unique term in this doc
            for token in tfs.keys():
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1
                
        self.avg_doc_len = total_len / self.corpus_size if self.corpus_size > 0 else 0.0
        
    def _idf(self, term: str) -> float:
        df = self.doc_freqs.get(term, 0)
        # Okapi BM25 IDF formula with smoothing to avoid division by zero or negative values
        return math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)
        
    def search(self, query: str, top_n: int = 3) -> list:
        """Search the indexed chunks for the query, returning top_n results."""
        if self.corpus_size == 0 or not query:
            return []
            
        query_tokens = self._tokenize(query)
        scores = []
        
        for idx in range(self.corpus_size):
            score = 0.0
            doc_len = self.doc_lens[idx]
            tfs = self.term_freqs[idx]
            
            for token in query_tokens:
                if token in tfs:
                    tf = tfs[token]
                    idf = self._idf(token)
                    
                    # Okapi BM25 formula
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                    score += idf * (numerator / denominator)
                    
            scores.append((score, idx))
            
        # Sort descending by score
        scores.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for score, idx in scores[:top_n]:
            results.append({
                "text": self.documents[idx],
                "index": idx,
                "score": score
            })
        return results
