import pytest
from unittest.mock import Mock, patch
from zotero_mcp.server import search_papers, get_paper_notes, add_note, request_summary, get_paper, get_pdf_content

# Mock data
MOCK_ITEMS = [
    {
        "key": "ABC123",
        "data": {
            "key": "ABC123",
            "title": "Test Paper",
            "tags": [{"tag": "test"}],
            "date": "2024",
            "creators": [{"firstName": "John", "lastName": "Doe"}],
            "itemType": "journalArticle",
            "abstractNote": "This is a test abstract"
        },
        "links": {
            "attachment": {
                "href": "/items/PDF123",
                "attachmentType": "application/pdf"
            }
        }
    }
]

MOCK_NOTES = [
    {
        "key": "NOTE123",
        "data": {
            "itemType": "note",
            "note": "Test note content",
            "tags": [{"tag": "test"}]
        }
    }
]

MOCK_CHILDREN = [
    {
        "key": "PDF456",
        "data": {
            "itemType": "attachment",
            "contentType": "application/pdf"
        }
    }
]

@pytest.fixture
def mock_zotero():
    with patch('zotero_mcp.server.zot') as mock_zot:
        mock_zot.items.return_value = MOCK_ITEMS
        mock_zot.children.return_value = MOCK_NOTES
        mock_zot.item_template.return_value = {"note": "", "tags": []}
        mock_zot.create_items.return_value = {"successful": {"0": {"key": "NEW123"}}}
        mock_zot.item.return_value = MOCK_ITEMS[0]
        mock_zot.update_item.return_value = None
        mock_zot.file.return_value = b"PDF content"
        yield mock_zot

def test_search_papers(mock_zotero):
    """Test the search_papers function."""
    # Test searching by tags only
    result = search_papers(tags=['tag1'])
    assert result['status'] == "success"
    assert len(result['items']) == 1
    assert result['items'][0]['title'] == 'Test Paper'

    # Test searching by query only
    result = search_papers(query='Test Paper')
    assert result['status'] == "success"
    assert len(result['items']) == 1
    assert result['items'][0]['title'] == 'Test Paper'

    # Test searching by both tags and query
    result = search_papers(tags=['tag1'], query='Test Paper')
    assert result['status'] == "success"
    assert len(result['items']) == 1
    assert result['items'][0]['title'] == 'Test Paper'

    # Test searching with no parameters
    result = search_papers()
    assert result['status'] == "success"
    assert len(result['items']) == 1

def test_get_paper(mock_zotero):
    result = get_paper("ABC123")
    assert result["status"] == "success"
    assert result["item"]["title"] == "Test Paper"
    assert result["item"]["key"] == "ABC123"

def test_get_paper_notes(mock_zotero):
    result = get_paper_notes("ABC123")
    assert len(result["notes"]) == 1
    assert result["notes"][0]["key"] == "NOTE123"
    assert result["notes"][0]["text"] == "Test note content"

def test_add_note(mock_zotero):
    result = add_note("ABC123", "New note", tags=["test"])
    assert result["status"] == "success"
    assert result["note_key"] == "NEW123"

def test_get_pdf_content_from_links(mock_zotero):
    result = get_pdf_content("ABC123")
    assert result["success"] == True
    assert result["content"] == b"PDF content"
    assert result["attachment_key"] == "PDF123"

def test_get_pdf_content_from_children(mock_zotero):
    # Remove attachment from links and set up children with PDF
    mock_item = MOCK_ITEMS[0].copy()
    mock_item["links"] = {}
    mock_zotero.item.return_value = mock_item
    mock_zotero.children.return_value = MOCK_CHILDREN
    
    result = get_pdf_content("ABC123")
    assert result["success"] == True
    assert result["content"] == b"PDF content"
    assert result["attachment_key"] == "PDF456"

def test_request_summary(mock_zotero):
    result = request_summary("ABC123")
    assert result["status"] == "success"
    assert result["message"] == "Summary requested"
    mock_zotero.update_item.assert_called_once()