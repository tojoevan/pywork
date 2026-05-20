# Inkspcl 设计规范 v2.0

> 浅色极简 · Baidu 风格 · 干净利落

## 设计哲学

参考 huashu-design 的 **#03 Information Architects** + **#18 Kenya Hara** 风格：
- **内容优先**：设计不是装饰，是内容的建筑
- **极致简洁**：删减到无法再删
- **功能即美学**：性能和可读性就是最好的设计

## 色彩系统

### 主色调

| Token | 值 | 用途 |
|-------|-----|------|
| `--primary-color` | `#2468f2` | 品牌蓝，链接、按钮、强调元素 |
| `--primary-hover` | `#1a56db` | 悬停状态 |
| `--primary-light` | `#e8effd` | 浅蓝底色（标签 hover、高亮卡片） |

### 背景

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg-page` | `#f5f6f8` | 页面底色 |
| `--bg-card` | `#ffffff` | 卡片白底 |
| `--bg-hover` | `#f0f2f5` | 悬停底色 |

### 文字

| Token | 值 | 用途 |
|-------|-----|------|
| `--text-primary` | `#222222` | 标题 |
| `--text-color` | `#333333` | 正文 |
| `--text-secondary` | `#666666` | 辅助文字 |
| `--text-muted` | `#999999` | 弱化信息 |

### 边框

| Token | 值 |
|-------|-----|
| `--border-color` | `#e8e8e8` |
| `--border-hover` | `#d0d0d0` |

### 内容类型色标

| 类型 | 色值 | 用途 |
|------|------|------|
| 博客 | `#2468f2` | 蓝色左边条 |
| 微博 | `#f59e0b` | 琥珀色左边条 |
| 笔记 | `#3b82f6` | 浅蓝左边条 |

## 字体

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont,
  'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
```

- 正文：15px / 1.6 行高
- 标题：16-20px / font-weight: 600-700
- 辅助：12-13px

## 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-sm` | `4px` | 按钮、输入框 |
| `--radius-md` | `8px` | 卡片 |
| `--radius-full` | `9999px` | 标签 |

## 阴影

```css
--shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
--shadow-md: 0 2px 8px rgba(0,0,0,0.06);  /* 卡片 hover */
```

## 组件规范

### 导航栏
- 白色底 + 底部 1px `#e8e8e8` 分割线
- 高度 56px，sticky 固定
- Logo 蓝色 `#2468f2`，20px 700 weight

### 卡片
- 白底 + 1px 边框
- 8px 圆角
- Hover 时添加 `shadow-md`
- 左侧 3px 色条标识内容类型

### 按钮
- Primary：蓝底白字，hover 加深
- Secondary：灰底黑字，1px 边框
- 高度 36px，4px 圆角

### 标签
- 圆角 pill（9999px）
- 灰底灰字，hover 变蓝底蓝字

## 设计原则

1. **白即美** — 80%+ 留白比例
2. **无多余** — 不用渐变、不用投影（除 hover）、不用动画装饰
3. **一致性** — 全站统一使用 CSS 变量
4. **可读性** — 正文 15px，行高 1.6，最大宽度 800px
5. **响应式** — 三栏布局在 768px 以下折叠为单栏

## 文件结构

| 文件 | 职责 |
|------|------|
| `base.css` | 全局 tokens、重置、通用组件 |
| `home.css` | 首页三栏布局、卡片流 |
| `blog.css` | 博客列表 + 文章详情 |
| `auth.css` | 登录注册页 |
| `nav.css` | 导航/书签页 |
| 其他 | microblog / notes / topic / rss / about / profile / board / comments |
