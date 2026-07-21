"""A1 Buyer Agent process entrypoint.

The buyer owns supplier discovery, direct A2A RFQs, deterministic validation,
ranking and the human-facing API. Trusted Infrastructure remains a control
plane and never negotiates or selects a quote.
"""

from fastapi import FastAPI

from sber_a2a.api import create_app
from sber_a2a.config import Settings
from sber_a2a.container import Container


def create_a1_app(container: Container | None = None) -> FastAPI:
    return create_app(container)


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(
        create_a1_app(),
        host=settings.app_host,
        port=settings.app_port,
    )


app = create_a1_app()
