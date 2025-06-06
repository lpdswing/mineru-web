# MinerU 文档解析系统后端

基于 FastAPI 的后端服务，支持文档上传、解析、导出等功能。

## 启动方式

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```


## 基础接口
- `GET /ping` 健康检查

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