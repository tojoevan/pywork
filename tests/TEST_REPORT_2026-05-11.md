# pyWork 单元测试报告

**日期**: 2026-05-11
**环境**: macOS, Python 3.14.3, pytest 9.0.3
**耗时**: 0.79 秒

---

## 概览

| 指标 | 数值 |
|------|------|
| 测试文件 | 15 |
| 测试用例 | 424 |
| 通过 | 424 |
| 失败 | 0 |
| 跳过 | 0 |
| 错误 | 0 |

---

## 各模块测试明细

### 1. test_auth.py — 27 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestCaptcha (4) | generate, verify_correct, verify_wrong, verify_expired | PASS |
| TestPasswordHash (6) | hash, hash_with_salt, verify_correct, verify_wrong, split_colon, split_dollar | PASS |
| TestRegister (5) | success, duplicate_username, duplicate_email, invalid_captcha, second_user_not_admin | PASS |
| TestLogin (3) | success, wrong_password, nonexistent_user | PASS |
| TestSession (2) | logout, get_user_by_token | PASS |
| TestMCPToken (4) | create, list, revoke, get_user_by_mcp_token | PASS |
| TestTokenGeneration (2) | generate, generate_unique | PASS |

### 2. test_blog.py — 6 tests

| 测试项 | 结果 |
|--------|------|
| create_post | PASS |
| search_posts | PASS |
| update_post | PASS |
| mcp_tools | PASS |
| mcp_resources | PASS |
| plugin_manager | PASS |

### 3. test_plugins.py — 38 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestBlogCreate (5) | success, with_tags, default_status, published, with_author | PASS |
| TestBlogRead (5) | success, not_found, empty, multiple, limit | PASS |
| TestBlogUpdate (6) | title, content, status, tags, not_found, partial | PASS |
| TestBlogDelete (2) | success, not_found | PASS |
| TestNotesCreate (3) | success, private_default, public | PASS |
| TestNotesRead (2) | success, list_by_user | PASS |
| TestNotesUpdate (2) | title, visibility | PASS |
| TestNotesDelete (1) | success | PASS |
| TestMicroblogCreate (2) | success, multiple | PASS |
| TestMicroblogRead (2) | success, list_posts | PASS |
| TestMicroblogDelete (1) | success | PASS |
| TestCrossPlugin (2) | shared_engine, timestamps_updated | PASS |
| TestEdgeCases (5) | empty_content, special_chars, unicode, long_content, empty_tags | PASS |

### 4. test_comments.py — 49 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestCreateComment (11) | success, not_logged_in, empty_content, too_long, invalid_target, target_not_found, auto_approve, pending, reply, reply_nested_rejected, reply_nonexistent | PASS |
| TestReviewComment (7) | approve, reject, not_logged_in, not_author, already_reviewed, invalid_action, nonexistent | PASS |
| TestDeleteComment (6) | by_comment_author, by_content_author, by_admin, unauthorized, not_logged_in, nonexistent | PASS |
| TestListComments (4) | approved, missing_params, invalid_type, invalid_id | PASS |
| TestPendingComments (4) | not_logged_in, missing_params, not_author, can_view | PASS |
| TestNotifications (8) | list, not_logged_in, mark_read, wrong_user, not_found, mark_all_read, unread_count, unread_not_logged | PASS |
| TestMCPTollComments (9) | list, no_token, invalid_token, empty_content, too_long, target_not_found, success, as_author, tools_registered | PASS |
| TestEdgeCases (5) | microblog, note, admin_review, properties, routes_count | PASS |

### 5. test_topic.py — 48 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestCreateTopic (5) | success, no_author, custom_deadline, mcp, mcp_invalid_token | PASS |
| TestUpdateTopic (7) | title, description, not_author, admin_allowed, closed, nonexistent, empty_title | PASS |
| TestReplyTopic (5) | success, no_author, closed, nonexistent, with_parent | PASS |
| TestVote (7) | upvote_new, downvote_new, toggle_off, change, no_author, on_reply, mcp, mcp_invalid_token | PASS |
| TestGetTopicDetail (5) | existing, nonexistent, with_replies, with_votes, remaining_hours | PASS |
| TestCloseTopic (3) | open, already_closed, nonexistent | PASS |
| TestListTopics (5) | empty, multiple, filter_by_status, with_limit, remaining_hours | PASS |
| TestMarkExpired (2) | mark_expired, no_expired | PASS |
| TestMCPTollTopic (5) | tools_count, tool_names, call_create, call_list, call_unknown | PASS |
| TestTopicPluginProperties (3) | name, version, routes_count | PASS |

### 6. test_llm_config.py — 27 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestMaskApiKey (4) | normal, short, empty, none | PASS |
| TestLLMConfigCRUD (11) | create, as_default, list_masks, get_real, get_default, update, update_not_found, delete, delete_not_found, mcp_non_admin, mcp_invalid_token | PASS |
| TestCallLLM (4) | no_config, default, specific, request_error | PASS |
| TestMCPTollLLM (5) | tools_count, call_list, call_create, call_delete, call_unknown | PASS |
| TestLLMConfigProperties (3) | name, version, routes_count | PASS |

### 7. test_nav.py — 28 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestCreateLink (4) | success, with_tags, private, mcp | PASS |
| TestUpdateLink (6) | title, not_author, admin_allowed, not_found, tags, visibility | PASS |
| TestDeleteLink (5) | by_author, by_admin, unauthorized, not_found, mcp | PASS |
| TestHideUnhide (4) | hide, unhide, get_hidden_ids, idempotent | PASS |
| TestListLinks (4) | empty, public, with_tags_parsed, mcp | PASS |
| TestMCPTollNav (2) | tools_count, tool_names | PASS |
| TestNavPluginProperties (3) | name, version, routes_count | PASS |

