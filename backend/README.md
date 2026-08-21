# MinerU 文档解析系统后端

基于 FastAPI 的后端服务，支持文档上传、解析、导出等功能。

## 启动方式

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```


## 基础接口
- `GET /ping` 健康检查

## 数据库（SQLite / PostgreSQL 可切换）

系统通过环境变量 `DATABASE_URL` 切换数据库，**默认使用 SQLite**，无需任何额外配置：

```bash
# 默认（不设置即用 SQLite）
# DATABASE_URL 缺省 -> sqlite:///./mineru.db
```

切换到 PostgreSQL，只需设置连接串（驱动用 `psycopg2`）后执行迁移：

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/mineru"
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000
```

说明：
- `postgres://` 会被自动规范为 `postgresql://`，裸 `postgresql://`（未带 `+驱动`）也会自动补上 `+psycopg2`，因此也可直接写 `postgresql://user@host/db`。
- PostgreSQL 模式需要 `psycopg2-binary`（已加入 `requirements.txt`）。
- 表结构、字段与现有 SQLite 设计完全一致，由同一套 Alembic 迁移生成，可随时切回 SQLite（改回 `DATABASE_URL` 即可）。

## 目录结构建议
```
backend/
  main.py           # FastAPI 主入口
  README.md         # 项目说明
  requirements.txt  # 依赖
  app/              # 业务代码（推荐后续拆分）
    api/            # 路由
    models/         # 数据模型
    services/       # 业务逻辑
    utils/          # 工具
    ...
``` 

# minio

```
mc alias set minio http://127.0.0.1:9000 minioadmin minioadmin
# 设置mds桶为public 
mc anonymous set download minio/mds
```