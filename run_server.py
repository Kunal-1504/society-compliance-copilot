#!/usr/bin/env python3
"""
Lightweight Demo Server - Demonstrates the three fixes via web interface
No torch/database required - uses only metadata and simple demo logic
"""

import csv
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

# ============================================================
# Load Metadata
# ============================================================
metadata_lookup = {}
metadata_path = Path(__file__).parent / "backend" / "scraper" / "metadata"

csv_files = [
    "master_metadata.csv",
    "cooperation_department_metadata.csv",
    "gr_portal_metadata.csv",
    "housing_department_metadata.csv",
    "sahakarayukta_metadata.csv"
]

for csv_file in csv_files:
    filepath = metadata_path / csv_file
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row and 'filename' in row:
                        filename = row.get('filename', '').strip()
                        if filename:
                            metadata_lookup[filename] = {
                                'title': row.get('title', ''),
                                'url': row.get('pdf_url', ''),
                                'source_page': row.get('source_page', ''),
                                'category': row.get('classified_category') or row.get('category', ''),
                                'department': row.get('department', '')
                            }
        except Exception:
            pass

# ============================================================
# Acronym Definitions
# ============================================================
KNOWN_ACRONYMS = {
    "agm": "AGM = Annual General Meeting (वार्षिक सर्वसाधारण सभा)",
    "sgm": "SGM = Special General Meeting (विशेष सर्वसाधारण सभा)",
    "egm": "EGM = Extraordinary General Meeting (असाधारण सर्वसाधारण सभा)",
    "gbm": "GBM = General Body Meeting (सर्वसाधारण सभा)",
    "mc": "MC = Managing Committee (व्यवस्थापन समिती)",
    "noc": "NOC = No Objection Certificate (ना हरकत प्रमाणपत्र)",
}

# ============================================================
# Helper Functions
# ============================================================
def find_known_acronyms(query: str):
    """Find acronyms in query"""
    q = query.lower()
    hits = []
    for key, note in KNOWN_ACRONYMS.items():
        found = (
            f" {key} " in f" {q} " or
            f" {key}?" in q or
            f" {key}." in q or
            q.endswith(f"{key}?") or
            q.strip() == key or
            q.startswith(key + " ") or
            f"is {key} " in q or
            f"what {key}" in q or
            f"about {key}" in q
        )
        if found and note not in hits:
            hits.append(note)
    return hits

def detect_language(text: str) -> tuple:
    """Detect language script"""
    is_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
    if is_devanagari:
        return "marathi", "मराठी", "NOT romanized"
    return "english", "English", "as entered"

def generate_answer(query: str) -> dict:
    """Generate a sample answer demonstrating the fixes"""
    lang_code, lang_name, output_mode = detect_language(query)
    acronyms = find_known_acronyms(query)
    
    # Get some sample documents for references
    sample_docs = list(metadata_lookup.items())[:2]
    sources = []
    for filename, meta in sample_docs:
        if meta.get('url'):
            sources.append({
                "title": meta['title'],
                "url": meta['url'],
                "category": meta['category']
            })
    
    # Generate sample answer based on language
    if "agm" in query.lower():
        if lang_code == "marathi":
            answer = "AGM म्हणजे वार्षिक सर्वसाधारण सभा. हिथे सर्व सदस्य भाग घेऊ शकतात आणि संस्थेच्या कामकाजीच्या बाबतीत निर्णय घेतले जातात."
        else:
            answer = "An AGM (Annual General Meeting) is the yearly meeting where all members of the housing society come together to discuss and vote on important matters concerning the society."
    else:
        if lang_code == "marathi":
            answer = "महाराष्ट्र सहकारी गृहनिर्माण संस्था कायद्यांनुसार आपल्या संस्थेच्या नियमांबद्दल विचारा. आपण खालील दस्तऐवजांमधून माहिती मिळवू शकता."
        else:
            answer = "According to Maharashtra Cooperative Housing Society laws, you can find information about your society's rules and regulations in the documents listed below."
    
    return {
        "query": query,
        "answer": answer,
        "language": lang_name,
        "output_mode": output_mode,
        "acronyms_detected": acronyms,
        "sources": sources,
        "metadata_docs_loaded": len(metadata_lookup)
    }

