"""Local retrieval: callers depend only on Retriever, QueryContext, EvidenceBundle."""

from .hybrid import HybridRetriever, QueryContext, Retriever

__all__ = ["HybridRetriever", "QueryContext", "Retriever"]
