import pytest
from zotero_mcp.server import search_papers, get_paper_notes, add_note, request_summary, get_paper, get_pdf_content
from zotero_mcp.server import zot
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@pytest.mark.integration
def test_real_search_papers():
    # Test search with no parameters
    result = search_papers()
    assert result["status"] == "success"
    logger.info(f"Found {result['total_results']} papers in total")
    
    # Log details of first few papers
    for item in result["items"][:3]:  # Show first 3 papers
        logger.info(
            f"Paper: '{item['title']}' "
            f"(Key: {item['key']}, "
            f"Year: {item['year']}, "
            f"Tags: {item['tags']})"
        )
    
    # Test search with a tag
    tag_result = search_papers(tags=["your_tag"])
    assert tag_result["status"] == "success"
    logger.info(f"Found {tag_result['total_results']} papers with specified tag")
    
    # Test search with a query
    query_result = search_papers(query="test")
    assert query_result["status"] == "success"
    logger.info(f"Found {query_result['total_results']} papers with query 'test'")
    
    if result["items"]:
        test_item = result["items"][0]
        test_item_key = test_item["key"]
        
        # Test get_paper
        paper_result = get_paper(test_item_key)
        logger.info(f"Retrieved paper details for '{test_item['title']}'")
        assert paper_result["status"] == "success"
        
        # Test get_paper_notes
        notes_result = get_paper_notes(test_item_key)
        logger.info(f"Retrieved notes for paper '{test_item['title']}'")
        assert "notes" in notes_result
        
        # Test adding a note
        note_result = add_note(
            test_item_key,
            "Test note from integration test - please delete",
            tags=["test_integration"]
        )
        logger.info(
            f"Added note to paper '{test_item['title']}'. "
            f"Result: {note_result}"
        )
        assert note_result["status"] == "success"
        
        # Test get_pdf_content
        pdf_result = get_pdf_content(test_item_key)
        logger.info(f"Retrieved PDF content for paper '{test_item['title']}'")
        assert 'success' in pdf_result
        
        # Test requesting a summary
        try:
            summary_result = request_summary(test_item_key)
            logger.info(f"Requested summary for paper '{test_item['title']}'")
            assert summary_result["status"] == "success"
        except ValueError as e:
            logger.error(f"Error requesting summary: {e}")
            # The function raises ValueError on error, so we need to handle it
            pytest.fail(f"request_summary raised ValueError: {e}")