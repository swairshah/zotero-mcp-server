#!/usr/bin/env python3
"""SQLite-based MCP server implementation for Zotero integration."""

import json
import logging
import os
import sqlite3
import random
import string
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP, Context
from pypdf import PdfReader
from io import BytesIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "zotero-db-mcp-server",
    version="0.1.0",
    capabilities={"tools": True}
)

class ZoteroDatabase:
    """Direct SQLite database interface for Zotero."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.storage_path = self.db_path.parent / "storage"
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Zotero database not found: {self.db_path}")
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self):
        """Test database connection and basic schema."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM items")
                count = cursor.fetchone()[0]
                logger.info(f"Connected to Zotero database with {count} items")
        except sqlite3.Error as e:
            raise ConnectionError(f"Failed to connect to database: {e}")
    
    def _execute_read(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a read query and return results as list of dicts."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database read error: {e}")
            raise
    
    def _execute_write(self, operations: List[tuple]) -> Dict[str, Any]:
        """Execute write operations in a transaction."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Begin transaction
                cursor.execute("BEGIN IMMEDIATE")
                
                results = []
                for query, params in operations:
                    cursor.execute(query, params)
                    results.append(cursor.lastrowid)
                
                conn.commit()
                return {"status": "success", "results": results}
                
        except sqlite3.Error as e:
            logger.error(f"Database write error: {e}")
            return {"status": "error", "message": str(e)}
    
    def _generate_key(self) -> str:
        """Generate a new 8-character Zotero-style key."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    def search_items(self, query: str = None, tags: List[str] = None) -> List[Dict]:
        """Search for items using direct SQL."""
        
        base_query = """
        SELECT 
            i.itemID,
            i.key,
            i.dateAdded,
            i.dateModified,
            it.typeName as itemType,
            -- Get title
            (SELECT idv.value 
             FROM itemData id 
             JOIN itemDataValues idv ON id.valueID = idv.valueID
             JOIN fields f ON id.fieldID = f.fieldID  
             WHERE id.itemID = i.itemID AND f.fieldName = 'title') as title,
            -- Get abstract
            (SELECT idv.value 
             FROM itemData id 
             JOIN itemDataValues idv ON id.valueID = idv.valueID
             JOIN fields f ON id.fieldID = f.fieldID  
             WHERE id.itemID = i.itemID AND f.fieldName = 'abstractNote') as abstract,
            -- Get URL
            (SELECT idv.value 
             FROM itemData id 
             JOIN itemDataValues idv ON id.valueID = idv.valueID
             JOIN fields f ON id.fieldID = f.fieldID  
             WHERE id.itemID = i.itemID AND f.fieldName = 'url') as url,
            -- Get date
            (SELECT idv.value 
             FROM itemData id 
             JOIN itemDataValues idv ON id.valueID = idv.valueID
             JOIN fields f ON id.fieldID = f.fieldID  
             WHERE id.itemID = i.itemID AND f.fieldName = 'date') as date
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE it.typeName NOT IN ('attachment', 'note')
        """
        
        params = []
        conditions = []
        
        if query:
            conditions.append("""
                (EXISTS (SELECT 1 FROM itemData id 
                        JOIN itemDataValues idv ON id.valueID = idv.valueID
                        JOIN fields f ON id.fieldID = f.fieldID  
                        WHERE id.itemID = i.itemID 
                        AND f.fieldName = 'title' 
                        AND idv.value LIKE ?))
            """)
            params.append(f"%{query}%")
        
        if tags:
            for tag in tags:
                conditions.append("""
                    EXISTS (SELECT 1 FROM itemTags itn 
                           JOIN tags t ON itn.tagID = t.tagID 
                           WHERE itn.itemID = i.itemID AND t.name = ?)
                """)
                params.append(tag)
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY i.dateModified DESC"
        
        results = self._execute_read(base_query, tuple(params))
        
        # Enhance results with creators and tags
        for item in results:
            item_id = item['itemID']
            
            # Get creators
            creators_query = """
                SELECT c.firstName, c.lastName, ct.creatorType
                FROM itemCreators ic
                JOIN creators c ON ic.creatorID = c.creatorID
                JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
                WHERE ic.itemID = ?
                ORDER BY ic.orderIndex
            """
            item['creators'] = self._execute_read(creators_query, (item_id,))
            
            # Get tags
            tags_query = """
                SELECT t.name
                FROM itemTags itn
                JOIN tags t ON itn.tagID = t.tagID
                WHERE itn.itemID = ?
            """
            item['tags'] = [row['name'] for row in self._execute_read(tags_query, (item_id,))]
        
        return results
    
    def get_item_by_key(self, key: str) -> Optional[Dict]:
        """Get a single item by its key."""
        results = self._execute_read("SELECT itemID FROM items WHERE key = ?", (key,))
        if not results:
            return None
        
        items = self.search_items()
        for item in items:
            if item['key'] == key:
                return item
        return None
    
    def get_item_notes(self, item_key: str) -> List[Dict]:
        """Get all notes for an item."""
        # First get the parent item ID
        parent_result = self._execute_read("SELECT itemID FROM items WHERE key = ?", (item_key,))
        if not parent_result:
            return []
        
        parent_id = parent_result[0]['itemID']
        
        # Get notes
        notes_query = """
            SELECT i.itemID, i.key, inotes.note, inotes.title
            FROM items i
            JOIN itemNotes inotes ON i.itemID = inotes.itemID
            WHERE inotes.parentItemID = ?
            ORDER BY i.dateAdded
        """
        notes = self._execute_read(notes_query, (parent_id,))
        
        # Get tags for each note
        for note in notes:
            note_id = note['itemID']
            tags_query = """
                SELECT t.name
                FROM itemTags itn
                JOIN tags t ON itn.tagID = t.tagID
                WHERE itn.itemID = ?
            """
            note['tags'] = [row['name'] for row in self._execute_read(tags_query, (note_id,))]
        
        return notes
    
    def add_note(self, item_key: str, note_text: str, tags: List[str] = None) -> Dict[str, Any]:
        """Add a note to an item."""
        # Get parent item
        parent_result = self._execute_read("SELECT itemID, libraryID FROM items WHERE key = ?", (item_key,))
        if not parent_result:
            return {"status": "error", "message": "Parent item not found"}
        
        parent_id = parent_result[0]['itemID']
        library_id = parent_result[0]['libraryID']
        
        # Get next item ID
        max_id_result = self._execute_read("SELECT MAX(itemID) as max_id FROM items")
        new_item_id = (max_id_result[0]['max_id'] or 0) + 1
        
        # Get note type ID
        note_type_result = self._execute_read("SELECT itemTypeID FROM itemTypes WHERE typeName = 'note'")
        if not note_type_result:
            return {"status": "error", "message": "Note item type not found"}
        note_type_id = note_type_result[0]['itemTypeID']
        
        # Generate new key and timestamp
        new_key = self._generate_key()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Prepare operations
        operations = [
            # Create item record
            ("INSERT INTO items (itemID, itemTypeID, dateAdded, dateModified, key, libraryID) VALUES (?, ?, ?, ?, ?, ?)",
             (new_item_id, note_type_id, current_time, current_time, new_key, library_id)),
            
            # Add note content
            ("INSERT INTO itemNotes (itemID, parentItemID, note) VALUES (?, ?, ?)",
             (new_item_id, parent_id, note_text))
        ]
        
        # Handle tags if provided
        if tags:
            # Get next tag ID
            max_tag_result = self._execute_read("SELECT MAX(tagID) as max_id FROM tags")
            next_tag_id = (max_tag_result[0]['max_id'] or 0) + 1
            
            for tag in tags:
                # Create tag if it doesn't exist
                operations.append(
                    ("INSERT OR IGNORE INTO tags (tagID, name) VALUES (?, ?)",
                     (next_tag_id, tag))
                )
                
                # Link tag to note
                operations.append(
                    ("INSERT INTO itemTags (itemID, tagID, type) VALUES (?, (SELECT tagID FROM tags WHERE name = ?), ?)",
                     (new_item_id, tag, 0))
                )
                next_tag_id += 1
        
        # Execute operations
        result = self._execute_write(operations)
        
        if result["status"] == "success":
            return {
                "status": "success",
                "note_key": new_key,
                "note_id": new_item_id
            }
        else:
            return result
    
    def get_pdf_content(self, item_key: str) -> Dict[str, Any]:
        """Get PDF content for an item."""
        # Get item ID
        item_result = self._execute_read("SELECT itemID FROM items WHERE key = ?", (item_key,))
        if not item_result:
            return {"success": False, "error": "Item not found"}
        
        item_id = item_result[0]['itemID']
        
        # Find PDF attachment
        attachment_query = """
            SELECT i.key, ia.path
            FROM items i
            JOIN itemAttachments ia ON i.itemID = ia.itemID
            WHERE ia.parentItemID = ? AND ia.contentType = 'application/pdf'
            ORDER BY i.dateAdded
            LIMIT 1
        """
        attachments = self._execute_read(attachment_query, (item_id,))
        
        if not attachments:
            return {"success": False, "error": "No PDF attachment found"}
        
        attachment_key = attachments[0]['key']
        
        # Try to read PDF file
        pdf_path = self.storage_path / attachment_key
        
        # Look for PDF files in the attachment directory
        if pdf_path.is_dir():
            pdf_files = list(pdf_path.glob("*.pdf"))
            if not pdf_files:
                return {"success": False, "error": "PDF file not found in storage"}
            pdf_file = pdf_files[0]
        else:
            return {"success": False, "error": "Attachment directory not found"}
        
        # Extract text from PDF
        try:
            with open(pdf_file, 'rb') as f:
                pdf_reader = PdfReader(f)
                text_content = ""
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
            
            return {
                "success": True,
                "text_content": text_content,
                "attachment_key": attachment_key,
                "page_count": len(pdf_reader.pages)
            }
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return {
                "success": False,
                "error": f"Failed to extract text from PDF: {str(e)}"
            }

