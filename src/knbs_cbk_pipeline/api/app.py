from __future__ import annotations
from fastapi import FastAPI
from knbs_cbk_pipeline.api.routers.indicators import router as indicators_router

def create_app() -> FastAPI:
    app = FastAPI(title="KNBS CBK Pipeline API", version="0.2.0")
    app.include_router(indicators_router)

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

app = create_app()
