import pytest
from unittest.mock import Mock, patch
from zotero_mcp.server import search_papers, get_paper_notes, add_note, request_summary

# Mock data
MOCK_ITEMS = [
    {
        "data": {
            "key": "ABC123",
            "title": "Test Paper",
            "tags": [{"tag": "test"}],
            "date": "2024",
            "creators": [{"firstName": "John", "lastName": "Doe"}]
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

@pytest.fixture
def mock_zotero():
    with patch('zotero_mcp.server.zot') as mock_zot:
        mock_zot.top.return_value = MOCK_ITEMS
        mock_zot.children.return_value = MOCK_NOTES
        mock_zot.item_template.return_value = {"note": "", "tags": []}
        mock_zot.create_items.return_value = {"successful": {"0": {"key": "NEW123"}}}
        mock_zot.item.return_value = MOCK_ITEMS[0]
        mock_zot.update_item.return_value = None
        yield mock_zot

def test_search_papers(mock_zotero):
    # Test search with no parameters
    result = search_papers()
    assert len(result["items"]) == 1
    assert result["items"][0]["key"] == "ABC123"

    # Test search with tag
    result = search_papers(tags=["test"])
    assert len(result["items"]) == 1

    # Test search with query
    result = search_papers(query="Test")
    assert len(result["items"]) == 1

    # Test search with non-matching query
    result = search_papers(query="nonexistent")
    assert len(result["items"]) == 0

def test_get_paper_notes(mock_zotero):
    result = get_paper_notes("ABC123")
    assert len(result["notes"]) == 1
    assert result["notes"][0]["key"] == "NOTE123"
    assert result["notes"][0]["text"] == "Test note content"

def test_add_note(mock_zotero):
    result = add_note("ABC123", "New note", tags=["test"])
    assert result["status"] == "success"
    assert result["note_key"] == "NEW123"

def test_request_summary(mock_zotero):
    result = request_summary("ABC123")
    assert result["status"] == "success"
    assert result["message"] == "Summary requested"
    mock_zotero.update_item.assert_called_once() 