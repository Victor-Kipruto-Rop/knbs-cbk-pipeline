import httpx
import pytest
import respx
from knbs_cbk_pipeline.ingestion.knbs_extractor import KNBSExtractor

SOURCE = {"id": "knbs_cpi", "format": "xlsx", "endpoint": "https://www.knbs.or.ke/download/cpi/", "download_link_keywords": ["consumer price index"]}

@respx.mock
def test_knbs_landing_page_resolves_and_validates_xlsx():
    respx.get(SOURCE["endpoint"]).mock(return_value=httpx.Response(200, text='<html><a href="/files/cpi.xlsx">Download Consumer Price Index</a></html>', headers={"content-type": "text/html"}))
    respx.get("https://www.knbs.or.ke/files/cpi.xlsx").mock(return_value=httpx.Response(200, content=b"PK\x03\x04valid-test-fixture", headers={"content-type": "application/octet-stream"}))
    with KNBSExtractor() as extractor:
        result = extractor.fetch(SOURCE)
    assert result.content.startswith(b"PK")
    assert result.source_url.endswith("/files/cpi.xlsx")
    assert result.metadata["validated_extension"] == ".xlsx"

@respx.mock
def test_knbs_rejects_html_200_without_download_link():
    respx.get(SOURCE["endpoint"]).mock(return_value=httpx.Response(200, text="<html><body>Temporarily unavailable</body></html>"))
    with KNBSExtractor() as extractor, pytest.raises(ValueError, match="did not expose"):
        extractor.fetch(SOURCE)

@respx.mock
def test_knbs_rejects_invalid_xlsx_signature():
    respx.get(SOURCE["endpoint"]).mock(return_value=httpx.Response(200, content=b"not an excel file", headers={"content-type": "application/octet-stream"}))
    with KNBSExtractor() as extractor, pytest.raises(ValueError, match="not a valid"):
        extractor.fetch(SOURCE)
