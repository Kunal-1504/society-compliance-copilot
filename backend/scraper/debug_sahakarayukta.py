# debug_sahakarayukta.py
import requests
from bs4 import BeautifulSoup

def debug_sahakarayukta():
    urls = [
        "https://sahakarayukta.maharashtra.gov.in/Site/Information/ListingUploadOtherPdf.aspx?Doctype=883C2837-B898-4558-8CD6-87090AD2291B&MenuID=1072",
        "https://sahakarayukta.maharashtra.gov.in/1065/GR-/-Circulars-/-Notifications",
        "https://sahakarayukta.maharashtra.gov.in/1105/Model-Bye-Laws?Doctype=1CC73BAD-36CA-45AA-BA03-2119E31B6337",
    ]
    
    for url in urls:
        print("\n" + "=" * 70)
        print(f"URL: {url}")
        print("=" * 70)
        
        try:
            response = requests.get(url, verify=False, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all tables
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables")
            
            for i, table in enumerate(tables):
                print(f"\n--- Table {i+1} ---")
                print(f"ID: {table.get('id', 'No ID')}")
                print(f"Class: {table.get('class', 'No Class')}")
                
                # Get first row
                rows = table.find_all('tr')
                if rows:
                    print(f"Rows: {len(rows)}")
                    # Show header row
                    header = rows[0].find_all(['th', 'td'])
                    header_text = [h.get_text(strip=True)[:30] for h in header]
                    print(f"Headers: {header_text}")
                    
                    # Show first data row
                    if len(rows) > 1:
                        data = rows[1].find_all(['td'])
                        data_text = [d.get_text(strip=True)[:30] for d in data]
                        print(f"First data row: {data_text}")
                        
                        # Find PDF links
                        for d in data:
                            link = d.find('a')
                            if link:
                                href = link.get('href')
                                if href and '.pdf' in href.lower():
                                    print(f"PDF Link: {href}")
            
            # Also look for PDF links outside tables
            pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            if pdf_links:
                print(f"\nFound {len(pdf_links)} PDF links outside tables:")
                for link in pdf_links[:5]:
                    print(f"  {link.get('href')}")
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_sahakarayukta()