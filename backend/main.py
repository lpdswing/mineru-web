import gc
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.api import auth_router, upload_router, files_router, folders_router, parsed_router, settings_router, health_router
from app.api import stats
from contextlib import asynccontextmanager

def clean_memory():
    gc.collect()

@asynccontextmanager
async def life_span(app: FastAPI):
    app.state.predictor = None
    yield
    clean_memory()


app = FastAPI(title="MinerU 文档解析系统 API", lifespan=life_span)

# 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)



app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(files_router, prefix="/api", tags=["files"])
app.include_router(folders_router, prefix="/api", tags=["folders"])
app.include_router(parsed_router, prefix="/api", tags=["parsed"])
app.include_router(settings_router, prefix="/api", tags=["settings"])
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(stats.router, prefix="/api", tags=["stats"])

@app.get("/ping")
def ping():
    return {"msg": "pong"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
