# Theme Switcher Plugin

主题切换插件，支持用户在传统界面和 V7.1 极简界面之间切换。

## 功能特性

- **双主题支持**：传统界面（经典布局）和 V7.1 极简界面（精密秩序风格）
- **中英文切换**：支持简体中文和英文两种语言
- **用户偏好持久化**：用户的主题和语言偏好保存在数据库中
- **无缝集成**：自动在用户中心显示主题切换选项

## 安装

插件已集成到 pyWork 项目中，无需额外安装。确保在 `app/main.py` 的 `enabled_plugins` 列表中包含了 `"theme_switcher"`。

## 使用方法

### 1. 切换主题

1. 登录 pyWork
2. 进入用户中心（/profile）
3. 在"界面偏好设置"区域，点击选择"传统界面"或"V7.1 极简界面"
4. 刷新首页即可看到新主题效果

### 2. 切换语言

1. 在用户中心的"界面偏好设置"区域
2. 从语言下拉菜单中选择"简体中文"或"English"
3. 语言设置会立即生效

## API 接口

### 获取主题偏好

```
GET /api/theme/preference
```

响应示例：
```json
{
  "theme": "traditional",
  "language": "zh-CN"
}
```

### 设置主题偏好

```
POST /api/theme/preference
Content-Type: application/json

{
  "theme": "v7",
  "language": "en-US"
}
```

响应示例：
```json
{
  "success": true,
  "theme": "v7",
  "language": "en-US"
}
```

## V7.1 极简界面

访问 `/v7` 可直接进入 V7.1 极简仪表盘页面（需要登录）。

特点：
- 精密秩序风格，高信息密度
- 左侧系统监控面板 + 右侧数据流列表
- 支持浅色/深色主题切换
- 支持中英文实时切换
- 无图无 Emoji，纯粹排版与空间关系

## 数据库结构

插件会自动创建 `user_preferences` 表：

```sql
CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY,
    theme_preference TEXT NOT NULL DEFAULT 'traditional',
    language_preference TEXT NOT NULL DEFAULT 'zh-CN',
    updated_at INTEGER NOT NULL
)
```

## 开发说明

如需自定义 V7.1 界面的样式或内容，可编辑：
- `plugins/theme_switcher/templates/v7_dashboard.html`

如需修改主题切换逻辑，可编辑：
- `plugins/theme_switcher/plugin.py`
