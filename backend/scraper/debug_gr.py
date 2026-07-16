import requests
from bs4 import BeautifulSoup

url = "https://gr.maharashtra.gov.in/1145/Government-Resolutions"

headers = {
    "User-Agent": "Mozilla/5.0"
}

r = requests.get(url, headers=headers)

print("Status:", r.status_code)
print("URL:", r.url)

with open("page.html", "w", encoding="utf-8") as f:
    f.write(r.text)

print("Saved page.html")
