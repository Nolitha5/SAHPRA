"""Start the API (and the built dashboard, if present).

    python -m app.api              # from the member2-rag folder
"""

from __future__ import annotations

import uvicorn

from app.api.server import create_app
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    app = create_app(settings=settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="warning")


if __name__ == "__main__":
    main()
