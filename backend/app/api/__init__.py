from .upload import router as upload_router
from .files import router as files_router
from .folders import router as folders_router
from .parsed import router as parsed_router
from .settings import router as settings_router
from .health import router as health_router
from .auth import router as auth_router
from . import stats

routers = [
    auth_router,
    upload_router,
    files_router,
    folders_router,
    parsed_router,
    settings_router,
    health_router,
    stats.router,  # 注册 stats 路由
]