# Initialize database
try:
    db_path = os.environ.get('ZOTERO_DB_PATH', '~/Zotero/zotero.sqlite')
    db = ZoteroDatabase(db_path)
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)

@mcp.tool()
def search_papers(tags: List[str] = None, query: str = None) -> dict:
    """Search through Zotero papers based on tags and/or text.
    
    Args:
        tags: List of tags to filter by
        query: Search query to filter by title and other fields
    """
    try:
        results = db.search_items(query=query, tags=tags)
        
        # Process results to match API format
        processed_items = []
        for item in results:
            processed_item = {
                'key': item['key'],
                'title': item['title'] or 'Unknown Title',
                'authors': [{'firstName': c['firstName'], 'lastName': c['lastName'], 'creatorType': c['creatorType']} 
                           for c in item['creators']],
                'year': item['date'].split('-')[0] if item['date'] else None,
                'tags': item['tags'],
                'abstract': item['abstract'],
                'url': item['url'],
                'item_type': item['itemType']
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
        notes = db.get_item_notes(item_key)
        return {
            "notes": [{
                "key": note["key"],
                "text": note["note"] or "",
                "tags": note["tags"],
                "title": note.get("title", "")
            } for note in notes]
        }
    except Exception as e:
        logger.error(f"Error getting notes: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
def get_paper(item_key: str) -> Dict[str, Any]:
    """Get details for a specific paper."""
    try:
        item = db.get_item_by_key(item_key)
        if not item:
            return {"status": "error", "message": "Paper not found"}
        
        processed_item = {
            'key': item['key'],
            'title': item['title'] or 'Unknown Title',
            'authors': [{'firstName': c['firstName'], 'lastName': c['lastName'], 'creatorType': c['creatorType']} 
                       for c in item['creators']],
            'year': item['date'].split('-')[0] if item['date'] else None,
            'tags': item['tags'],
            'abstract': item['abstract'],
            'url': item['url'],
            'item_type': item['itemType']
        }
        return {"status": "success", "item": processed_item}
    except Exception as e:
        logger.error(f"Error getting paper: {str(e)}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
def add_note(item_key: str, note_text: str, tags: List[str] = None) -> dict:
    """Add a note to a specific paper."""
    try:
        result = db.add_note(item_key, note_text, tags)
        
        if result["status"] == "success":
            # Get paper title for response
            paper = db.get_item_by_key(item_key)
            paper_title = paper['title'] if paper else "Unknown Paper"
            
            return {
                "status": "success",
                "note_key": result["note_key"],
                "paper_title": paper_title
            }
        else:
            return result
            
    except Exception as e:
        logger.error(f"Error adding note: {str(e)}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
def get_pdf_content(item_key: str) -> dict:
    """Get the PDF content for a given item.
    
    Args:
        item_key: The Zotero item key
    """
    try:
        return db.get_pdf_content(item_key)
    except Exception as e:
        logger.error(f"Error getting PDF content: {e}")
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == "__main__":
    #load_dotenv()
    #
    #required_env_vars = ['ZOTERO_DB_PATH']
    #missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    #
    #if missing_vars:
    #    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    #    logger.error("Set ZOTERO_DB_PATH to your zotero.sqlite file path")
    #    exit(1)
    
    mcp.run()
