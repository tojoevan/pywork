# pyWork 生产环境升级指导书

**版本：** v1.0  |  **日期：** 2026-04-21  |  **维护者：** 代可行

---

## 一、升级前准备

### 1.1 确认当前版本

```bash
cd ~/pyWork
git log --oneline -1
git status
```

### 1.2 备份

```bash
# 数据库热备份（不锁库）
cp data/pywork.db "data/pywork.db.$(date +%Y%m%d%H%M%S).bak"

# 配置目录备份
cp -r data data.bak.$(date +%Y%m%d%H%M%S)

# 代码备份（可选，如需完整回滚）
git bundle create data/pywork.bundle HEAD
```

> ⚠️ **每次升级前必须备份。备份文件放在 data/ 目录下，不要删除。**

---

## 二、升级步骤

### 2.1 拉取最新代码

```bash
cd ~/pyWork
git pull
```

### 2.2 安装依赖

```bash
pip install -e .
```

### 2.3 启动/重启服务

```bash
# systemd（推荐）
sudo systemctl restart pywork

# 或手动重启
pkill -f "uvicorn app.main" && sleep 2
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 >> data/logs/pywork.log 2>&1 &
```

---

## 三、升级后验证

### 3.1 健康检查

```bash
curl -s http://localhost:8000/health | head -5
```

### 3.2 数据库结构验证

```bash
sqlite3 data/pywork.db <<'EOF'
.headers on

-- 检查 FTS5 全文搜索表
SELECT name FROM sqlite_master WHERE type='table' AND name='blog_posts_fts';

-- 检查 FTS 触发器
SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'blog_posts_fts_sync%';

-- 检查日志表
SELECT name FROM sqlite_master WHERE type='table' AND name='app_logs';

-- FTS 记录数与 blog_posts 一致
SELECT
  (SELECT COUNT(*) FROM blog_posts) AS posts,
  (SELECT COUNT(*) FROM blog_posts_fts) AS fts;

-- app_logs 当前行数
SELECT COUNT(*) AS log_entries FROM app_logs;
EOF
```

预期输出：blog_posts_fts、app_logs、3 个触发器全部存在，posts = fts，log_entries > 0。

### 3.3 功能验证

| 功能 | 验证方式 |
|------|---------|
| 首页 | `curl http://localhost:8000/` 返回 200 |
| FTS5 搜索 | 博客页搜索关键词返回结果 |
| 日志页面 | `curl http://localhost:8000/board/logs` 返回 200 |
| 错误码 | 访问不存在的页面返回 404（非 500） |

---

## 四、数据库变更说明

本次升级涉及以下数据库变更（自动执行，无需手动操作）：

### Migration 004 — FTS5 + 日志表

**执行时机：** 首次启动时检测 `_meta` 表，幂等执行。

| 变更 | 说明 |
|------|------|
| 创建 `blog_posts_fts` FTS5 表 | 博客全文搜索索引 |
| 同步已有博客数据到 FTS | INSERT INTO blog_posts_fts SELECT ... |
| 创建 3 个 AFTER 触发器 | INSERT/UPDATE/DELETE 自动同步 FTS |
| 创建 `app_logs` 表 | 结构化日志持久化 |

**触发器列表：**
- `blog_posts_fts_sync_insert` — 插入时同步
- `blog_posts_fts_sync_update` — 更新时同步
- `blog_posts_fts_sync_delete` — 删除时同步

---

## 五、回滚方案

### 5.1 数据库回滚

```bash
# 停止服务
sudo systemctl stop pywork

# 恢复备份
cp data/pywork.db.20260421143000.bak data/pywork.db   # 替换为实际备份文件名

# 重启
sudo systemctl start pywork
```

### 5.2 代码回滚

```bash
# 查看升级前的 commit
git log --oneline -5

# 回退代码
git reset --hard <good-commit-hash>

# 重装依赖（如果依赖有变）
pip install -e .

# 重启
sudo systemctl restart pywork
```

---

## 六、监控与日志

### 6.1 应用日志

```bash
# 实时查看
tail -f data/logs/pywork.log

# 搜索错误
grep -i error data/logs/pywork.log | tail -20

# 查看最近 100 行
tail -100 data/logs/pywork.log
```

### 6.2 SQLite 日志查询

```bash
# 最近 20 条 ERROR 日志
sqlite3 data/pywork.db "SELECT created_at, level, module, message FROM app_logs WHERE level='ERROR' ORDER BY created_at DESC LIMIT 20;"

# 某模块日志
sqlite3 data/pywork.db "SELECT created_at, level, message FROM app_logs WHERE module='auth' ORDER BY created_at DESC LIMIT 20;"

# 关键词搜索
sqlite3 data/pywork.db "SELECT created_at, level, message FROM app_logs WHERE message LIKE '%keyword%' ORDER BY created_at DESC LIMIT 20;"
```

### 6.3 日志页面

访问 `http://your-domain.com/board/logs`（需管理员登录），支持：
- 按级别筛选（DEBUG/INFO/WARNING/ERROR/CRITICAL）
- 按模块筛选（core/auth/blog/microblog/notes/board/mcp/storage/route）
- 关键词搜索（message + traceback 全文）
- 分页浏览（50条/页）
- traceback 折叠

---

## 七、常见问题

### Q1: 升级后 500 错误
```bash
# 查看错误日志
tail -50 data/logs/pywork.log

# 检查数据库是否损坏
sqlite3 data/pywork.db "PRAGMA integrity_check;"
```

### Q2: FTS 搜索结果为空
```bash
# 检查 FTS 表是否存在
sqlite3 data/pywork.db "SELECT COUNT(*) FROM blog_posts_fts;"

# 手动重新同步
sqlite3 data/pywork.db "DELETE FROM blog_posts_fts;
INSERT INTO blog_posts_fts(rowid, title, body, tags)
  SELECT id, title, COALESCE(body,''), COALESCE(tags,'') FROM blog_posts;"
```

### Q3: 服务起不来
```bash
# 检查端口占用
lsof -i :8000

# 检查依赖
pip install -e . --force-reinstall
```

### Q4: app_logs 表不存在
```bash
# 手动创建
sqlite3 data/pywork.db "CREATE TABLE IF NOT EXISTS app_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL DEFAULT 'INFO',
    module TEXT NOT NULL DEFAULT 'core',
    message TEXT NOT NULL,
    context TEXT DEFAULT '',
    traceback TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);"
```

---

## 八、定期维护

### 清理旧日志（/board/logs/cleanup 会自动清理 30 天前）

```bash
# 手动清理 30 天前日志
sqlite3 data/pywork.db "DELETE FROM app_logs WHERE created_at < $(date -v-30d +%s);"

# 清理旧备份文件（保留最近 5 个）
cd data
ls -t pywork.db.*.bak | tail -n +6 | xargs rm -f

# vacuum 数据库（降低文件大小）
sqlite3 data/pywork.db "VACUUM;"
```

---

## 九、服务管理

```bash
# 查看状态
sudo systemctl status pywork

# 启动/停止/重启
sudo systemctl start pywork
sudo systemctl stop pywork
sudo systemctl restart pywork

# 查看启动日志
journalctl -u pywork -f
```

---

## 十、升级检查清单

- [ ] 备份已创建
- [ ] git pull 完成
- [ ] pip install -e . 成功
- [ ] systemctl restart 成功
- [ ] curl /health 返回 200
- [ ] blog_posts_fts 表存在
- [ ] app_logs 表存在且有记录
- [ ] /board/logs 页面可访问
- [ ] 首页正常加载

---

*本指导书随代码更新。每次升级前确认是否有新增数据库变更。*