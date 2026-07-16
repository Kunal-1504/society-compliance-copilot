"""
S3 POLLER - Automatic Document Ingestion Pipeline
1. Polls S3 for new PDFs
2. Downloads them
3. Runs OCR (diagnose_ocr.py)
4. Chunks and embeds (vector_store.py)
5. Stores in pgvector
"""

import os
import sys
import csv
import io
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import your existing modules
from app.services.vector_store import VectorStore
from app.diagnose_ocr import OCRProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("s3_poller")

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET_NAME', 'society-compliance-copilot')
S3_PREFIX = os.environ.get('S3_PREFIX', 'dataset')
LOCAL_DATA_DIR = Path(os.environ.get('S3_MIRROR_DIR', './data/s3_mirror'))

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

class AutomaticS3Poller:
    """Automatic S3 Poller with full OCR -> Chunk -> Embed -> Store pipeline"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
        self.bucket = S3_BUCKET
        self.prefix = S3_PREFIX
        self.local_dir = LOCAL_DATA_DIR
        
        # Create local directory
        self.local_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize OCR and Vector Store
        self.ocr_processor = OCRProcessor()
        self.vector_store = VectorStore()
        
        # Statistics
        self.stats = {
            'total_in_s3': 0,
            'already_downloaded': 0,
            'new_downloads': 0,
            'ocr_success': 0,
            'ocr_failed': 0,
            'chunk_success': 0,
            'chunk_failed': 0,
            'vector_success': 0,
            'vector_failed': 0
        }
        
        logger.info(f"{Colors.CYAN}📁 Automatic S3 Poller initialized{Colors.RESET}")
        logger.info(f"   Bucket: {self.bucket}")
        logger.info(f"   Prefix: {self.prefix}")
        logger.info(f"   Local: {self.local_dir}")
    
    def list_pdfs(self) -> List[Dict]:
        """List all PDFs in S3 with metadata"""
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
    
    def download_file(self, s3_key: str) -> Optional[Path]:
        """Download a file from S3"""
        try:
            local_path = self.local_dir / s3_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if already downloaded
            if local_path.exists():
                logger.info(f"{Colors.YELLOW}⏭️  Already exists: {local_path}{Colors.RESET}")
                return local_path
            
            # Download
            self.s3_client.download_file(self.bucket, s3_key, str(local_path))
            logger.info(f"{Colors.GREEN}✅ Downloaded: {s3_key}{Colors.RESET}")
            return local_path
            
        except Exception as e:
            logger.error(f"{Colors.RED}❌ Failed to download {s3_key}: {e}{Colors.RESET}")
            return None
    
    def get_category(self, s3_key: str) -> str:
        """Extract category from S3 key"""
        parts = s3_key.split('/')
        return parts[1] if len(parts) >= 3 else "uncategorized"
    
    def get_language(self, filename: str) -> str:
        """Detect language from filename"""
        if any(c in filename for c in ['मराठी', 'हिंदी', 'अधिनियम', 'नियम', 'आदरश', 'गहनरमण']):
            return "mr"
        elif any(c in filename for c in ['Act', 'Rules', 'Regulation', 'Election']):
            return "en"
        return "mixed"
    
    def process_with_ocr(self, pdf_path: Path) -> Optional[str]:
        """Run OCR on PDF and extract text"""
        try:
            logger.info(f"{Colors.BLUE}📄 Running OCR on: {pdf_path.name}{Colors.RESET}")
            
            # Use your existing OCR processor
            result = self.ocr_processor.process_pdf(str(pdf_path))
            
            if result and result.get('text'):
                logger.info(f"{Colors.GREEN}✅ OCR successful: {len(result['text'])} characters extracted{Colors.RESET}")
                self.stats['ocr_success'] += 1
                return result['text']
            else:
                logger.warning(f"{Colors.YELLOW}⚠️ No text extracted from: {pdf_path.name}{Colors.RESET}")
                self.stats['ocr_failed'] += 1
                return None
                
        except Exception as e:
            logger.error(f"{Colors.RED}❌ OCR failed for {pdf_path.name}: {e}{Colors.RESET}")
            self.stats['ocr_failed'] += 1
            return None
    
    def chunk_and_embed(self, text: str, doc_name: str, category: str, language: str) -> bool:
        """Chunk text and store embeddings in vector database"""
        try:
            logger.info(f"{Colors.BLUE}🧩 Chunking and embedding: {doc_name}{Colors.RESET}")
            
            # Use your vector store to process
            result = self.vector_store.process_and_index_pdf(
                pdf_path=text,  # This expects PDF path, but we have text
                doc_name=doc_name,
                language=language,
                category=category
            )
            
            # Alternative: Create chunks directly if you have that function
            if hasattr(self.vector_store, 'chunk_and_store_text'):
                result = self.vector_store.chunk_and_store_text(
                    text=text,
                    doc_name=doc_name,
                    category=category,
                    language=language
                )
            else:
                # Fallback: Use the vector store's chunking method
                chunks = self.vector_store.chunk_text(text)
                embeddings = self.vector_store.embed_chunks(chunks)
                stored = self.vector_store.store_embeddings(doc_name, chunks, embeddings, category, language)
                
                if stored:
                    logger.info(f"{Colors.GREEN}✅ Successfully stored {len(chunks)} chunks{Colors.RESET}")
                    self.stats['vector_success'] += 1
                    return True
            
            self.stats['vector_success'] += 1
            return True
            
        except Exception as e:
            logger.error(f"{Colors.RED}❌ Failed to chunk/embed {doc_name}: {e}{Colors.RESET}")
            self.stats['vector_failed'] += 1
            return False
    
    def process_document(self, pdf_path: Path, s3_key: str) -> bool:
        """Process a single document through the full pipeline"""
        try:
            # Get metadata
            category = self.get_category(s3_key)
            language = self.get_language(pdf_path.name)
            doc_name = pdf_path.name
            
            logger.info(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
            logger.info(f"{Colors.CYAN}📄 Processing: {doc_name}{Colors.RESET}")
            logger.info(f"{Colors.CYAN}   Category: {category}{Colors.RESET}")
            logger.info(f"{Colors.CYAN}   Language: {language}{Colors.RESET}")
            logger.info(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
            
            # Step 1: OCR
            text = self.process_with_ocr(pdf_path)
            if not text:
                return False
            
            # Step 2: Chunk and Embed
            success = self.chunk_and_embed(text, doc_name, category, language)
            
            return success
            
        except Exception as e:
            logger.error(f"{Colors.RED}❌ Failed to process {s3_key}: {e}{Colors.RESET}")
            return False
    
    def run_once(self):
        """Run the poller once - full pipeline"""
        print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}🔄 AUTOMATIC S3 POLLER - FULL PIPELINE{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}   OCR -> Chunk -> Embed -> Store in pgvector{Colors.RESET}")
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
        self.stats['total_in_s3'] = len(pdfs)
        logger.info(f"📄 Found {len(pdfs)} PDF(s) in S3")
        
        if not pdfs:
            print(f"\n{Colors.YELLOW}⚠️ No PDFs found in S3{Colors.RESET}")
            return
        
        # Show categories
        categories = {}
        for pdf in pdfs:
            cat = self.get_category(pdf['key'])
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n{Colors.BLUE}📊 Document Categories:{Colors.RESET}")
        for cat, count in sorted(categories.items()):
            print(f"   📁 {cat}: {count} documents")
        
        # Process each PDF
        print(f"\n{Colors.CYAN}📥 Starting automatic processing...{Colors.RESET}")
        print(f"{Colors.YELLOW}⏳ This may take time (OCR + Embedding)...{Colors.RESET}\n")
        
        processed = 0
        for i, pdf_info in enumerate(pdfs, 1):
            s3_key = pdf_info['key']
            print(f"\n{Colors.BLUE}[{i}/{len(pdfs)}] Processing...{Colors.RESET}")
            
            # Download
            local_path = self.download_file(s3_key)
            if not local_path:
                continue
            
            self.stats['new_downloads'] += 1
            
            # Process through full pipeline
            success = self.process_document(local_path, s3_key)
            if success:
                processed += 1
            
            # Progress update
            progress = (i / len(pdfs)) * 100
            print(f"{Colors.BLUE}📊 Progress: {progress:.1f}% ({i}/{len(pdfs)}){Colors.RESET}")
        
        # Final summary
        print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}📊 INGESTION SUMMARY{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BLUE}📄 Total in S3: {self.stats['total_in_s3']}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Downloaded: {self.stats['new_downloads']}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ OCR Success: {self.stats['ocr_success']}{Colors.RESET}")
        print(f"{Colors.RED}❌ OCR Failed: {self.stats['ocr_failed']}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Vector Storage: {self.stats['vector_success']}{Colors.RESET}")
        print(f"{Colors.RED}❌ Vector Failed: {self.stats['vector_failed']}{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.GREEN}✅ Automatic ingestion complete!{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")

def run_once():
    """Run the poller once"""
    poller = AutomaticS3Poller()
    poller.run_once()

def run_continuous():
    """Run the poller continuously (for production)"""
    import time
    poller = AutomaticS3Poller()
    
    print(f"\n{Colors.CYAN}🔄 Running in continuous mode...{Colors.RESET}")
    print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.RESET}\n")
    
    while True:
        try:
            poller.run_once()
            print(f"\n{Colors.YELLOW}⏳ Waiting 1 hour before next check...{Colors.RESET}")
            time.sleep(3600)  # Check every hour
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⏹️ Stopped by user{Colors.RESET}")
            break
        except Exception as e:
            logger.error(f"Error in continuous run: {e}")
            time.sleep(60)  # Wait 1 minute on error

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--continuous', action='store_true', 
                       help='Run continuously (check every hour)')
    parser.add_argument('--once', action='store_true', default=True,
                       help='Run once (default)')
    args = parser.parse_args()
    
    if args.continuous:
        run_continuous()
    else:
        run_once()
