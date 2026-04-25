# pyWork 评论系统设计文档

> 版本：v1.0  
> 更新日期：2026-04-23  
> 状态：设计阶段

---

## 1. 概述

### 1.1 功能定位
为博客（blog）、微博（microblog）、笔记（notes）三个内容模块提供统一的评论系统，支持楼中楼回复，需作者审核后可见。

### 1.2 核心约束
| 约束 | 说明 |
|------|------|
| 不支持游客评论 | 必须登录后才能评论 |
| 审核后可见 | 评论默认 `pending`，作者审核后 `approved` 才展示 |
| 拒绝后保留 | 审核拒绝的评论保留记录（`status=rejected`），提供删除按钮 |
| 审核期间禁止编辑 | `pending` 状态的评论在审核结果出来之前不可修改 |

---

## 2. 数据模型

### 2.1 数据库表

```sql
CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type     TEXT NOT NULL,           -- 'blog' | 'microblog' | 'note'
    target_id       INTEGER NOT NULL,
    parent_id       INTEGER,                 -- NULL=顶级评论，非NULL=楼中楼回复
    author_id       INTEGER NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',  -- pending | approved | rejected
    reviewer_id     INTEGER,                 -- 审核人（作者）ID
    reviewed_at     INTEGER,                 -- 审核时间
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (author_id) REFERENCES users(id),
    FOREIGN KEY (parent_id) REFERENCES comments(id)
);
```

### 2.2 表字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键 |
| `target_type` | TEXT | 被评论内容类型：`blog` / `microblog` / `note` |
| `target_id` | INTEGER | 被评论内容的 ID |
| `parent_id` | INTEGER | 父评论 ID，NULL 表示顶级评论 |
| `author_id` | INTEGER | 评论者用户 ID |
| `content` | TEXT | 评论正文（允许 Markdown） |
| `status` | TEXT | `pending` 待审核 / `approved` 已通过 / `rejected` 已拒绝 |
| `reviewer_id` | INTEGER | 审核人 ID（被评论内容的作者） |
| `reviewed_at` | INTEGER | 审核时间戳 |
| `created_at` | INTEGER | 评论创建时间戳 |
| `updated_at` | INTEGER | 评论更新时间戳 |

### 2.3 索引

```sql
CREATE INDEX IF NOT EXISTS idx_comments_target
    ON comments(target_type, target_id, status);
CREATE INDEX IF NOT EXISTS idx_comments_parent
    ON comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_author
    ON comments(author_id);
CREATE INDEX IF NOT EXISTS idx_comments_status
    ON comments(status);
```

---

## 3. API 设计

### 3.1 评论列表

```
GET /api/comments?target=blog&target_id=5
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target` | string | 是 | `blog` \| `microblog` \| `note` |
| `target_id` | int | 是 | 被评论内容 ID |
| `status` | string | 否 | 默认返回 `approved`；传入 `pending` 供作者查看待审 |

**响应：**
```json
{
  "comments": [
    {
      "id": 1,
      "target_type": "blog",
      "target_id": 5,
      "parent_id": null,
      "author_id": 3,
      "author_name": "Alice",
      "author_avatar": "/static/avatar/default.png",
      "content": "写得很好！",
      "status": "approved",
      "created_at": 1745337600,
      "replies": [
        {
          "id": 2,
          "parent_id": 1,
          "author_id": 4,
          "author_name": "Bob",
          "content": "同意",
          "status": "approved",
          "created_at": 1745337700,
          "replies": []
        }
      ]
    }
  ],
  "total": 1
}
```

> 注：仅返回 `status=approved` 的顶级评论及其 approved 子评论。`pending` / `rejected` 评论仅作者本人可见。

### 3.2 创建评论

```
POST /api/comments
Content-Type: application/json

{
  "target_type": "blog",
  "target_id": 5,
  "parent_id": null,       // null=顶级评论，数字=回复某条评论
  "content": "写得很详细，收藏了"
}
```

**业务规则：**
- 必须登录，未登录返回 401
- `target_type` / `target_id` 需对应真实存在的 blog/microblog/note
- `parent_id` 非 NULL 时，父评论必须存在且属于同一 target
- 新评论默认 `status = 'pending'`，立即进入待审核状态
- 楼中楼回复同样需要审核，不继承父评论的审核状态

**响应：**
```json
{
  "id": 10,
  "status": "pending",
  "message": "评论已提交，等待作者审核"
}
```

### 3.3 审核评论（approve / reject）

```
POST /api/comments/{id}/review
Content-Type: application/json

{
  "action": "approve"    // "approve" | "reject"
}
```

**权限：**
- 仅被评论内容的作者可审核（blog/microblog/note 的 `author_id`）
- 非作者返回 403

**审核拒绝后：**
- `status` 更新为 `rejected`，评论内容仍保留
- 在内容作者的"待审评论管理页面"显示该评论，并提供**删除按钮**
- 评论者收到通知（见通知系统设计）

**响应：**
```json
{
  "id": 10,
  "status": "approved",   // 或 "rejected"
  "message": "已审核通过"  // 或 "已拒绝"
}
```

### 3.4 删除评论

```
DELETE /api/comments/{id}
```

**权限：**
- 评论者（`author_id`）可删除自己的评论
- 被评论内容的作者可删除任意评论
- 其他用户不能删除

