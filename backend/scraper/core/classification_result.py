"""
Classification Result - Immutable result object.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ClassificationResult:
    """
    Result of document classification.
    
    Attributes:
        category: The classified category (e.g., "Acts", "Rules")
        confidence: Confidence score between 0.0 and 1.0
        reason: Human-readable reason for classification
        matched_keywords: List of keywords that matched
        fallback: Whether this is a fallback classification
    """
    category: str
    confidence: float
    reason: str
    matched_keywords: List[str] = None
    fallback: bool = False
    
    def __post_init__(self):
        if self.matched_keywords is None:
            object.__setattr__(self, 'matched_keywords', [])
    
    def is_confident(self, threshold: float = 0.5) -> bool:
        """Check if confidence meets threshold."""
        return self.confidence >= threshold
    
    def to_dict(self) -> dict:
        """Convert to dictionary for metadata storage."""
        return {
            "classified_category": self.category,
            "classification_confidence": self.confidence,
            "classification_reason": self.reason,
            "matched_keywords": ",".join(self.matched_keywords) if self.matched_keywords else "",
        }