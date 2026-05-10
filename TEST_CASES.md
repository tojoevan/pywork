# pyWork 测试用例说明

> 生成日期：2026-05-10 | 更新日期：2026-05-10 | 测试框架：pytest + pytest-asyncio | 用例总数：417

---

## 目录

- [公共配置](#公共配置)
- [test_storage.py — 存储引擎](#test_storagepy--存储引擎)
- [test_blog.py — 博客插件](#test_blogpy--博客插件)
- [test_auth.py — 认证插件](#test_authpy--认证插件)
- [test_home_service.py — 首页聚合服务](#test_home_servicepy--首页聚合服务)
- [test_mcp.py — MCP 协议](#test_mcppy--mcp-协议)
- [test_plugins.py — 插件 CRUD](#test_pluginspy--插件-crud)
- [test_comments.py — 评论系统](#test_commentspy--评论系统)
- [test_topic.py — 讨论话题](#test_topicpy--讨论话题)
- [test_llm_config.py — LLM 配置](#test_llm_configpy--llm-配置)
- [test_nav.py — 导航书签](#test_navpy--导航书签)
- [test_board.py — 管理后台](#test_boardpy--管理后台)
- [test_config.py — 配置管理](#test_configpy--配置管理)
- [test_template_engine.py — 模板引擎](#test_template_enginepy--模板引擎)
- [test_utils.py — 工具函数](#test_utilspy--工具函数)
- [test_security.py — 安全功能](#test_securitypy--安全功能)

---

## 公共配置

**文件**: `tests/conftest.py`

提供 4 个 pytest fixture，供所有测试复用：

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `event_loop` | session | 创建独立事件循环，避免异步测试冲突 |
| `db_engine` | function | 临时目录中的 SQLiteEngine，测试结束自动清理 |
| `plugin_context` | function | 基于 `db_engine` 的 PluginContext |
| `plugin_manager` | function | 基于 `db_engine` 的 PluginManager |

---

## test_storage.py — 存储引擎

**路径**: `tests/test_storage.py` | **用例数**: 9 | **测试类型**: 集成测试（真实 SQLite）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_engine_start_stop` | 引擎启动后 mode 为 "sqlite" |
| 2 | `test_put_and_get` | 写入 blog_posts 后能通过 SQL 查询到 |
| 3 | `test_query` | 批量写入后按 status 过滤查询 |
| 4 | `test_delete` | 写入后删除，再查询返回 None |
| 5 | `test_raft_log` | 写入后 Raft 日志有记录，op 为 INSERT/UPDATE |
| 6 | `test_export_import` | export 导出日志，current_index 递增 |
| 7 | `test_microblog_posts_table` | microblog_posts 表的 content 字段读写 |
| 8 | `test_notes_table` | notes 表的 title/body 字段读写 |
| 9 | `test_guestbook_entries_table` | guestbook_entries 表的 nickname/body/email 字段读写 |

---

## test_blog.py — 博客插件

**路径**: `tests/test_blog.py` | **用例数**: 6 | **测试类型**: 集成测试（真实 SQLite + BlogPlugin）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_create_post` | 创建博客文章，验证返回 id/title/status |
| 2 | `test_search_posts` | 创建多篇后搜索，验证 status 过滤 |
| 3 | `test_update_post` | 创建后更新 title 和 status，验证持久化 |
| 4 | `test_mcp_tools` | MCP 工具列表包含 create_post/search_posts/update_post |
| 5 | `test_mcp_resources` | 创建文章后 list_all_posts 资源包含标题 |
| 6 | `test_plugin_manager` | PluginManager 注册插件后能获取工具列表 |

---

## test_auth.py — 认证插件

**路径**: `tests/test_auth.py` | **用例数**: 27 | **测试类型**: 单元测试（Mock Engine）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_generate_captcha` | 生成 4 位数字验证码 |
| 2 | `test_verify_captcha_correct` | 正确验证码验证通过 |
| 3 | `test_verify_captcha_wrong` | 错误验证码返回 False |
| 4 | `test_verify_captcha_expired` | 过期验证码返回 False |
| 5 | `test_hash_password` | PBKDF2-SHA256 哈希 |
| 6 | `test_hash_password_with_salt` | 相同 salt + 密码产生相同哈希 |
| 7 | `test_verify_password_correct` | 正确密码验证通过 |
| 8 | `test_verify_password_wrong` | 错误密码验证失败 |
| 9 | `test_split_password_hash_colon` | 解析冒号分隔格式 |
| 10 | `test_split_password_hash_dollar` | 解析美元符号分隔格式 |
| 11 | `test_register_success` | 正常注册，第一个用户自动成为 admin |
| 12 | `test_register_duplicate_username` | 重复用户名返回错误 |
| 13 | `test_register_duplicate_email` | 重复邮箱返回错误 |
| 14 | `test_register_invalid_captcha` | 无效验证码返回错误 |
| 15 | `test_register_second_user_not_admin` | 第二个用户角色为 user |
| 16 | `test_login_success` | 正确用户名密码登录成功 |
| 17 | `test_login_wrong_password` | 错误密码返回错误 |
| 18 | `test_login_nonexistent_user` | 不存在的用户返回错误 |
| 19 | `test_logout` | 登出后 session 记录被删除 |
| 20 | `test_get_user_by_token` | 有效 token 能获取用户信息 |
| 21 | `test_get_user_by_invalid_token` | 无效 token 返回 None |
| 22 | `test_create_mcp_token` | 创建 MCP Token，长度 43 字符 |
| 23 | `test_list_mcp_tokens` | 列出用户的所有 MCP Token |
| 24 | `test_revoke_mcp_token` | 撤销 Token 后再次撤销返回 False |
| 25 | `test_get_user_by_mcp_token` | 通过 MCP Token 获取用户信息 |
| 26 | `test_generate_token` | 生成 token_urlsafe(32)，长度 43 字符 |
| 27 | `test_generate_token_unique` | 100 个 token 全部唯一 |

---

## test_home_service.py — 首页聚合服务

**路径**: `tests/test_home_service.py` | **用例数**: 19 | **测试类型**: 单元测试（Mock 插件）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_to_dict_post` | post 类型转换，包含 tags |
| 2 | `test_to_dict_microblog` | microblog 类型转换 |
| 3 | `test_to_dict_note` | note 类型转换 |
| 4 | `test_empty_plugins` | 无插件返回空列表 |
| 5 | `test_blog_only` | 仅 blog 插件返回博客数据 |
| 6 | `test_microblog_only` | 仅 microblog 插件返回微博数据 |
| 7 | `test_notes_only` | 仅 notes 插件返回笔记数据 |
| 8 | `test_mixed_feed_sorted_by_time` | 混合内容按时间倒序排列 |
| 9 | `test_limit_respected` | limit 参数生效 |
| 10 | `test_plugin_exception_handled` | 单个插件异常不影响其他插件 |
| 11 | `test_no_board_plugin` | 无 board 插件返回默认值 0 |
| 12 | `test_board_plugin_returns_stats` | board 插件返回正确统计数字 |
| 13 | `test_board_plugin_exception` | board 异常时返回默认值 0 |
| 14 | `test_no_board_plugin` | 无 board 插件返回空列表 |
| 15 | `test_board_plugin_returns_authors` | board 插件返回活跃作者列表 |
| 16 | `test_board_plugin_exception` | board 异常时返回空列表 |
| 17 | `test_all_empty` | 全部为空时各字段为默认值 |
| 18 | `test_all_data_combined` | 多插件数据正确组合 |
| 19 | `test_parallel_execution` | asyncio.gather 并行调用各方法 |

---

## test_mcp.py — MCP 协议

**路径**: `tests/test_mcp.py` | **用例数**: 33 | **测试类型**: 单元测试（内置 Mock MCP Server）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_initialize_returns_protocol_version` | 返回 protocolVersion 2024-11-05 |
| 2 | `test_initialize_returns_capabilities` | 返回 tools/resources/prompts 能力 |
| 3 | `test_initialize_returns_server_info` | 返回 name=pyWork, version=0.1.0 |
| 4 | `test_initialize_ignores_params` | 任意参数都能正常初始化 |
| 5 | `test_list_tools_returns_all_tools` | 返回所有注册工具 |
| 6 | `test_list_tools_namespaced` | 工具名格式为 plugin.tool_name |
| 7 | `test_list_tools_includes_schema` | 包含 inputSchema 和 properties |
| 8 | `test_list_tools_empty_when_no_tools` | 无工具时返回空列表 |
| 9 | `test_call_tool_invalid_name` | 无效名称返回错误 |
| 10 | `test_call_tool_not_found` | 不存在的工具返回错误 |
| 11 | `test_call_tool_plugin_not_found` | 不存在的插件返回错误 |
| 12 | `test_call_tool_with_handler` | 调用 handler 执行并返回结果 |
| 13 | `test_call_tool_with_mcp_call` | 优先使用 mcp_call 方法 |
| 14 | `test_call_tool_exception_handling` | 异常被捕获，isError=True |
| 15 | `test_list_resources_returns_all` | 返回所有注册资源 |
| 16 | `test_list_resources_includes_metadata` | 包含 uri/name/mimeType |
| 17 | `test_list_resources_empty_when_none` | 无资源时返回空列表 |
| 18 | `test_read_resource_invalid_uri` | 无效 URI 返回错误 |
| 19 | `test_read_resource_not_found` | 不存在的资源返回错误 |
| 20 | `test_read_resource_success` | 读取已有资源返回内容 |
| 21 | `test_read_resource_exception_handling` | handler 异常被捕获 |
| 22 | `test_list_prompts_returns_all` | 返回所有注册 Prompt |
| 23 | `test_list_prompts_namespaced` | Prompt 名格式为 plugin.prompt_name |
| 24 | `test_list_prompts_includes_arguments` | 包含参数定义 |
| 25 | `test_get_prompt_invalid_name` | 无效名称返回空 messages |
| 26 | `test_get_prompt_not_found` | 不存在返回错误 |
| 27 | `test_get_prompt_success` | 获取已有 Prompt 返回模板 |
| 28 | `test_get_prompt_template_substitution` | 变量 {{username}} 被替换 |
| 29 | `test_get_prompt_missing_argument` | 缺少参数时保留 {{placeholder}} |
| 30 | `test_unknown_method_raises_error` | 未知方法抛出 ValueError |
| 31 | `test_empty_params_handled` | 空参数正常处理 |
| 32 | `test_full_initialize_then_list_tools` | 完整流程：初始化 → 列出工具 |
| 33 | `test_multiple_plugins_all_registered` | 多插件的 tools/resources/prompts 全部注册 |

---

## test_plugins.py — 插件 CRUD

**路径**: `tests/test_plugins.py` | **用例数**: 38 | **测试类型**: 单元测试（Mock Engine）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_create_post_success` | 创建成功返回 id 和 created=True |
| 2 | `test_create_post_with_tags` | 带标签创建，tags 正确存储 |
| 3 | `test_create_post_default_status` | 不指定 status 默认为 draft |
| 4 | `test_create_post_published` | 指定 published 状态 |
| 5 | `test_create_post_with_author` | 带 author_id 创建 |
| 6 | `test_get_post_success` | 获取已有文章 |
| 7 | `test_get_post_not_found` | 不存在返回 None |
| 8 | `test_list_posts_empty` | 空表返回空列表 |
| 9 | `test_list_posts_multiple` | 列出多篇文章 |
| 10 | `test_list_posts_limit` | limit 参数生效 |
| 11 | `test_update_post_title` | 更新标题 |
| 12 | `test_update_post_content` | 更新内容 |
| 13 | `test_update_post_status` | 更新状态 |
| 14 | `test_update_post_tags` | 更新标签 |
| 15 | `test_update_post_not_found` | 不存在返回错误 |
| 16 | `test_update_post_partial` | 部分更新保留其他字段 |
| 17 | `test_delete_post_success` | 删除后查询返回 None |
| 18 | `test_delete_post_not_found` | 删除不存在的文章幂等成功 |
| 19 | `test_create_note_success` | 创建成功 |
| 20 | `test_create_note_private_by_default` | 默认私有 |
| 21 | `test_create_note_public` | 指定公开 |
| 22 | `test_get_note_success` | 获取已有笔记 |
| 23 | `test_list_notes_by_user` | 按用户过滤 |
| 24 | `test_update_note_title` | 更新标题 |
| 25 | `test_update_note_visibility` | 更新可见性 |
| 26 | `test_delete_note_success` | 删除后查询返回 None |
| 27 | `test_create_microblog_success` | 创建成功 |
| 28 | `test_create_microblog_multiple` | 多条创建 ID 递增 |
| 29 | `test_get_microblog_success` | 获取已有微博 |
| 30 | `test_list_microblog_posts` | 列出多条微博 |
| 31 | `test_delete_microblog_success` | 删除成功 |
| 32 | `test_shared_engine` | 多插件共享引擎，数据隔离 |
| 33 | `test_timestamps_updated` | 更新后 updated_at 递增 |
| 34 | `test_empty_content` | 空内容正常存储 |
| 35 | `test_special_characters_in_title` | 特殊字符原样存储 |
| 36 | `test_unicode_content` | 中文和 emoji 正确存储 |
| 37 | `test_long_content` | 10000 字符长文本正确存储 |
| 38 | `test_empty_tags` | 空标签列表正确存储 |

---

## test_comments.py — 评论系统

**路径**: `tests/test_comments.py` | **用例数**: 35 | **测试类型**: 单元测试（Mock Engine）

### TestCreateComment（评论创建）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_create_comment_success` | 创建评论成功，返回 id 和 pending 状态 |
| 2 | `test_create_comment_not_logged_in` | 未登录返回 401 |
| 3 | `test_create_comment_empty_content` | 空内容返回错误 |
| 4 | `test_create_comment_too_long` | 超过 2000 字返回错误 |
| 5 | `test_create_comment_invalid_target_type` | 无效 target_type 返回错误 |
| 6 | `test_create_comment_target_not_found` | 目标不存在返回错误 |
| 7 | `test_auto_approve_when_content_author` | 内容作者评论自动审核通过 |
| 8 | `test_pending_when_not_content_author` | 非作者评论状态为 pending |
| 9 | `test_create_reply_to_comment` | 回复评论成功 |
| 10 | `test_reply_to_nested_comment_rejected` | 不支持多层嵌套回复 |
| 11 | `test_reply_to_nonexistent_parent` | 回复不存在的评论返回错误 |

### TestReviewComment（评论审核）

| # | 用例名 | 说明 |
|---|--------|------|
| 12 | `test_approve_comment` | 审核通过评论 |
| 13 | `test_reject_comment` | 拒绝评论 |
| 14 | `test_review_not_logged_in` | 未登录返回 401 |
| 15 | `test_review_not_content_author` | 非作者无权审核 |
| 16 | `test_review_already_reviewed` | 已审核的评论返回错误 |
| 17 | `test_review_invalid_action` | 无效 action 返回错误 |
| 18 | `test_review_nonexistent_comment` | 不存在的评论返回错误 |

### TestDeleteComment（评论删除）

| # | 用例名 | 说明 |
|---|--------|------|
| 19 | `test_delete_by_comment_author` | 评论作者可删除 |
| 20 | `test_delete_by_content_author` | 内容作者可删除 |
| 21 | `test_delete_by_admin` | 管理员可删除 |
| 22 | `test_delete_unauthorized` | 无权删除返回错误 |
| 23 | `test_delete_not_logged_in` | 未登录返回 401 |
| 24 | `test_delete_nonexistent` | 不存在的评论返回错误 |

### TestListComments（评论列表）

| # | 用例名 | 说明 |
|---|--------|------|
| 25 | `test_list_approved_comments` | 匿名用户只看 approved 评论 |
| 26 | `test_list_missing_params` | 缺少参数返回错误 |
| 27 | `test_list_invalid_target_type` | 无效类型返回错误 |
| 28 | `test_list_invalid_target_id` | 无效 ID 返回错误 |

### TestPendingComments（待审评论）

| # | 用例名 | 说明 |
|---|--------|------|
| 29 | `test_pending_not_logged_in` | 未登录返回 401 |
| 30 | `test_pending_missing_params` | 缺少参数返回错误 |
| 31 | `test_pending_not_content_author` | 非作者无权查看 |
| 32 | `test_pending_content_author_can_view` | 内容作者可查看待审评论 |

### TestNotifications（通知）

| # | 用例名 | 说明 |
|---|--------|------|
| 33 | `test_list_notifications` | 列出通知 |
| 34 | `test_mark_notification_read` | 标记单条已读 |
| 35 | `test_mark_all_read` | 全部标记已读 |

### TestMCPTollComments（MCP 工具）

| # | 用例名 | 说明 |
|---|--------|------|
| 36 | `test_mcp_list_comments` | MCP 列出已审核评论 |
| 37 | `test_mcp_create_comment_no_token` | 无 token 返回错误 |
| 38 | `test_mcp_create_comment_invalid_token` | 无效 token 返回错误 |
| 39 | `test_mcp_create_comment_empty_content` | 空内容返回错误 |
| 40 | `test_mcp_create_comment_too_long` | 超长内容返回错误 |
| 41 | `test_mcp_create_comment_target_not_found` | 目标不存在返回错误 |
| 42 | `test_mcp_create_comment_success` | MCP 创建评论成功 |
| 43 | `test_mcp_create_comment_as_content_author` | 内容作者自动审核 |
| 44 | `test_mcp_tools_registered` | MCP 工具注册正确 |

### TestCommentsEdgeCases（边界情况）

| # | 用例名 | 说明 |
|---|--------|------|
| 45 | `test_comment_on_microblog` | 微博评论 |
| 46 | `test_comment_on_note` | 笔记评论 |
| 47 | `test_admin_can_review` | 管理员可审核 |
| 48 | `test_plugin_properties` | 插件属性正确 |
| 49 | `test_routes_count` | 路由数量正确 (12) |

---

## test_topic.py — 讨论话题

**路径**: `tests/test_topic.py` | **用例数**: 42 | **测试类型**: 单元测试（Mock Engine）

### TestCreateTopic（创建话题）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_create_topic_success` | 创建话题成功 |
| 2 | `test_create_topic_no_author` | 无作者返回错误 |
| 3 | `test_create_topic_custom_deadline` | 自定义截止时间 |
| 4 | `test_create_topic_mcp` | MCP 创建话题 |
| 5 | `test_create_topic_mcp_invalid_token` | 无效 MCP token 返回错误 |

### TestUpdateTopic（更新话题）

| # | 用例名 | 说明 |
|---|--------|------|
| 6 | `test_update_title` | 更新标题 |
| 7 | `test_update_description` | 更新描述 |
| 8 | `test_update_not_author` | 非作者无权编辑 |
| 9 | `test_update_admin_allowed` | 管理员可编辑 |
| 10 | `test_update_closed_topic` | 已关闭话题不可编辑 |
| 11 | `test_update_nonexistent` | 不存在返回错误 |
| 12 | `test_update_empty_title` | 空标题返回错误 |

### TestReplyTopic（回复话题）

| # | 用例名 | 说明 |
|---|--------|------|
| 13 | `test_reply_success` | 回复成功 |
| 14 | `test_reply_no_author` | 无作者返回错误 |
| 15 | `test_reply_closed_topic` | 已关闭话题不可回复 |
| 16 | `test_reply_nonexistent_topic` | 不存在返回错误 |
| 17 | `test_reply_with_parent` | 嵌套回复 |

### TestVote（投票）

| # | 用例名 | 说明 |
|---|--------|------|
| 18 | `test_upvote_new` | 新增赞成票 |
| 19 | `test_downvote_new` | 新增反对票 |
| 20 | `test_vote_toggle_off` | 重复投票取消 |
| 21 | `test_vote_change` | 切换投票类型 |
| 22 | `test_vote_no_author` | 无作者返回错误 |
| 23 | `test_vote_on_reply` | 对回复投票 |
| 24 | `test_vote_mcp` | MCP 投票 |
| 25 | `test_vote_mcp_invalid_token` | 无效 token 返回错误 |

### TestGetTopicDetail（话题详情）

| # | 用例名 | 说明 |
|---|--------|------|
| 26 | `test_get_existing_topic` | 获取已有话题 |
| 27 | `test_get_nonexistent_topic` | 不存在返回错误 |
| 28 | `test_get_topic_with_replies` | 包含回复列表 |
| 29 | `test_get_topic_with_votes` | 包含投票统计 |
| 30 | `test_remaining_hours` | 剩余时间计算 |

### TestCloseTopic（关闭话题）

| # | 用例名 | 说明 |
|---|--------|------|
| 31 | `test_close_open_topic` | 关闭进行中话题 |
| 32 | `test_close_already_closed` | 已关闭返回错误 |
| 33 | `test_close_nonexistent` | 不存在返回错误 |

### TestListTopics（话题列表）

| # | 用例名 | 说明 |
|---|--------|------|
| 34 | `test_list_empty` | 空列表 |
| 35 | `test_list_multiple` | 多个话题 |
| 36 | `test_list_filter_by_status` | 按状态过滤 |
| 37 | `test_list_with_limit` | limit 生效 |
| 38 | `test_list_remaining_hours` | 包含剩余时间 |

### TestMarkExpired（过期处理）

| # | 用例名 | 说明 |
|---|--------|------|
| 39 | `test_mark_expired` | 标记过期话题为已关闭 |
| 40 | `test_no_expired` | 无过期话题 |

### TestMCPTollTopic（MCP 工具）

| # | 用例名 | 说明 |
|---|--------|------|
| 41 | `test_mcp_tools_count` | 7 个 MCP 工具 |
| 42 | `test_mcp_tool_names` | 工具名称正确 |
| 43 | `test_mcp_call_create` | MCP 创建话题 |
| 44 | `test_mcp_call_list` | MCP 列出话题 |
| 45 | `test_mcp_call_unknown_tool` | 未知工具抛异常 |

### TestTopicPluginProperties（插件属性）

| # | 用例名 | 说明 |
|---|--------|------|
| 46 | `test_plugin_name` | name == "topic" |
| 47 | `test_plugin_version` | version == "0.1.0" |
| 48 | `test_routes_count` | 路由数量 (11) |

---

## test_llm_config.py — LLM 配置

**路径**: `tests/test_llm_config.py` | **用例数**: 24 | **测试类型**: 单元测试（Mock Engine）

### TestMaskApiKey（API Key 脱敏）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_mask_normal_key` | sk-1234****cdef 格式 |
| 2 | `test_mask_short_key` | 短 key 返回 **** |
| 3 | `test_mask_empty_key` | 空 key 返回 **** |
| 4 | `test_mask_none_key` | None 返回 **** |

### TestLLMConfigCRUD（配置 CRUD）

| # | 用例名 | 说明 |
|---|--------|------|
| 5 | `test_create_config` | 创建配置成功 |
| 6 | `test_create_config_as_default` | 设为默认时清除旧默认 |
| 7 | `test_list_configs_masks_key` | 列表中 api_key 已脱敏 |
| 8 | `test_get_config_returns_real_key` | 内部获取返回真实 key |
| 9 | `test_get_default_config` | 获取默认配置 |
| 10 | `test_update_config_name` | 更新名称 |
| 11 | `test_update_config_not_found` | 不存在返回错误 |
| 12 | `test_delete_config` | 删除配置 |
| 13 | `test_delete_config_not_found` | 不存在返回错误 |
| 14 | `test_create_mcp_non_admin` | 非管理员 MCP 无权创建 |
| 15 | `test_create_mcp_invalid_token` | 无效 MCP token 返回错误 |

### TestCallLLM（LLM 调用）

| # | 用例名 | 说明 |
|---|--------|------|
| 16 | `test_call_llm_no_config` | 无配置返回错误 |
| 17 | `test_call_llm_uses_default` | 使用默认配置 |
| 18 | `test_call_llm_uses_specific_config` | 使用指定配置 |
| 19 | `test_call_llm_request_error` | 请求失败返回错误 |

### TestMCPTollLLM（MCP 工具）

| # | 用例名 | 说明 |
|---|--------|------|
| 20 | `test_mcp_tools_count` | 6 个 MCP 工具 |
| 21 | `test_mcp_call_list` | MCP 列出配置 |
| 22 | `test_mcp_call_create` | MCP 创建配置 |
| 23 | `test_mcp_call_delete` | MCP 删除配置 |
| 24 | `test_mcp_call_unknown` | 未知工具抛异常 |

### TestLLMConfigProperties（插件属性）

| # | 用例名 | 说明 |
|---|--------|------|
| 25 | `test_name` | name == "llm_config" |
| 26 | `test_version` | version == "0.1.0" |
| 27 | `test_routes_count` | 路由数量 (7) |

---

## test_nav.py — 导航书签

**路径**: `tests/test_nav.py` | **用例数**: 31 | **测试类型**: 单元测试（Mock Engine）

### TestCreateLink（创建书签）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_create_link_success` | 创建书签成功 |
| 2 | `test_create_link_with_tags` | 带标签创建 |
| 3 | `test_create_link_private` | 私有书签 |
| 4 | `test_create_link_mcp` | MCP 创建书签 |

### TestUpdateLink（更新书签）

| # | 用例名 | 说明 |
|---|--------|------|
| 5 | `test_update_title` | 更新标题 |
| 6 | `test_update_not_author` | 非作者无权编辑 |
| 7 | `test_update_admin_allowed` | 管理员可编辑 |
| 8 | `test_update_not_found` | 不存在返回错误 |
| 9 | `test_update_tags` | 更新标签 |
| 10 | `test_update_visibility` | 更新可见性 |

### TestDeleteLink（删除书签）

| # | 用例名 | 说明 |
|---|--------|------|
| 11 | `test_delete_by_author` | 作者可删除 |
| 12 | `test_delete_by_admin` | 管理员可删除 |
| 13 | `test_delete_unauthorized` | 无权删除返回错误 |
| 14 | `test_delete_not_found` | 不存在返回错误 |
| 15 | `test_delete_mcp` | MCP 删除 |

### TestHideUnhide（隐藏/显示）

| # | 用例名 | 说明 |
|---|--------|------|
| 16 | `test_hide_link` | 隐藏书签 |
| 17 | `test_unhide_link` | 取消隐藏 |
| 18 | `test_get_hidden_ids` | 获取隐藏 ID 集合 |
| 19 | `test_hide_idempotent` | 重复隐藏幂等 |

### TestListLinks（书签列表）

| # | 用例名 | 说明 |
|---|--------|------|
| 20 | `test_list_empty` | 空列表 |
| 21 | `test_list_public` | 只返回公开书签 |
| 22 | `test_list_with_tags_parsed` | tags 解析为列表 |
| 23 | `test_list_mcp` | MCP 列出书签 |

### TestMCPTollNav（MCP 工具）

| # | 用例名 | 说明 |
|---|--------|------|
| 24 | `test_mcp_tools_count` | 3 个 MCP 工具 |
| 25 | `test_mcp_tool_names` | create/list/delete_nav_link |

### TestNavPluginProperties（插件属性）

| # | 用例名 | 说明 |
|---|--------|------|
| 26 | `test_name` | name == "nav" |
| 27 | `test_version` | version == "0.1.0" |
| 28 | `test_routes_count` | 路由数量 (7) |

---

## test_board.py — 管理后台

**路径**: `tests/test_board.py` | **用例数**: 14 | **测试类型**: 单元测试（Mock Engine）

### TestGetStats（统计数据）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_stats_from_cache` | 从缓存读取统计 |
| 2 | `test_stats_empty_live` | 无缓存时实时计算 |

### TestActiveAuthors（活跃作者）

| # | 用例名 | 说明 |
|---|--------|------|
| 3 | `test_empty_authors` | 无作者返回空列表 |
| 4 | `test_authors_from_cache` | 从缓存读取作者 |

### TestHotTags（热门标签）

| # | 用例名 | 说明 |
|---|--------|------|
| 5 | `test_empty_hot_tags` | 无标签返回空列表 |
| 6 | `test_hot_tags_from_cache` | 从缓存读取标签 |

### TestCronJobs（定时任务）

| # | 用例名 | 说明 |
|---|--------|------|
| 7 | `test_list_cron_jobs_empty` | 空任务列表 |
| 8 | `test_create_cron_job` | 创建定时任务 |
| 9 | `test_get_cron_job` | 获取任务详情 |
| 10 | `test_get_cron_job_not_found` | 不存在返回 None |
| 11 | `test_delete_cron_job` | 删除任务 |

### TestBoardPluginProperties（插件属性）

| # | 用例名 | 说明 |
|---|--------|------|
| 12 | `test_name` | name == "board" |
| 13 | `test_routes_count` | 路由数量 (20) |

### TestPresetJobs（预置任务）

| # | 用例名 | 说明 |
|---|--------|------|
| 14 | `test_preset_jobs_defined` | 4 个预置任务已定义 |
| 15 | `test_interval_options` | 5 个间隔选项 |

---

## test_config.py — 配置管理

**路径**: `tests/test_config.py` | **用例数**: 25 | **测试类型**: 单元测试

### TestAppConfig（应用配置）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_default_values` | 默认值正确 |
| 2 | `test_custom_values` | 自定义值 |
| 3 | `test_port_validation_valid` | 有效端口 |
| 4 | `test_port_validation_invalid` | 无效端口抛异常 |
| 5 | `test_log_level_uppercase` | 日志级别自动大写 |
| 6 | `test_log_level_invalid` | 无效级别抛异常 |
| 7 | `test_enabled_plugins_default` | 默认启用 blog/auth |
| 8 | `test_github_fields_optional` | GitHub 字段可选 |

### TestSiteConfigManager（站点配置管理器）

| # | 用例名 | 说明 |
|---|--------|------|
| 9 | `test_load_empty` | 空表返回 {} |
| 10 | `test_load_from_db` | 从数据库加载 |
| 11 | `test_load_cache_hit` | 缓存命中不重复查询 |
| 12 | `test_load_cache_expired` | 缓存过期重新查询 |
| 13 | `test_get_existing` | 获取已有配置 |
| 14 | `test_get_default` | 不存在返回默认值 |
| 15 | `test_set_value` | 设置值并清除缓存 |
| 16 | `test_batch_set` | 批量设置 |
| 17 | `test_batch_set_with_allowed_keys` | 白名单过滤 |
| 18 | `test_get_all` | 获取全部配置（副本） |
| 19 | `test_invalidate_cache` | 手动清除缓存 |
| 20 | `test_set_engine` | 设置引擎 |
| 21 | `test_no_engine` | 无引擎时静默失败 |

### TestConfigWrapper（配置包装器）

| # | 用例名 | 说明 |
|---|--------|------|
| 22 | `test_attribute_access` | 属性访问 |
| 23 | `test_getitem` | 字典风格访问 |
| 24 | `test_get` | get 方法 |
| 25 | `test_contains` | in 运算符 |

### TestConfigToDict（配置转字典）

| # | 用例名 | 说明 |
|---|--------|------|
| 26 | `test_returns_dict` | 返回字典 |

---

## test_template_engine.py — 模板引擎

**路径**: `tests/test_template_engine.py` | **用例数**: 28 | **测试类型**: 单元测试

### TestDatetimeFilter（日期格式化）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_valid_timestamp` | 有效时间戳格式化 |
| 2 | `test_string_timestamp` | 字符串时间戳 |
| 3 | `test_invalid_value` | 无效值返回"未知时间" |

### TestDatefmtFilter（相对时间）

| # | 用例名 | 说明 |
|---|--------|------|
| 4 | `test_just_now` | 刚刚 |
| 5 | `test_minutes_ago` | X 分钟前 |
| 6 | `test_hours_ago` | X 小时前 |
| 7 | `test_days_ago` | X 天前 |
| 8 | `test_old_date` | 超过 30 天显示日期 |
| 9 | `test_invalid` | 无效值返回"未知时间" |

### TestExcerptFilter（摘要提取）

| # | 用例名 | 说明 |
|---|--------|------|
| 10 | `test_none_input` | None 返回空字符串 |
| 11 | `test_empty_string` | 空字符串返回空 |
| 12 | `test_strips_markdown_headers` | 去除 # 标记 |
| 13 | `test_strips_bold` | 去除 ** 标记 |
| 14 | `test_strips_links` | 去除链接语法 |
| 15 | `test_truncation` | 截断并加 ... |
| 16 | `test_short_text_no_truncation` | 短文本不截断 |

### TestSanitizeHtmlInput（HTML 净化）

| # | 用例名 | 说明 |
|---|--------|------|
| 17 | `test_script_tag_escaped` | script 标签被转义 |
| 18 | `test_img_onerror_escaped` | onerror 事件被移除 |
| 19 | `test_safe_tags_preserved` | 安全标签保留 |
| 20 | `test_safe_a_href_preserved` | 安全链接保留 |
| 21 | `test_javascript_href_blocked` | javascript: 链接被阻止 |
| 22 | `test_data_href_blocked` | data: 链接被阻止 |
| 23 | `test_unsafe_tag_escaped` | iframe 等不安全标签被转义 |
| 24 | `test_safe_attrs_preserved` | 安全属性保留 |
| 25 | `test_unsafe_attrs_removed` | 事件属性被移除 |
| 26 | `test_plain_text_unchanged` | 纯文本不变 |

### TestMarkdownFilter（Markdown 渲染）

| # | 用例名 | 说明 |
|---|--------|------|
| 27 | `test_basic_markdown` | 粗体/斜体渲染 |
| 28 | `test_xss_in_markdown` | XSS 被阻止 |
| 29 | `test_strips_first_h1` | 去除第一个 H1 |
| 30 | `test_code_block` | 代码块渲染 |
| 31 | `test_link_markdown` | 链接渲染 |

### TestTemplateEngine（模板引擎）

| # | 用例名 | 说明 |
|---|--------|------|
| 32 | `test_init_with_valid_dir` | 有效目录初始化 |
| 33 | `test_init_with_invalid_dir` | 无效目录回退 |
| 34 | `test_render_string` | 字符串模板渲染 |
| 35 | `test_custom_filters_registered` | 自定义过滤器已注册 |
| 36 | `test_load_site_config_no_engine` | 无引擎时加载默认配置 |
| 37 | `test_load_site_config_cached` | 配置缓存 |
| 38 | `test_add_template_dir` | 添加模板目录 |

---

## test_utils.py — 工具函数

**路径**: `tests/test_utils.py` | **用例数**: 16 | **测试类型**: 单元测试

### TestHighlightExcerpt（搜索高亮）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_empty_text` | 空文本返回空 |
| 2 | `test_none_text` | None 返回空 |
| 3 | `test_short_text_with_match` | 短文本匹配高亮 |
| 4 | `test_case_insensitive` | 大小写不敏感 |
| 5 | `test_multiple_matches` | 多个匹配全部高亮 |
| 6 | `test_xss_in_query_escaped` | 查询中 XSS 被转义 |
| 7 | `test_xss_in_text_escaped` | 文本中 XSS 被转义 |
| 8 | `test_truncation_no_match` | 无匹配时截断 |
| 9 | `test_truncation_with_match_centered` | 匹配居中截断 |
| 10 | `test_truncation_match_at_start` | 匹配在开头 |
| 11 | `test_truncation_match_at_end` | 匹配在末尾 |
| 12 | `test_special_regex_chars_in_query` | 特殊正则字符安全 |
| 13 | `test_dot_in_query` | 点号匹配 |
| 14 | `test_unicode_query` | 中文查询 |
| 15 | `test_max_len_default_200` | 默认截断长度 200 |
| 16 | `test_text_shorter_than_max_len` | 短文本不截断 |

---

## test_security.py — 安全功能

**路径**: `tests/test_security.py` | **用例数**: 25 | **测试类型**: 单元测试

### TestXSSSanitization（XSS 净化）

| # | 用例名 | 说明 |
|---|--------|------|
| 1 | `test_script_tag_escaped` | script 标签被转义 |
| 2 | `test_img_onerror_stripped` | onerror 被移除 |
| 3 | `test_safe_tags_preserved` | 安全标签保留 |
| 4 | `test_javascript_href_blocked` | javascript: 被阻止 |
| 5 | `test_data_href_blocked` | data: 被阻止 |
| 6 | `test_event_handler_removed` | 事件属性被移除 |
| 7 | `test_safe_link_preserved` | 安全链接保留 |
| 8 | `test_plain_text_unchanged` | 纯文本不变 |

### TestSearchHighlight（搜索高亮 XSS）

| # | 用例名 | 说明 |
|---|--------|------|
| 9 | `test_script_in_query_escaped` | script 查询被转义 |
| 10 | `test_html_in_text_escaped` | HTML 文本被转义 |
| 11 | `test_special_chars_preserved` | 特殊字符安全 |
| 12 | `test_dot_in_query` | 点号查询 |
| 13 | `test_unicode_query` | 中文查询 |
| 14 | `test_truncation_safe` | 截断安全 |

### TestMarkdownXSS（Markdown XSS）

| # | 用例名 | 说明 |
|---|--------|------|
| 15 | `test_script_in_markdown_stripped` | script 被移除 |
| 16 | `test_basic_markdown_works` | 基本 Markdown 正常 |
| 17 | `test_link_preserved` | 链接保留 |
| 18 | `test_empty_input` | 空输入返回空 |

### TestOAuthState（OAuth State 验证）

| # | 用例名 | 说明 |
|---|--------|------|
| 19 | `test_oauth_states_dict_exists` | _oauth_states 字典存在 |
| 20 | `test_state_stored_with_expiry` | state 存储带过期时间 |
| 21 | `test_expired_state_cleanup` | 过期 state 被清理 |

### TestCookieSecurity（Cookie 安全属性）

| # | 用例名 | 说明 |
|---|--------|------|
| 22 | `test_cookie_has_samesite_lax` | SameSite=Lax |
| 23 | `test_cookie_has_httponly` | HttpOnly 设置 |
| 24 | `test_cookie_secure_dynamic` | Secure 动态检测 |

### TestRateLimiting（速率限制）

| # | 用例名 | 说明 |
|---|--------|------|
| 25 | `test_rate_limit_dict_exists` | 速率限制字典存在 |
| 26 | `test_rate_limit_sliding_window` | 滑动窗口实现 |

### TestExcerptFilter（摘要 XSS）

| # | 用例名 | 说明 |
|---|--------|------|
| 27 | `test_strips_markdown_headers` | 去除标题标记 |
| 28 | `test_strips_bold` | 去除粗体标记 |
| 29 | `test_strips_links` | 去除链接 |
| 30 | `test_truncation` | 截断安全 |
| 31 | `test_none_input` | None 输入安全 |

### TestAuthorIdSecurity（作者 ID 安全）

| # | 用例名 | 说明 |
|---|--------|------|
| 32 | `test_blog_create_requires_author` | 博客创建需要作者 |
| 33 | `test_topic_create_requires_author` | 话题创建需要作者 |

---

## 测试覆盖汇总

| 测试文件 | 用例数 | 状态 |
|----------|--------|------|
| `test_storage.py` | 9 | ✅ |
| `test_blog.py` | 6 | ⚠️ 4 个集成测试失败（需适配 author_id 变更） |
| `test_auth.py` | 27 | ✅ |
| `test_home_service.py` | 19 | ⚠️ 3 个测试失败（需适配 to_dict 变更） |
| `test_mcp.py` | 33 | ✅ |
| `test_plugins.py` | 38 | ✅ |
| `test_comments.py` | 49 | ✅ 新增 |
| `test_topic.py` | 48 | ✅ 新增 |
| `test_llm_config.py` | 27 | ✅ 新增 |
| `test_nav.py` | 28 | ✅ 新增 |
| `test_board.py` | 15 | ✅ 新增 |
| `test_config.py` | 26 | ✅ 新增 |
| `test_template_engine.py` | 38 | ✅ 新增 |
| `test_utils.py` | 16 | ✅ 新增 |
| `test_security.py` | 33 | ✅ 新增 |
| **总计** | **417** | **410 通过，7 个预存失败** |
