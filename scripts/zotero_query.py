#!/usr/bin/env python3
"""
Simple script to query Zotero API directly.
Run with: python zotero_query.py "your search query"
"""

import os
import sys
from io import BytesIO
from dotenv import load_dotenv
from pyzotero import zotero
from pypdf import PdfReader

def get_pdf_content(zot, item_key: str) -> tuple:
    """Get the PDF content for a given item.
    Returns (success, content, attachment_key)
    """
    try:
        # First get the item to find its attachments
        item = zot.item(item_key)
        
        # Look for PDF attachment in the links
        if 'attachment' in item['links'] and item['links']['attachment']['attachmentType'] == 'application/pdf':
            attachment_key = item['links']['attachment']['href'].split('/')[-1]
            # Get the PDF content
            pdf_content = zot.file(attachment_key)
            return True, pdf_content, attachment_key
        
        # If not found in links, check children
        children = zot.children(item_key)
        for child in children:
            if child['data'].get('itemType') == 'attachment' and child['data'].get('contentType') == 'application/pdf':
                pdf_content = zot.file(child['key'])
                return True, pdf_content, child['key']
        
        return False, None, None
        
    except Exception as e:
        print(f"Error getting PDF content: {e}")
        return False, None, None

def main():
    load_dotenv()
    
    if not os.environ.get("ZOTERO_API_KEY") or not os.environ.get("ZOTERO_USER_ID"):
        print("Error: ZOTERO_API_KEY and ZOTERO_USER_ID must be set in .env file")
        sys.exit(1)
    
    try:
        zot = zotero.Zotero(
            os.environ['ZOTERO_USER_ID'],
            "user",
            os.environ['ZOTERO_API_KEY'],
            local=True
        )
        # Test the connection
        zot.items(limit=1)
    except Exception as e:
        if "Local API is not enabled" in str(e):
            print("Zotero local API is not enabled. Please enable it in Zotero Preferences -> Advanced -> Allow other applications on this computer to communicate with Zotero.")
            sys.exit(1)
        else:
            print(f"Error connecting to Zotero: {e}")
            sys.exit(1)
    
    query = sys.argv[1] if len(sys.argv) > 1 else "machine learning"
    
    items = zot.items(q=query)
    
    print(f"\nFound {len(items)} items matching query '{query}':")
    for item in items:
        data = item['data']
        title = data.get('title', 'No title')
        key = data.get('key')
        
        # Check for PDF
        has_pdf, _, attachment_key = get_pdf_content(zot, key)
        pdf_status = f"[PDF: {attachment_key}]" if has_pdf else "[No PDF]"
        if has_pdf:
            pdf_content = zot.file(attachment_key)
            try:
                # Try to decode as UTF-8 text first
                reader = PdfReader(BytesIO(pdf_content))
                # print(reader.pages[0].extract_text()[:1000])
                print(reader.pages[0].extract_text())
                for page in reader.pages:
                    print(page.extract_text())
            except Exception as e:
                # If decoding fails, show hex representation
                print(f"Error decoding PDF content: {e}")
                print("\nPDF Content (hex, first 100 bytes):")
                print(pdf_content[:100].hex())
        
        print(f"\n{pdf_status} {title}")
        print(f"Key: {key}")
        if data.get('abstractNote'):
            print(f"Abstract: {data['abstractNote'][:200]}...")
            print(data)
        print("-" * 80)
        

if __name__ == "__main__":
    main()
