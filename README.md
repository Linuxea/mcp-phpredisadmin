# mcp-phpredisadmin

通过 phpRedisAdmin 的 HTTP 页面操作 Redis 的 MCP server（stdio）。
适用于 Redis 端口不暴露、唯一入口是 phpRedisAdmin 网页的场景。

## 原理

不直连 Redis，而是模拟浏览器调用 phpRedisAdmin 的页面接口：

- `POST export.php`（type=json）→ 读 key / 按 filter 批量导出
- `POST edit.php` → 写 key（string/hash/list/set/zset）
- `POST delete.php` → 删 key
- `GET index.php` → 列 key（解析侧栏链接）
- `GET info.php` → 服务器信息

自动处理 cookie session、表单登录/HTTP Basic、CSRF token（从页面提取后随 POST 提交）。

## 安装

标准 uv 项目布局，首次 clone 后安装依赖：

```bash
uv sync
```

运行（等价入口：`uv run pra-mcp` 或 `uv run python -m pra_mcp`）：

```bash
uv run pra-mcp
```

## 配置（opencode）

`~/.config/opencode/opencode.json`：

```json
{
  "mcp": {
    "phpredisadmin": {
      "type": "local",
      "command": ["uv", "run", "--project", "/path/to/mcp-phpredisadmin", "pra-mcp"],
      "environment": {
        "PRA_URL": "https://pra.example.com",
        "PRA_USER": "yourname",
        "PRA_PASS": "yourpass",
        "PRA_LOGIN": "basic",
        "PRA_SERVER_ID": "0",
        "PRA_DB": "0"
      }
    }
  }
}
```

环境变量：

| 变量 | 说明 |
|---|---|
| `PRA_URL` | phpRedisAdmin 根地址（必填） |
| `PRA_USER` / `PRA_PASS` | 登录凭据 |
| `PRA_LOGIN` | `basic`（默认，HTTP Basic 或无登录）或 `form`（login.php 表单） |
| `PRA_SERVER_ID` | phpRedisAdmin 配置里的服务器编号，默认 0 |
| `PRA_DB` | Redis db 编号，默认 0 |

## 提供的工具

- `redis_servers()` — 列出 phpRedisAdmin 管理的所有 Redis 实例
- `redis_use_server(s, db)` — 切换到指定实例/db
- `redis_keys(filter)` — 列 key（不取值）
- `redis_get(key)` — 读单个 key（自动识别类型，返回 JSON）
- `redis_export(filter)` — 批量导出 key+值（重操作，慎用）
- `redis_set(key, value, type, hkey?,, index?, score?)` — 写 key
- `redis_delete(key)` — 删 key
- `redis_info()` — 服务器信息

## 已知限制（2026-10 实测 @ redis.chathot.me，均有 live 测试固化）

**假 OK —— 工具返回 OK 但实际未写入**（edit.php 对不满足分支条件的写入静默跳过，但仍渲染成功页）：

- `redis_set(type="list")` 不传 `index`（工具默认值就是空，字段被省略）
- `redis_set(type="hash")` 缺 `hkey`
- `redis_set(type="zset")` 缺 `score`
- `type` 传了非法值

其他：

- list `index=-1`：新版 phpRedisAdmin 文档为 prepend，这台老实例实测为 append
- zset 导出不带 score（export.php 用 zRange）
- `redis_delete` 删不存在的 key 同样返回 OK，无法区分
- `redis_get` 不存在的 key 返回字面量 `null`
- `redis_keys` 的 filter 在这台实例上是客户端子串过滤（服务端忽略 GET filter 参数）；glob（`xxx*`）会匹配不到任何 key；每次查询都拉全量 key 页面（数千 key 时页面很大）
- `redis_export` 全量导出在数千 key 的实例上会超时（服务端 KEYS 全量扫描）
- 不支持 TTL 设置（工具未暴露，phpRedisAdmin 页面本身能力有限）

## 项目结构

```
src/pra_mcp/
├── config.py       # 环境变量 → Config
├── registry.py     # MCPServer 实例（装配锚点）
├── http_client.py  # phpRedisAdmin HTTP 会话/登录/CSRF/当前 server+db
├── parsing.py      # 纯 HTML 解析函数（无 IO，可独立单测）
└── tools/          # 每组工具一个模块
    ├── keys.py     # redis_keys / redis_export
    ├── kv.py       # redis_get / redis_set / redis_delete
    └── cluster.py  # redis_info / redis_servers / redis_use_server
tests/
├── test_parsing.py     # 纯函数单测，离线可跑
└── test_tools_live.py  # 真实 phpRedisAdmin 集成测试（见下）
```

## 测试

离线单测（解析函数、工具注册）：

```bash
uv run pytest
```

连真实 phpRedisAdmin 的集成测试（默认 skip，显式开启；`PRA_LIVE` 开关防止误打到生产）：

```bash
PRA_LIVE=1 PRA_URL=https://pra.example.com PRA_USER=... PRA_PASS=... \
    uv run pytest tests/test_tools_live.py
```

集成测试使用 MCP SDK 的 in-memory client（`Client(mcp)`）直连 server 对象，不起子进程、不开端口；只做安全操作（info/keys/读写自建 key），不涉及 flush 等危险命令。
