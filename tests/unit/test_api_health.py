from fastapi.testclient import TestClient
from knbs_cbk_pipeline.api.app import app

def test_health_endpoint_reports_liveness():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
