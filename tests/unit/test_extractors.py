"""
Extractors are tested against mocked HTTP responses, never live network
calls — this is what makes the test suite deterministic and runnable in
CI/sandboxed environments without egress to centralbank.go.ke.

Uses respx (httpx-native mocking) since our HTTP client is httpx, not requests.
"""
import json
from pathlib import Path

import httpx
import respx

from knbs_cbk_pipeline.ingestion.cbk_extractor import CBKExtractor
from knbs_cbk_pipeline.ingestion.knbs_extractor import KNBSExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"

CBK_FX_SOURCE = {
    "id": "cbk_fx_rates",
    "extractor": "cbk_extractor",
    "fetch_mode": "api_json",
    "endpoint": "https://api.frankfurter.dev/v2/latest",
    "params": {"providers": "CBK", "base": "USD"},
}

CBK_HTML_SOURCE = {
    "id": "cbk_key_rates",
    "extractor": "cbk_extractor",
    "fetch_mode": "html_scrape",
    "endpoint": "https://www.centralbank.go.ke/",
}

KNBS_CPI_SOURCE = {
    "id": "knbs_cpi",
    "extractor": "knbs_extractor",
    "fetch_mode": "file_download",
    "endpoint": "https://www.knbs.or.ke/download/consumer-price-index-cpi/",
    "format": "xlsx",
}


@respx.mock
def test_cbk_extractor_fetches_fx_rates_json():
    fixture = json.loads((FIXTURES / "cbk_fx_rates_response.json").read_text())
    respx.get("https://api.frankfurter.dev/v2/latest").mock(
        return_value=httpx.Response(200, json=fixture, headers={"content-type": "application/json"})
    )

    with CBKExtractor() as extractor:
        result = extractor.fetch(CBK_FX_SOURCE)

    assert result.source_id == "cbk_fx_rates"
    assert result.content_type == "application/json"
    parsed = json.loads(result.content)
    assert parsed["rates"]["KES"] == 129.31


@respx.mock
def test_cbk_extractor_fetches_key_rates_html():
    sample_html = """
    <table>
      <tr><td>Central Bank Rate</td><td>13.00%</td><td>05/06/2024</td></tr>
      <tr><td>Inflation Rate</td><td>5.1%</td><td>May,2024</td></tr>
    </table>
    """
    respx.get("https://www.centralbank.go.ke/").mock(
        return_value=httpx.Response(200, text=sample_html, headers={"content-type": "text/html"})
    )

    with CBKExtractor() as extractor:
        result = extractor.fetch(CBK_HTML_SOURCE)

    assert result.content_type == "text/html"
    assert b"Central Bank Rate" in result.content


@respx.mock
def test_knbs_extractor_downloads_file():
    respx.get("https://www.knbs.or.ke/download/consumer-price-index-cpi/").mock(
        return_value=httpx.Response(
            200,
            content=b"fake-xlsx-bytes",
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        )
    )

    with KNBSExtractor() as extractor:
        result = extractor.fetch(KNBS_CPI_SOURCE)

    assert result.source_id == "knbs_cpi"
    assert result.content == b"fake-xlsx-bytes"
    assert result.metadata["declared_format"] == "xlsx"


@respx.mock
def test_extractor_retries_then_raises_on_persistent_failure():
    route = respx.get("https://api.frankfurter.dev/v2/latest")
    route.mock(return_value=httpx.Response(500))

    with CBKExtractor() as extractor:
        try:
            extractor.fetch(CBK_FX_SOURCE)
            assert False, "expected an exception after exhausting retries"
        except httpx.HTTPStatusError:
            pass

    # retried up to the configured stop_after_attempt(4)
    assert route.call_count == 4