### 8. test_board.py — 15 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestGetStats (2) | from_cache, empty_live | PASS |
| TestActiveAuthors (2) | empty, from_cache | PASS |
| TestHotTags (2) | empty, from_cache | PASS |
| TestCronJobs (5) | list_empty, create, get, get_not_found, delete | PASS |
| TestBoardPluginProperties (2) | name, routes_count | PASS |
| TestPresetJobs (2) | preset_jobs_defined, interval_options | PASS |

### 9. test_mcp.py — 24 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestInitialize (4) | protocol_version, capabilities, server_info, ignores_params | PASS |
| TestToolsList (4) | all_tools, namespaced, includes_schema, empty | PASS |
| TestToolsCall (6) | invalid_name, not_found, plugin_not_found, with_handler, with_mcp_call, exception | PASS |
| TestResourcesList (3) | all, includes_metadata, empty | PASS |
| TestResourcesRead (4) | invalid_uri, not_found, success, exception | PASS |
| TestPromptsList (3) | all, namespaced, includes_arguments | PASS |
| TestPromptsGet (5) | invalid_name, not_found, success, template_substitution, missing_argument | PASS |
| TestErrorHandling (2) | unknown_method, empty_params | PASS |
| TestIntegration (2) | full_init_then_list_tools, multiple_plugins_registered | PASS |

### 10. test_storage.py — 9 tests

| 测试项 | 结果 |
|--------|------|
| engine_start_stop | PASS |
| put_and_get | PASS |
| query | PASS |
| delete | PASS |
| raft_log | PASS |
| export_import | PASS |
| microblog_posts_table | PASS |
| notes_table | PASS |
| guestbook_entries_table | PASS |

### 11. test_config.py — 31 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestAppConfig (8) | defaults, custom, port_valid, port_invalid, log_upper, log_invalid, plugins_default, github_optional | PASS |
| TestSiteConfigManager (11) | empty, from_db, cache_hit, cache_expired, get_existing, get_default, set, batch_set, batch_allowed, get_all, invalidate | PASS |
| TestConfigWrapper (9) | attr, getitem, get, contains, items, keys, values, key_error, attr_error | PASS |
| TestConfigToDict (1) | returns_dict | PASS |

### 12. test_home_service.py — 18 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestHomeFeedItem (3) | to_dict_post, to_dict_microblog, to_dict_note | PASS |
| TestGetFeed (7) | empty, blog_only, microblog_only, notes_only, mixed_sorted, limit, exception | PASS |
| TestGetStats (3) | no_board, returns_stats, exception | PASS |
| TestGetActiveAuthors (3) | no_board, returns_authors, exception | PASS |
| TestGetHomeData (3) | all_empty, all_data, parallel | PASS |

### 13. test_security.py — 33 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestXSSSanitization (8) | script_escaped, img_onerror, safe_tags, javascript_href, data_href, event_handler, safe_link, plain_text | PASS |
| TestSearchHighlight (6) | script_query, html_text, special_chars, dot_query, unicode, truncation | PASS |
| TestMarkdownXSS (4) | script_stripped, basic_works, link_preserved, empty | PASS |
| TestOAuthState (3) | dict_exists, stored_with_expiry, expired_cleanup | PASS |
| TestCookieSecurity (3) | samesite_lax, httponly, secure_dynamic | PASS |
| TestRateLimiting (2) | dict_exists, sliding_window | PASS |
| TestExcerptFilter (5) | headers, bold, links, truncation, none | PASS |
| TestAuthorIdSecurity (2) | blog_requires_author, topic_requires_author | PASS |

### 14. test_template_engine.py — 39 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestDatetimeFilter (3) | valid, string, invalid | PASS |
| TestDatefmtFilter (6) | just_now, minutes, hours, days, old_date, invalid | PASS |
| TestExcerptFilter (7) | none, empty, headers, bold, links, truncation, short | PASS |
| TestSanitizeHtmlInput (10) | script, img, safe_tags, a_href, javascript, data, unsafe_tag, safe_attrs, unsafe_attrs, plain | PASS |
| TestMarkdownFilter (7) | empty, basic, xss, strips_h1, keeps_h1, code_block, link | PASS |
| TestTemplateEngine (7) | valid_dir, invalid_dir, render_string, custom_filters, no_engine, cached, add_dir | PASS |

### 15. test_utils.py — 16 tests

| 测试类 | 测试项 | 结果 |
|--------|--------|------|
| TestHighlightExcerpt (16) | empty, none, short_match, case_insensitive, multiple, xss_query, xss_text, truncation_no_match, truncation_centered, truncation_start, truncation_end, regex_chars, dot_query, unicode, max_len_default, short_no_truncation | PASS |

---

## 模块覆盖率汇总

| 模块 | 测试文件 | 用例数 | 状态 |
|------|----------|--------|------|
| auth | test_auth.py | 27 | 全部通过 |
| blog | test_blog.py + test_plugins.py | 44 | 全部通过 |
| comments | test_comments.py | 49 | 全部通过 |
| topic | test_topic.py | 48 | 全部通过 |
| llm_config | test_llm_config.py | 27 | 全部通过 |
| nav | test_nav.py | 28 | 全部通过 |
| board | test_board.py | 15 | 全部通过 |
| mcp | test_mcp.py | 24 | 全部通过 |
| storage | test_storage.py | 9 | 全部通过 |
| config | test_config.py | 31 | 全部通过 |
| home_service | test_home_service.py | 18 | 全部通过 |
| security | test_security.py | 33 | 全部通过 |
| template_engine | test_template_engine.py | 39 | 全部通过 |
| utils | test_utils.py | 16 | 全部通过 |
| **合计** | **15** | **424** | **全部通过** |
