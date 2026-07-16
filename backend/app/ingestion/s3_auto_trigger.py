"""
AUTOMATIC S3 TRIGGER - Uses YOUR existing functions
- Polls S3 for new PDFs
- Downloads them to the correct folder structure that YOUR batch_ingest expects
- Calls YOUR batch_ingest.py (which calls YOUR vector_store.py)
- NO CHANGES to your diagnose_ocr.py, vector_store.py, batch_ingest.py, or manifest.py
"""

import os
import sys
import asyncio
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import YOUR existing modules (unchanged)
from app.services.batch_ingest import BatchIngestionService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("s3_auto_trigger")

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET_NAME', 'society-compliance-copilot')
S3_PREFIX = os.environ.get('S3_PREFIX', 'dataset')
DOWNLOAD_DIR = Path("./data/downloads")
RAW_STORE_DIR = Path("./data/raw_store")

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

class S3AutoTrigger:
    """Automatic trigger that uses YOUR existing batch_ingest.py"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
        self.bucket = S3_BUCKET
        self.prefix = S3_PREFIX
        
        # Create directories
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        RAW_STORE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create all expected folders from your manifest
        try:
            from config.manifest import CATEGORY_MAPPINGS
            for folder in CATEGORY_MAPPINGS.keys():
                (RAW_STORE_DIR / folder).mkdir(parents=True, exist_ok=True)
            logger.info(f"{Colors.CYAN}📁 Created folders from manifest: {list(CATEGORY_MAPPINGS.keys())}{Colors.RESET}")
        except:
            # Fallback folders
            default_folders = [
                "01_Core_Acts", "02_Model_ByeLaws", "03_Redevelopment",
                "04_Demed_Conveyance", "05_Society_Governance", "06_Aduit", "07_Policies"
            ]
            for folder in default_folders:
                (RAW_STORE_DIR / folder).mkdir(parents=True, exist_ok=True)
            logger.info(f"{Colors.CYAN}📁 Created default folders: {default_folders}{Colors.RESET}")
        
        logger.info(f"{Colors.CYAN}📁 S3 Auto Trigger initialized{Colors.RESET}")
        logger.info(f"   Using YOUR existing batch_ingest.py from app/services/")
        logger.info(f"   S3 Bucket: {self.bucket}")
        logger.info(f"   Raw Store: {RAW_STORE_DIR}")
    
    def list_pdfs(self) -> List[Dict]:
        """List all PDFs in S3"""
        try:
            pdfs = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{self.prefix}/"):
                for obj in page.get('Contents', []):
                    if obj['Key'].lower().endswith('.pdf'):
                        pdfs.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified']
                        })
            return pdfs
        except ClientError as e:
            logger.error(f"{Colors.RED}❌ Error listing S3 files: {e}{Colors.RESET}")
            return []
    
    def get_s3_category(self, s3_key: str) -> str:
        """Extract category from S3 key"""
        parts = s3_key.split('/')
        return parts[1] if len(parts) >= 3 else "Acts"
    
    def map_s3_to_local(self, s3_category: str) -> str:
        """Map S3 folder to your expected local folder"""
        mapping = {
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
            "Audit": "06_Aduit",
            "Policies": "07_Policies",
            "Model_Bye_Laws": "02_Model_ByeLaws",
            "Bye_Laws": "02_Model_ByeLaws",
        }
        return mapping.get(s3_category, "01_Core_Acts")
    
    def download_and_organize(self, s3_key: str) -> Optional[Path]:
        """Download file and place it in the correct raw_store folder"""
        try:
            # Get S3 category and map to local folder
            s3_category = self.get_s3_category(s3_key)
            local_folder = self.map_s3_to_local(s3_category)
            
            # Create target path in raw_store
            filename = s3_key.split('/')[-1]
            target_path = RAW_STORE_DIR / local_folder / filename
            
            # Check if already exists
            if target_path.exists():
                logger.info(f"{Colors.YELLOW}⏭️  Already exists: {filename}{Colors.RESET}")
                return target_path
            
            # Download to temp location first
            temp_path = DOWNLOAD_DIR / filename
            self.s3_client.download_file(self.bucket, s3_key, str(temp_path))
            logger.info(f"{Colors.GREEN}✅ Downloaded: {filename}{Colors.RESET}")
            
            # Move to correct raw_store folder
            shutil.move(str(temp_path), str(target_path))
            logger.info(f"{Colors.GREEN}✅ Organized: {s3_category} -> {local_folder}/{filename}{Colors.RESET}")
            
            return target_path
            
        except Exception as e:
            logger.error(f"{Colors.RED}❌ Failed to process {s3_key}: {e}{Colors.RESET}")
            return None
    
    def run(self):
        """Main trigger function - calls YOUR batch_ingest"""
        print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}🔄 AUTOMATIC S3 TRIGGER{Colors.RESET}")
        print(f"{Colors.CYAN}   Using YOUR existing:{Colors.RESET}")
        print(f"{Colors.CYAN}   - app/services/batch_ingest.py (BatchIngestionService){Colors.RESET}")
        print(f"{Colors.CYAN}   - app/services/vector_store.py (VectorStore){Colors.RESET}")
        print(f"{Colors.CYAN}   - app/diagnose_ocr.py (OCRProcessor){Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")
        
        # Check S3 connection
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            print(f"{Colors.GREEN}✅ Connected to S3 bucket: {self.bucket}{Colors.RESET}\n")
        except ClientError as e:
            print(f"{Colors.RED}❌ Failed to connect: {e}{Colors.RESET}")
            return
        
        # List PDFs in S3
        pdfs = self.list_pdfs()
        print(f"{Colors.BLUE}📄 Found {len(pdfs)} PDF(s) in S3{Colors.RESET}")
        
        if not pdfs:
            print(f"\n{Colors.YELLOW}⚠️ No PDFs found in S3{Colors.RESET}")
            return
        
        # Show S3 categories
        s3_categories = {}
        for pdf in pdfs:
            cat = self.get_s3_category(pdf['key'])
            s3_categories[cat] = s3_categories.get(cat, 0) + 1
        
        print(f"\n{Colors.BLUE}📊 S3 Document Categories:{Colors.RESET}")
        for cat, count in sorted(s3_categories.items()):
            mapped = self.map_s3_to_local(cat)
            print(f"   📁 {cat} -> {mapped}: {count} documents")
        
        # Download and organize all PDFs
        print(f"\n{Colors.CYAN}📥 Downloading and organizing documents...{Colors.RESET}")
        processed_paths = []
        for pdf in pdfs:
            target_path = self.download_and_organize(pdf['key'])
            if target_path:
                processed_paths.append(str(target_path))
        
        print(f"\n{Colors.GREEN}✅ Organized: {len(processed_paths)} documents in raw_store/{Colors.RESET}")
        
        if not processed_paths:
            print(f"\n{Colors.YELLOW}⚠️ No new documents to process{Colors.RESET}")
            return
        
        # === TRIGGER YOUR EXISTING BATCH_INGEST ===
        print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}🧠 TRIGGERING YOUR BATCH_INGEST.PY{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.YELLOW}⏳ This will run your existing pipeline:{Colors.RESET}")
        print(f"   1. Your OCR (diagnose_ocr.py)")
        print(f"   2. Your Vector Store (vector_store.py)")
        print(f"   3. Your Batch Ingestion (batch_ingest.py)")
        print(f"\n{Colors.YELLOW}⏳ Processing... (this may take time){Colors.RESET}\n")
        
        try:
            # Use YOUR BatchIngestionService from app/services/
            service = BatchIngestionService(
                category_filter=None,
                file_filter=None,
                concurrency=2,
                dry_run=False
            )
            
            # Run YOUR batch ingestion
            result = asyncio.run(service.run())
            
            # Show result
            print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
            print(f"{Colors.CYAN}📊 BATCH INGESTION RESULT (from YOUR batch_ingest.py){Colors.RESET}")
            print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
            print(f"{Colors.GREEN}✅ Processed: {result.get('processed', 0)}{Colors.RESET}")
            print(f"{Colors.GREEN}📝 Total Chunks: {result.get('total_chunks', 0)}{Colors.RESET}")
            print(f"{Colors.YELLOW}⏭️  Skipped: {result.get('skipped', 0)}{Colors.RESET}")
            print(f"{Colors.RED}❌ Failed: {result.get('failed', 0)}{Colors.RESET}")
            
            if result.get('failures'):
                print(f"\n{Colors.RED}Failures:{Colors.RESET}")
                for f in result['failures']:
                    print(f"   - {f}")
            
            print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
            print(f"{Colors.GREEN}✅ Automatic trigger complete!{Colors.RESET}")
            print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")
            
        except Exception as e:
            print(f"{Colors.RED}❌ Error triggering batch_ingest: {e}{Colors.RESET}")
            import traceback
            traceback.print_exc()

def run_once():
    """Run the trigger once"""
    trigger = S3AutoTrigger()
    trigger.run()

if __name__ == "__main__":
    run_once()
