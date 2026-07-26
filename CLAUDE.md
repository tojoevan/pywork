# pyWork 项目规范

## Git workflow

- 所有修改走 feature branch + PR，禁止直接 push main
- Commit message 用中文，保留英文 type prefix（feat/fix/refactor）
- 每次新修改前，先 `gh pr view <num> --json state` 确认上一个 PR 是否已合并
  - 已合并 → `git checkout main && git pull && git checkout -b <new-branch>` → commit → push → 询问后开 PR
  - 未合并 → 推同一分支
- 分支合并后删除本地和远程分支

## 技术栈

- FastAPI + aiosqlite（异步 SQLite）
- Jinja2 模板引擎
- 插件架构，每个功能独立 plugin
- 认证：cookie auth_token，无 flask-login
- CSS：原生 CSS，无预处理器
