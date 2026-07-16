"""
Folder Mapper - Maps S3 categories to your expected folder structure
Maps: Acts -> 01_Core_Acts, Rules -> 02_Model_ByeLaws, etc.
Without changing your existing manifest.py or batch_ingest.py
"""

# Mapping from S3 folder names to your expected folder names
S3_TO_LOCAL_FOLDER_MAP = {
    "Acts": "01_Core_Acts",
    "Rules": "02_Model_ByeLaws",
    "Government_Resolutions": "05_Society_Governance",
    "Model_ByeLaws": "02_Model_ByeLaws",
    "Notifications": "05_Society_Governance",
    "Publications": "05_Society_Governance",
    "Finance": "07_Policies",
    "Minutes": "05_Society_Governance",
    "Government_Resolution": "05_Society_Governance",
    "Redevelopment": "03_Redevelopment",
    "Deemed_Conveyance": "04_Demed_Conveyance",
    "Audit": "06_Aduit",  # Note: Keeping your typo
    "Policies": "07_Policies",
    "Model_Bye_Laws": "02_Model_ByeLaws",
    "Bye_Laws": "02_Model_ByeLaws",
}

def map_s3_to_local(s3_category: str) -> str:
    """Map S3 folder name to your expected local folder name"""
    return S3_TO_LOCAL_FOLDER_MAP.get(s3_category, "01_Core_Acts")

def get_all_expected_folders() -> list:
    """Get all expected folder names from your manifest"""
    from config.manifest import CATEGORY_MAPPINGS
    return list(CATEGORY_MAPPINGS.keys())

if __name__ == "__main__":
    print("S3 to Local Folder Mapping:")
    for s3, local in sorted(S3_TO_LOCAL_FOLDER_MAP.items()):
        print(f"  {s3} -> {local}")
