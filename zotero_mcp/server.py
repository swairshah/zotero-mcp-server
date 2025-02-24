#!/usr/bin/env python3
"""MCP server implementation for Zotero integration."""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP, Context
from pyzotero import zotero
from anthropic import Anthropic
from pypdf import PdfReader
from io import BytesIO
import tempfile
import zipfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TODO_TAG_NAME = "todo"
SUMMARIZED_TAG_NAME = "summarized"
ERROR_TAG_NAME = "error"
DENY_TAG_NAME = "deny"

mcp = FastMCP(
    "zotero-mcp-server",
    version="0.1.0",
    capabilities={"tools": True}
)

zot = zotero.Zotero(
    int(os.environ['ZOTERO_USER_ID']),
    "user",
    os.environ['ZOTERO_API_KEY']
)
anthropic = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

@mcp.tool()
def search_papers(tags: List[str] = None) -> dict:
    """Search through Zotero papers based on tags and/or text."""
    try:
        if tags:
            # use a single tag for now since the API handles multiple tags differently
            items = zot.items(tag=tags[0]) if len(tags) == 1 else zot.items()
            # filter for multiple tags client-side if needed
            if len(tags) > 1:
                items = [item for item in items 
                        if all(tag in [t['tag'] for t in item['data'].get('tags', [])] 
                        for tag in tags)]
        else:
            items = zot.items()

        # enhanced response with more useful information
        processed_items = []
        for item in items:
            # skip attachments and notes
            if item.get('data', {}).get('itemType') in ['attachment', 'note']:
                continue
                
            item_data = item.get('data', {})
            processed_item = {
                'key': item.get('key'),
                'title': item_data.get('title', 'Unknown Title'),
                'authors': item_data.get('creators', []),
                'year': item_data.get('date', '').split('-')[0] if item_data.get('date') else None,
                'tags': [t.get('tag') for t in item_data.get('tags', [])],
                'abstract': item_data.get('abstractNote'),
                'url': item_data.get('url'),
                'item_type': item_data.get('itemType'),
                'raw_data': item  # Include raw data for complete access 
            }
            processed_items.append(processed_item)

        return {
            "status": "success", 
            "total_results": len(processed_items),
            "items": processed_items
        }
    except Exception as e:
        logger.error(f"Error searching papers: {str(e)}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
def get_paper_notes(item_key: str) -> Dict[str, Any]:
    """Get all notes attached to a specific paper."""
    try:
        notes = zot.children(item_key)
        return {
            "notes": [{
                "key": note["key"],
                "text": note["data"].get("note", ""),
                "tags": [tag["tag"] for tag in note["data"].get("tags", [])]
            } for note in notes if note["data"].get("itemType") == "note"]
        }
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        raise ValueError(str(e))

@mcp.tool()
def get_paper(item_key: str) -> Dict[str, Any]:
    """Get details for a specific paper."""
    try:
        item = zot.item(item_key)
        if not item:
            return {"status": "error", "message": "Paper not found"}
            
        item_data = item.get('data', {})
        processed_item = {
            'key': item.get('key'),
            'title': item_data.get('title', 'Unknown Title'),
            'authors': item_data.get('creators', []),
            'year': item_data.get('date', '').split('-')[0] if item_data.get('date') else None,
            'tags': [t.get('tag') for t in item_data.get('tags', [])],
            'abstract': item_data.get('abstractNote'),
            'url': item_data.get('url'),
            'item_type': item_data.get('itemType'),
            'raw_data': item
        }
        return {"status": "success", "item": processed_item}
    except Exception as e:
        logger.error(f"Error getting paper: {str(e)}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
def add_note(item_key: str, note_text: str, tags: List[str] = None) -> dict:
    """Add a note to a specific paper."""
    try:
        # verify the paper exists first
        paper = get_paper(item_key)
        if paper.get("status") == "error":
            return paper
        
        # create the note
        template = {
            'itemType': 'note',
            'parentItem': item_key,
            'note': note_text,
            'tags': [{'tag': tag} for tag in (tags or [])]
        }
        
        result = zot.create_items([template])
        note_key = result.get("successful", {}).get("0", {}).get("key")
        
        return {
            "status": "success",
            "note_key": note_key,
            "paper_title": paper["item"]["title"]
        }
    except Exception as e:
        logger.error(f"Error adding note: {str(e)}")
        return {"status": "error", "message": str(e)}

# TODO: FIX THIS
@mcp.tool()
def request_summary(item_key: str) -> Dict[str, Any]:
    """Request a summary for a paper."""
    try:
        # add TODO tag to trigger summarization
        item = zot.item(item_key)
        tags = item["data"]["tags"]
        if not any(tag["tag"] == TODO_TAG_NAME for tag in tags):
            tags.append({"tag": TODO_TAG_NAME})
            item["data"]["tags"] = tags
            zot.update_item(item)
        return {"status": "success", "message": "Summary requested"}
    except Exception as e:
        logger.error(f"Error requesting summary: {e}")
        raise ValueError(str(e))

if __name__ == "__main__":
    # for local testing
    load_dotenv()
    
    required_env_vars = ['ZOTERO_USER_ID']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please ensure these are set in your .env file")
        exit(1)
        
    mcp.run()