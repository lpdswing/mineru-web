# Worker 并发调度设计

## 背景

MinerU API 可以通过 `mineru-router` 使用多 GPU 并行推理，但当前 `mineru-web` 的 worker 在每个进程内是串行处理 Redis Stream 消息的。`WORKER_REPLICAS` 可以通过增加 worker 容器数量提高吞吐，但单个 worker 容器内部没有并发控制。

当前的 `WORK_BATCH` 只表示一次从 Redis 读取多少条消息；读出来以后还是按 `for` 循环一条一条同步解析。因此它不是实际并发控制项。

这次目标是用一个简单、静态、可配置的并发上限，把 worker 的提交能力调到 MinerU API 可承载范围内。这个设计不做动态容量探测，也不引入自动重试、死信队列或 Redis pending 消息回收。

## 目标

- 新增单 worker 内部并发配置：`WORKER_CONCURRENCY`。
- 总并发模型保持简单：

  ```text
  总解析并发 = WORKER_REPLICAS * WORKER_CONCURRENCY
  ```

- 默认值保持保守：不配置时，一个 worker 容器一次只处理一个任务。
- worker 不提前抢占超过自己空闲执行槽数量的 Redis 消息。
- 单个任务失败不能阻塞其他正在执行的任务。
- 失败语义保持简单：解析失败后文件状态标记为 `parse_failed`，这条 Redis 消息处理结束后仍然 ack。

## 非目标

- 不做自动重试。
- 不做死信队列。
- 不做 Redis pending entry reclaim。
- 不从 MinerU health/status 接口动态推断容量。
- 不把 Redis、SQLAlchemy、MinIO、HTTP client 改成 async。
- 不在本次加入 Prometheus 指标。

## 配置

新增：

```text
WORKER_CONCURRENCY=1
```

规则：

- 未设置、非法值、小于 1 的值，都回退到 `1`。
- `WORKER_REPLICAS` 继续表示 worker 容器数量。
- `WORKER_CONCURRENCY` 表示单个 worker 进程内最多同时处理多少个解析任务。
- `WORK_BATCH` 不进入新的调度模型，也不作为推荐调参入口。

多 GPU 部署示例：

```text
WORKER_REPLICAS=2
WORKER_CONCURRENCY=2
MINERU_API_USE_ASYNC_TASKS=1
```

这表示 worker 侧一共有 4 个解析执行槽。

`MINERU_API_USE_ASYNC_TASKS=1` 只控制调用 MinerU API 的协议模式：从同步 `/file_parse` 切换为 `/tasks` 提交、轮询、取结果。它本身不增加 worker 并发。

## Worker 调度模型

每个 worker 进程内部创建一个线程池：

```python
ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)
```

主循环维护当前正在执行的任务集合 `in_flight`。每轮先回收已完成任务，再根据空闲槽位读取新消息：

```text
free_slots = WORKER_CONCURRENCY - len(in_flight)
if free_slots > 0:
    从 Redis 最多读取 free_slots 条消息
    每条消息提交到线程池
```

这样 worker 只会领取自己马上能开始处理的任务，不会把大量消息提前占住。多个 worker 副本之间也能继续通过 Redis consumer group 分摊任务。

## 任务生命周期

每条 Redis 消息的生命周期：

```text
XREADGROUP -> 提交到线程池 -> process_task -> future 完成 -> XACK
```

每个任务线程自己创建数据库 session：

```python
with get_db_context() as db:
    process_task(task_data, db)
```

`ParserService`、`MineruApiClient`、MinIO 操作都留在任务线程内部执行。SQLAlchemy session 不跨线程共享。

成功时：

- parser 按现有逻辑保存解析结果和 MinIO artifacts。
- worker ack 对应 Redis 消息。

失败时：

- 文件状态按现有语义标记为 `parse_failed`。
- worker 记录错误日志。
- worker 仍然 ack 对应 Redis 消息。
- 其他正在执行的任务不受影响。

## 退出行为

正常中断时，worker 停止读取新消息，并等待已经提交到线程池的任务完成后退出。这样保留现有的近似 at-most-once 行为：已经开始处理的任务尽量跑完并 ack。

如果容器被强制杀掉，正在执行的任务仍可能中断。用 Redis pending reclaim 处理这种情况不在本次范围内。

## 日志

启动时记录：

```text
Worker Consumer Name: worker_...
WORKER_CONCURRENCY=N
```

调度循环中可以低频记录：

```text
in_flight=X free_slots=Y received=Z
```

单任务日志保持当前风格：

```text
Processing task: ...
Processing file ...
File ... processed successfully
Error processing task ...
Task ... processed and acknowledged
```

## 测试

新增 worker 调度测试，使用 fake Redis 和 fake task processor，不调用真实 MinerU 推理：

- `WORKER_CONCURRENCY=1` 时，同一时间最多 1 个任务运行。
- `WORKER_CONCURRENCY=3` 时，同一时间最多 3 个任务运行。
- Redis 每轮读取数量不超过空闲槽位。
- 任务 future 完成以后才 ack。
- 失败任务也会 ack，且不会阻塞其他正在执行的任务。
- 非法 `WORKER_CONCURRENCY` 会回退到 `1`。

现有 parser 和 MinerU API client 测试继续保持通过。

## 部署建议

对已知容量的 MinerU API router，配置时满足：

```text
WORKER_REPLICAS * WORKER_CONCURRENCY <= MinerU parse slot capacity
```

建议从保守值开始调大，观察 GPU 利用率、MinerU 队列等待和超时情况。

多 GPU 部署推荐开启：

```text
MINERU_API_USE_ASYNC_TASKS=1
```

这样每个 worker 执行槽不会长时间挂在一个同步 `/file_parse` HTTP 请求上，而是使用 MinerU 的任务提交、轮询和取结果接口。
