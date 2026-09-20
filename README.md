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

无需手动安装依赖，脚本内嵌依赖声明（PEP 723），用 [uv](https://docs.astral.sh/uv/) 直接运行：
`uv run phpredisadmin_mcp.py`

## 配置（opencode）

`~/.config/opencode/opencode.json`：

```json
{
  "mcp": {
    "phpredisadmin": {
      "type": "local",
      "command": ["uv", "run", "/path/to/mcp-phpredisadmin/phpredisadmin_mcp.py"],
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

## 已知限制

- 不支持 TTL 设置（phpRedisAdmin 页面本身能力有限）
- zset 导出不带 score；list 只能追加/按索引覆写
- `redis_export` 在 key 极多时会拉全量数据
