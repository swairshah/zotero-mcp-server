import sys
from unittest.mock import MagicMock

mock_zotero = MagicMock()
mock_zotero.zotero = MagicMock()

sys.modules['pyzotero'] = mock_zotero