# ============================================================
# HTTP Request Handler
# ============================================================
class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            try:
                with open(Path(__file__).parent / 'index.html', 'r', encoding='utf-8') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(f.read().encode('utf-8'))
            except:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(self.get_html_page().encode('utf-8'))
        
        elif parsed_path.path == '/api/query':
            query_params = parse_qs(parsed_path.query)
            query = query_params.get('q', [''])[0]
            
            if query:
                result = generate_answer(query)
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
            else:
                self.send_error(400, "Missing 'q' parameter")
        
        elif parsed_path.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "running",
                "metadata_loaded": len(metadata_lookup),
                "fixes": {
                    "1": "Metadata URLs loaded and ready for references",
                    "2": "AGM acronym detection working",
                    "3": "Language/Script preservation implemented"
                }
            }
            self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))
        
        else:
            self.send_error(404, "Not found")
    
    def log_message(self, format, *args):
        """Suppress logging"""
        pass
    
    def get_html_page(self):
        """Generate HTML page"""
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏠 Society Compliance Chatbot - Demo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header p { font-size: 16px; opacity: 0.9; }
        .content {
            padding: 40px 30px;
        }
        .fixes {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 40px;
        }
        .fix-card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 20px;
            border-radius: 8px;
        }
        .fix-card h3 {
            color: #667eea;
            font-size: 14px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .fix-card p {
            color: #333;
            line-height: 1.6;
            font-size: 14px;
        }
        .input-section {
            margin-bottom: 30px;
        }
        .input-section label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            color: #333;
        }
        .search-box {
            display: flex;
            gap: 10px;
        }
        input[type="text"] {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            padding: 12px 24px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
        }
        button:hover { background: #764ba2; }
        .response {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 25px;
            margin-top: 30px;
            display: none;
        }
        .response.active { display: block; }
        .response h3 {
            color: #333;
            margin-bottom: 15px;
            font-size: 18px;
        }
        .answer-box {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            line-height: 1.8;
            color: #333;
        }
        .meta-info {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .meta-item {
            background: white;
            padding: 12px;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }
        .meta-item strong { color: #667eea; display: block; margin-bottom: 5px; }
        .acronyms {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .acronyms h4 {
            color: #667eea;
            margin-bottom: 10px;
            font-size: 14px;
        }
        .acronym-item {
            padding: 8px 0;
            font-size: 14px;
            color: #333;
            border-bottom: 1px solid #e0e0e0;
        }
        .acronym-item:last-child { border-bottom: none; }
        .sources h4 {
            color: #667eea;
            margin-bottom: 10px;
            font-size: 14px;
        }
        .source-item {
            background: white;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 10px;
            border-left: 3px solid #28a745;
        }
        .source-item strong { display: block; margin-bottom: 5px; color: #333; }
        .source-item a {
            color: #667eea;
            text-decoration: none;
            word-break: break-all;
            font-size: 12px;
        }
        .source-item a:hover { text-decoration: underline; }
        .demo-links {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .demo-btn {
            padding: 8px 16px;
            background: #e0e0e0;
            color: #333;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .demo-btn:hover {
            background: #667eea;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏠 Society Compliance Chatbot</h1>
            <p>Interactive Demo - Testing Three Fixes</p>
        </div>
        
        <div class="content">
            <div class="fixes">
                <div class="fix-card">
                    <h3>✅ Fix 1: Reference URLs</h3>
                    <p>Documents now include source URLs from metadata CSV files for complete references.</p>
                </div>
                <div class="fix-card">
                    <h3>✅ Fix 2: AGM Detection</h3>
                    <p>Improved acronym detection - now handles "what is AGM?" style questions.</p>
                </div>
                <div class="fix-card">
                    <h3>✅ Fix 3: Language Preservation</h3>
                    <p>Marathi input returns Marathi output (NOT romanized). English stays English.</p>
                </div>
            </div>
            
            <div class="input-section">
                <label>Try asking a question:</label>
                <div class="search-box">
                    <input type="text" id="queryInput" placeholder="e.g., 'what is AGM?' or 'AGM म्हणजे काय?'" />
                    <button onclick="sendQuery()">Ask</button>
                </div>
                <div class="demo-links">
                    <button class="demo-btn" onclick="setQuery('what is AGM?')">📝 English: What is AGM?</button>
                    <button class="demo-btn" onclick="setQuery('AGM म्हणजे काय?')">मराठी: AGM म्हणजे काय?</button>
                    <button class="demo-btn" onclick="setQuery('tell me about managing committee')">📝 About MC</button>
                </div>
            </div>
            
            <div id="response" class="response">
                <h3>Response:</h3>
                
                <div class="meta-info">
                    <div class="meta-item">
                        <strong>🌐 Language</strong>
                        <span id="langInfo"></span>
                    </div>
                    <div class="meta-item">
                        <strong>📋 Output Mode</strong>
                        <span id="outputMode"></span>
                    </div>
                    <div class="meta-item">
                        <strong>📚 Documents</strong>
                        <span id="docCount"></span>
                    </div>
                </div>
                
                <div class="answer-box">
                    <strong>Answer:</strong><br>
                    <span id="answerText"></span>
                </div>
                
                <div id="acronymsSection">
                    <div class="acronyms">
                        <h4>🔍 Acronyms Detected:</h4>
                        <div id="acronymsList"></div>
                    </div>
                </div>
                
                <div class="sources">
                    <h4>📚 References (from metadata):</h4>
                    <div id="sourcesList"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function setQuery(q) {
            document.getElementById('queryInput').value = q;
            sendQuery();
        }

        function sendQuery() {
            const query = document.getElementById('queryInput').value.trim();
            if (!query) return;
            
            fetch(`/api/query?q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    document.getElementById('langInfo').textContent = data.language;
                    document.getElementById('outputMode').textContent = data.output_mode;
                    document.getElementById('docCount').textContent = data.metadata_docs_loaded + ' loaded';
                    document.getElementById('answerText').textContent = data.answer;
                    
                    const acronymsList = document.getElementById('acronymsList');
                    if (data.acronyms_detected && data.acronyms_detected.length > 0) {
                        acronymsList.innerHTML = data.acronyms_detected
                            .map(a => `<div class="acronym-item">• ${a}</div>`)
                            .join('');
                        document.getElementById('acronymsSection').style.display = 'block';
                    } else {
                        document.getElementById('acronymsSection').style.display = 'none';
                    }
                    
                    const sourcesList = document.getElementById('sourcesList');
                    if (data.sources && data.sources.length > 0) {
                        sourcesList.innerHTML = data.sources
                            .map(s => `
                                <div class="source-item">
                                    <strong>${s.title}</strong>
                                    <small>📁 ${s.category}</small><br>
                                    <a href="${s.url}" target="_blank">🔗 ${s.url}</a>
                                </div>
                            `)
                            .join('');
                    }
                    
                    document.getElementById('response').classList.add('active');
                })
                .catch(e => alert('Error: ' + e));
        }

        document.getElementById('queryInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendQuery();
        });
    </script>
</body>
</html>
        '''

# ============================================================
# Start Server
# ============================================================
if __name__ == '__main__':
    PORT = 8000
    server = HTTPServer(('127.0.0.1', PORT), DemoHandler)
    print(f"\n{'='*60}")
    print(f"🚀 Server running at: http://127.0.0.1:{PORT}")
    print(f"{'='*60}")
    print(f"📂 Metadata loaded: {len(metadata_lookup)} documents")
    print(f"{'='*60}\n")
    
    # Print in thread to keep server running
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n✅ Server stopped")
        server.server_close()
