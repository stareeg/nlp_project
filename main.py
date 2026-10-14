from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from detector import LawReferenceDetector


class LawLink(BaseModel):
    law_id: int
    article: Optional[str] = None
    point_article: Optional[str] = None
    subpoint_article: Optional[str] = None


class LinksResponse(BaseModel):
    links: List[LawLink]


class TextRequest(BaseModel):
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = LawReferenceDetector.cached(Path(__file__).parent / "law_aliases.json")
    yield


def get_detector(request: Request) -> LawReferenceDetector:
    return request.app.state.detector


app = FastAPI(
    title="Law Links Service",
    description="Сервис для выделения юридических ссылок из текста",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/detect")
async def get_law_links(data: TextRequest, detector: LawReferenceDetector = Depends(get_detector)) -> LinksResponse:
    links = [
        LawLink(
            law_id=link.law_id,
            article=link.article,
            point_article=link.point_article,
            subpoint_article=link.subpoint_article,
        )
        for link in detector.detect(data.text)
    ]
    return LinksResponse(links=links)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8978)
