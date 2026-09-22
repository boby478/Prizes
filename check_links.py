import os
import json
import argparse
import requests
from bs4 import BeautifulSoup
import nbformat
from nbconvert import HTMLExporter
from urllib.parse import urljoin

def check_url(url, session):
    """Checks the status of a URL."""
    try:
        # Use HEAD first to be efficient
        response = session.head(url, allow_redirects=True, timeout=10)
        # Some servers return 405 Method Not Allowed for HEAD, so fallback to GET
        if response.status_code == 405 or response.status_code >= 400:
            response = session.get(url, allow_redirects=True, timeout=10)
        return response.status_code
    except requests.exceptions.RequestException as e:
        return str(e)

def get_links_from_html(html_content, base_url=None):
    """Extracts all absolute and relative links from HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        # Skip anchors, mailto, tel, etc.
        if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        
        if href.startswith(('http://', 'https://')):
            links.add(href)
        elif base_url:
            # Resolve relative links using base_url
            links.add(urljoin(base_url, href))
    return links

def process_file(file_path, base_url=None):
    """Processes a file and returns its HTML content."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.ipynb':
            with open(file_path, 'r', encoding='utf-8') as f:
                nb = nbformat.read(f, as_version=4)
            html_exporter = HTMLExporter()
            (body, _) = html_exporter.from_notebooknode(nb)
            return body
        elif ext == '.html':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                # For JSON, we treat the whole thing as text to find links
                return f.read()
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Check for dead links in HTML, JSON, and Jupyter notebooks.")
    parser.add_argument("path", help="Path to file or directory to scan")
    parser.add_argument("--base-url", help="Base URL for resolving relative links (e.g., https://brightway.org/)", default=None)
    parser.add_argument("--output", help="Output JSON file path", default="broken_links.json")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path {args.path} does not exist.")
        return

    files_to_scan = []
    if os.path.isfile(args.path):
        files_to_scan.append(args.path)
    else:
        for root, _, files in os.walk(args.path):
            for file in files:
                if file.endswith(('.html', '.ipynb', '.json')):
                    files_to_scan.append(os.path.join(root, file))

    print(f"Found {len(files_to_scan)} files to scan.")

    # Map of URL -> list of files containing it
    url_to_files = {}
    
    for file_path in files_to_scan:
        html_content = process_file(file_path, args.base_url)
        if html_content:
            links = get_links_from_html(html_content, args.base_url)
            for link in links:
                if link not in url_to_files:
                    url_to_files[link] = []
                url_to_files[link].append(file_path)

    print(f"Extracted {len(url_to_files)} unique links. Checking status...")

    session = requests.Session()
    session.headers.update({'User-Agent': 'Brightway-Link-Checker/1.0'})
    
    broken_links = []

    for url, files in url_to_files.items():
        status = check_url(url, session)
        
        is_broken = False
        error_msg = ""
        
        if isinstance(status, int):
            if status >= 400:
                is_broken = True
                error_msg = f"HTTP {status}"
        else:
            is_broken = True
            error_msg = status

        if is_broken:
            broken_links.append({
                "url": url,
                "error": error_msg,
                "found_in": files
            })

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(broken_links, f, indent=2)

    print(f"Scan complete. {len(broken_links)} broken links found.")
    print(f"Report saved to: {args.output}")

if __name__ == "__main__":
    main()