# Minimalist Cyan Design System

## Visual Theme & Atmosphere

- **Design Philosophy**: "Less is More" — 以极简主义为核心，强调空间感和呼吸感
- **Visual Tone**: 清新、现代、专业，带有科技感和生命力
- **Emotional Response**: 平静、专注、高效，同时充满活力

## Color Palette & Roles

### Primary Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--primary-cyan` | `#00BCD4` | 主色调，用于链接、按钮、强调元素 |
| `--primary-hover` | `#00ACC1` | 悬停状态 |
| `--primary-light` | `#E0F7FA` | 浅蓝底色（标签 hover、高亮卡片） |

### Neutral Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-page` | `#FAFAFA` | 页面底色 |
| `--bg-card` | `#FFFFFF` | 卡片白底 |
| `--bg-hover` | `#F5F5F5` | 悬停底色 |
| `--text-primary` | `#212121` | 标题 |
| `--text-color` | `#424242` | 正文 |
| `--text-secondary` | `#757575` | 辅助文字 |
| `--text-muted` | `#9E9E9E` | 弱化信息 |
| `--border-color` | `#EEEEEE` | 边框颜色 |

### Accent Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--accent-green` | `#4CAF50` | 成功状态、积极指标 |
| `--accent-orange` | `#FF9800` | 警告状态、重要提示 |

## Typography Rules

### Font Families
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 
  'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
```

### Type Scale
| Element | Size | Weight | Line Height | Usage |
|---------|------|--------|-------------|-------|
| H1 | 36px | 700 | 1.2 | 页面主标题 |
| H2 | 28px | 600 | 1.3 | 章节标题 |
| H3 | 22px | 600 | 1.4 | 子章节标题 |
| Body Large | 18px | 400 | 1.6 | 重要段落 |
| Body | 16px | 400 | 1.6 | 正文内容 |
| Small | 14px | 400 | 1.5 | 辅助信息 |
| Caption | 12px | 400 | 1.4 | 图注、标签 |

## Component Stylings

### Buttons
- **Primary Button**: 
  - Background: `--primary-cyan`
  - Text: White
  - Border Radius: 8px
  - Padding: 12px 24px
  - Hover: Darken by 10%
  
- **Secondary Button**:
  - Background: Transparent
  - Text: `--text-primary`
  - Border: 1px solid `--border-color`
  - Border Radius: 8px
  - Padding: 12px 24px

### Cards
- Background: `--bg-card`
- Border: 1px solid `--border-color`
- Border Radius: 12px
- Box Shadow: `0 2px 8px rgba(0,0,0,0.06)`
- Padding: 24px
- Hover Effect: Slight elevation with increased shadow

### Navigation Bar
- Height: 64px
- Background: `--bg-card`
- Border Bottom: 1px solid `--border-color`
- Logo: Bold, 20px, `--primary-cyan`
- Links: Regular weight, 16px, `--text-color`

## Layout Principles

### Spacing System
- Base Unit: 8px
- Small: 8px
- Medium: 16px
- Large: 24px
- XLarge: 32px
- XXLarge: 48px

### Grid System
- Container Max Width: 1200px
- Gutter: 24px
- Columns: 12-column grid for desktop, single column for mobile

### Section Spacing
- Between Sections: 64px vertical padding
- Within Sections: 32px vertical padding

## Depth & Elevation

### Shadows
- **Small**: `0 1px 3px rgba(0,0,0,0.05)`
- **Medium**: `0 4px 12px rgba(0,0,0,0.08)`
- **Large**: `0 8px 24px rgba(0,0,0,0.12)`

### Z-Index Scale
- Dropdowns: 100
- Modals: 200
- Tooltips: 300

## Do's and Don'ts

### Do's
- ✅ Use ample white space to create breathing room
- ✅ Maintain consistent spacing using the 8px grid system
- ✅ Use cyan accents sparingly for emphasis
- ✅ Ensure sufficient contrast for accessibility
- ✅ Keep typography clean and readable

### Don'ts
- ❌ Avoid heavy gradients or complex patterns
- ❌ Don't use more than 2-3 colors in any section
- ❌ Avoid overcrowding content
- ❌ Don't use decorative elements that don't serve a purpose
- ❌ Avoid inconsistent spacing or alignment

## Responsive Behavior

### Breakpoints
- Mobile: < 768px
- Tablet: 768px - 1024px
- Desktop: > 1024px

### Mobile Adaptations
- Stack columns vertically
- Reduce font sizes by 10-15%
- Increase touch targets to minimum 44px
- Simplify navigation to hamburger menu

## Agent Prompt Guide

### Quick Color Reference
- Primary: `#00BCD4` (Cyan)
- Background: `#FAFAFA` (Light Gray)
- Text: `#212121` (Dark Gray)
- Accent: `#4CAF50` (Green)

### Sample Prompts
- "Create a minimalist homepage with cyan accent colors"
- "Design a clean card component with subtle shadows"
- "Build a responsive navigation bar with cyan logo"
- "Generate a content section with proper spacing hierarchy"