**业务规则：**
- 删除顶级评论时，一并删除所有子评论（楼中楼）
- 已删除的评论不可恢复

### 3.5 获取待审核评论列表（内容作者）

```
GET /api/comments/pending?target=blog&target_id=5
```

**权限：** 仅内容作者可访问

**响应格式同 3.1，但 `status` 包含 `pending` 和 `rejected` 记录。

---

## 4. 通知系统

### 4.1 通知类型

| 类型 | 触发时机 | 通知对象 |
|------|----------|----------|
| `comment_pending` | 用户提交评论 | 内容作者 |
| `comment_approved` | 作者审核通过 | 评论者 |
| `comment_rejected` | 作者审核拒绝 | 评论者 |
| `reply_pending` | 用户提交楼中楼回复 | 被回复者 + 内容作者 |
| `reply_approved` | 回复审核通过 | 被回复者 |

### 4.2 通知存储

复用现有 `cron_logs` 表？不合适。新建 `notifications` 表：

```sql
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    type            TEXT NOT NULL,         -- pending | approved | rejected | reply
    target_type     TEXT,
    target_id       INTEGER,
    comment_id      INTEGER,
    content         TEXT,                   -- 通知摘要（截取前50字）
    is_read         INTEGER DEFAULT 0,
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

> 注：关于通知的具体实现（站内通知 vs 邮件通知），本文档仅设计站内通知。后续可扩展邮件推送。

### 4.3 用户中心通知入口

在用户中心（`/profile`）页面添加**通知消息**标签页，显示：
- 未读通知数量 Badge（角标）
- 通知列表（时间倒序）
- 每条通知包含：类型图标、内容摘要、时间、已读/未读状态
- 点击通知跳转对应内容页面（锚点定位到对应评论）

---

## 5. 评论展示页面设计

### 5.1 各内容详情页底部评论区

每个内容详情页（博客正文页、微博详情页、笔记详情页）底部统一添加评论区块：

```
┌─────────────────────────────────────────┐
│ 评论区 (3)                              │
├─────────────────────────────────────────┤
│ [头像] Alice    2026-04-23 14:00        │
│ 这篇文章写得非常详细，学到了很多。        │
│                         [回复] [审核中]  │
│  ─────────────────────────────────────  │
│   [头像] Bob     2026-04-23 14:05       │
│   同意，特别是最后那个例子。             │
│                              [审核中]   │
└─────────────────────────────────────────┘
│ 发表评论                                  │
│ [发表评论...]                [提交]     │
└─────────────────────────────────────────┘
```

**展示规则：**
- 所有人可见：`approved` 状态的评论
- 仅评论者可见：`pending` 状态自己的评论（显示"审核中"标签）
- 仅作者可见：`pending` / `rejected` 状态的所有评论（在管理区显示）
- `rejected` 评论对评论者显示被拒绝状态 + **删除按钮**，对其他人隐藏

### 5.2 楼中楼嵌套展示

- 顶级评论最多显示两层嵌套（避免无限嵌套导致 UI 混乱）
- 超过两层时，顶级评论的子评论收起，显示"展开更多回复"

---

## 6. 权限矩阵

| 操作 | 登录用户 | 评论者 | 内容作者 | 管理员 |
|------|----------|--------|----------|--------|
| 查看 approved 评论 | ✅ | ✅ | ✅ | ✅ |
| 查看自己 pending 评论 | — | ✅ | ✅ | ✅ |
| 提交评论 | ✅ | ✅ | ✅ | ✅ |
| 审核评论 | — | — | ✅ | ✅ |
| 删除自己评论 | — | ✅ | ✅ | ✅ |
| 删除任意评论 | — | — | ✅ | ✅ |
| 查看 pending/rejected | — | 仅自己 | 仅自己的内容 | ✅ |

---

## 7. 实现计划

### Phase 1：基础设施
- [ ] 数据库：添加 `comments` 表 + 索引，添加到 `ALLOWED_TABLES`
- [ ] Migration 005：添加 `comments` 表
- [ ] 数据库：添加 `notifications` 表
- [ ] Migration 006：添加 `notifications` 表

### Phase 2：评论 CRUD
- [ ] `plugins/comments/plugin.py`（新建独立评论插件，或内嵌到各插件）
- [ ] 评论列表 API（分页、嵌套结构）
- [ ] 创建评论 API（含楼中楼 parent_id 校验）
- [ ] 审核评论 API（approve/reject，含 author 权限校验）
- [ ] 删除评论 API（含权限校验）
- [ ] 用户待审评论管理页面

### Phase 3：通知系统
- [ ] 通知写入（评论提交/审核通过/审核拒绝/回复）
- [ ] 通知列表 API
- [ ] 标记已读 API
- [ ] 用户中心通知页面

### Phase 4：UI 集成
- [ ] 博客详情页评论区块
- [ ] 微博详情页评论区块
- [ ] 笔记详情页评论区块
- [ ] 用户中心通知入口 + Badge

---

## 8. 影响评估

| 影响项 | 说明 |
|--------|------|
| 数据库 | 新增 2 表（`comments`、`notifications`），3 个索引 |
| API | 新增 7 个端点 |
| 插件 | 现有 blog/microblog/notes 插件需添加评论展示区块 |
| 模板 | 3 个详情页底部添加评论区 |
| 性能 | 评论列表查询需注意 index，走 `target_type, target_id, status` 复合索引 |
