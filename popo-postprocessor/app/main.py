from fastapi import FastAPI
from pydantic import BaseModel

from app.pipeline import PopoPipeline


class PopoRequest(BaseModel):
    bucket: str
    source_bucket: str | None = None
    prefix: str
    artifacts: dict[str, str]
    outputs: dict[str, str]


app = FastAPI(title="MinerU-Popo Postprocessor")
pipeline = PopoPipeline()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/postprocess")
def postprocess(request: PopoRequest) -> dict[str, str]:
    return pipeline.run(request)
