"""
config/manifest.py
File path and category mappings for the RAG pipeline.
"""
from pathlib import Path

# Root directory - auto-detected
ROOT_DIR = Path(__file__).parent.parent  # This goes up from config to backend
DATA_DIR = ROOT_DIR / "data"  # Now points to backend/data

# Category mappings for folders — MUST match the exact folder names under
# backend/data/raw_store/, including the "06_Aduit" typo (do NOT "fix" the
# spelling here unless you also rename the folder on disk to match).
CATEGORY_MAPPINGS = {
    "01_Core_Acts": "core_acts",
    "02_Model_ByeLaws": "model_byelaws",
    "03_Redevelopment": "redevelopment",
    "04_Demed_Conveyance": "demed_conveyance",
    "05_Society_Governance": "society_governance",
    "06_Aduit": "audit",
    "07_Policies": "policies",
}


def get_category(folder_name: str) -> str:
    """Get category from folder name, with fallback."""
    return CATEGORY_MAPPINGS.get(folder_name, "uncategorized")