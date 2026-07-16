import psycopg
import os
from dotenv import load_dotenv

load_dotenv("/home/stark/society-compliance-chatbot/backend/.env")
dsn = os.getenv("DATABASE_URL")

try:
    conn = psycopg.connect(dsn)
    print("Connected successfully!")
    with conn.cursor() as cur:
        query_text = "Apartment"
        # Test full text search query
        cur.execute("""
            SELECT 
                dc.content, 
                dc.source_page_start, 
                d.file_name, 
                ts_rank_cd(to_tsvector('simple', dc.content), plainto_tsquery('simple', %s)) AS rank
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', %s)
            ORDER BY rank DESC
            LIMIT 5;
        """, (query_text, query_text))
        rows = cur.fetchall()
        print(f"FTS Search for '{query_text}' returned {len(rows)} results:")
        for idx, row in enumerate(rows):
            print(f"Result {idx+1}: p.{row[1]} in {row[2]} (Rank: {row[3]:.3f})")
            print(f"  Content: {row[0][:150]}...")
    conn.close()
except Exception as e:
    print("Error:", e)
