"""
Category Classifier with Priority-Based Matching

Uses external configuration from config/category_rules.json.
Priority-based matching prevents misclassification.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.classification_result import ClassificationResult


class CategoryClassifier:
    """
    Classifies documents into legal topic categories.
    
    Priority system (highest to lowest):
    1. document_type
    2. category (connector-provided)
    3. title keywords (with priority groups)
    4. department
    5. source_website (fallback)
    
    Configuration:
        config/category_rules.json
    """

    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Load category rules from external file
        rules_file = config.get("CATEGORY_RULES_FILE", "config/category_rules.json")
        self.category_rules = self._load_rules(rules_file)
        
        # Category priority order (higher = more specific)
        self.category_priority = config.get("CATEGORY_PRIORITY", [
            "Model_ByeLaws",
            "Acts",
            "Rules",
            "Redevelopment",
            "Deemed_Conveyance",
            "Audit",
            "Election",
            "Committee",
            "AGM",
            "Annual_Return",
            "Circulars",
            "Notifications",
            "Government_Resolutions",
            "Housing",
            "Land",
            "MHADA",
            "RERA",
            "Rent_Control",
            "Slum",
            "Minutes",
            "Policies",
            "Guidelines",
            "Manuals",
            "Publications",
            "Finance",
            "Forms",
        ])
        
        # Confidence threshold from config
        self.min_confidence = config.get("MIN_CONFIDENCE", 0.3)

    def _load_rules(self, rules_file: str) -> Dict[str, List[str]]:
        """Load category rules from JSON file."""
        try:
            filepath = Path(rules_file)
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                    self.logger.info(f"Loaded {len(rules)} categories from {rules_file}")
                    return rules
            else:
                self.logger.warning(f"Rules file not found: {rules_file}")
                return {}
        except Exception as e:
            self.logger.error(f"Failed to load rules: {e}")
            return {}

    def classify(self, document: Dict) -> ClassificationResult:
        """
        Classify document using priority-based matching.
        
        Returns:
            ClassificationResult with category, confidence, and reason.
        """
        # Build search text from available fields
        title = document.get("title", "")
        category = document.get("category", "")
        department = document.get("department", "")
        doc_type = document.get("document_type", "")
        source_website = document.get("source_website", "")
        
        # Priority 1: document_type
        if doc_type:
            result = self._match_field(doc_type, "document_type")
            if result:
                return self._create_result(result, 0.95, f"Matched document_type: {doc_type}")
        
        # Priority 2: category (connector-provided)
        if category:
            result = self._match_field(category, "category")
            if result:
                return self._create_result(result, 0.85, f"Matched connector category: {category}")
        
        # Priority 3: title keywords (with priority order)
        if title:
            result = self._match_title(title)
            if result:
                return result
        
        # Priority 4: department
        if department:
            result = self._match_field(department, "department")
            if result:
                return self._create_result(result, 0.5, f"Matched department: {department}")
        
        # Priority 5: source_website (fallback)
        if source_website:
            result = self._match_field(source_website, "source_website")
            if result:
                return self._create_result(result, 0.3, f"Matched source: {source_website}")
        
        # No match - Unknown
        return self._create_result("Unknown", 0.0, "No matching category found", fallback=True)

    def _match_field(self, value: str, field_type: str) -> Optional[str]:
        """Match a field value against category rules."""
        value_lower = value.lower()
        
        # Check categories in priority order
        for category in self.category_priority:
            rules = self.category_rules.get(category, {})
            keywords = rules.get(field_type, [])
            for keyword in keywords:
                if keyword.lower() in value_lower:
                    return category
        
        return None

    def _match_title(self, title: str) -> Optional[ClassificationResult]:
        """Match title against keywords with priority."""
        title_lower = title.lower()
        matched = []
        
        # Check each category in priority order
        for category in self.category_priority:
            rules = self.category_rules.get(category, {})
            keywords = rules.get("title_keywords", [])
            
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    matched.append((category, keyword))
            
            # If any match in this category, return it (priority order)
            if matched:
                # Use highest confidence based on number of matches
                confidence = min(0.7 + (len(matched) * 0.05), 0.95)
                reason = f"Matched keywords: {', '.join(k for _, k in matched[:3])}"
                return self._create_result(
                    matched[0][0],
                    confidence,
                    reason,
                    [k for _, k in matched]
                )
        
        return None

    def _create_result(
        self,
        category: str,
        confidence: float,
        reason: str,
        keywords: List[str] = None,
        fallback: bool = False
    ) -> ClassificationResult:
        """Create a ClassificationResult with logging."""
        result = ClassificationResult(
            category=category,
            confidence=confidence,
            reason=reason,
            matched_keywords=keywords or [],
            fallback=fallback
        )
        
        if fallback:
            self.logger.debug(f"Fallback: {reason}")
        else:
            self.logger.debug(f"Classified: {category} (conf: {confidence:.2f}) - {reason}")
        
        return result

    def get_category_for_download(self, document: Dict) -> str:
        """Get category for download folder (with confidence check)."""
        result = self.classify(document)
        
        # If confidence is too low, use Unknown
        if result.confidence < self.min_confidence and not result.fallback:
            self.logger.debug(f"Low confidence ({result.confidence:.2f}), using Unknown")
            return "Unknown"
        
        # Sanitize category name for filesystem
        return self._sanitize(result.category)

    def _sanitize(self, name: str) -> str:
        """Sanitize category name for filesystem use."""
        import re
        folder = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        folder = re.sub(r"_+", "_", folder)
        folder = folder.strip("_")
        return folder if folder else "Unknown"