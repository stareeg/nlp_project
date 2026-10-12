from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, Field

from detector import LawReferenceDetector


BASE_DIR = Path(__file__).resolve().parent


class LawLink(BaseModel):
    law_id: int
    article: str | None = None
    point_article: str | None = None
    subpoint_article: str | None = None


class LinksResponse(BaseModel):
    links: list[LawLink]


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The alias automaton and ambiguity metadata are built once. Requests only
    # scan text and never read files or compile expressions.
    app.state.detector = LawReferenceDetector(BASE_DIR / "law_aliases.json")
    yield
    del app.state.detector


def get_detector(request: Request) -> LawReferenceDetector:
    return request.app.state.detector


app = FastAPI(
    title="Law Links Service",
    description="Сервис для выделения ссылок на нормы российского права",
    version="2.0.0",
    lifespan=lifespan,
)


@app.post("/detect", response_model=LinksResponse)
async def get_law_links(
    data: TextRequest,
    detector: Annotated[LawReferenceDetector, Depends(get_detector)],
) -> LinksResponse:
    parsed = detector.detect(data.text)
    return LinksResponse(
        links=[
            LawLink(
                law_id=item.law_id,
                article=item.article,
                point_article=item.point_article,
                subpoint_article=item.subpoint_article,
            )
            for item in parsed
        ]
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8978)
