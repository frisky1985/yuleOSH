# yuleOSH SaaS Frontend

yuleOSH 嵌入式AI开发全流程平台的前端应用，基于 Next.js 构建。

## 技术栈

- **Next.js 16** — App Router, TypeScript
- **Tailwind CSS 4** — 深色主题，品牌色系
- **shadcn/ui** — UI 组件库 (Base UI 驱动)
- **Lucide React** — 图标库

## 品牌色系

| 用途 | 色值 |
|------|------|
| 主色 (紫) | `#722ed1` |
| 辅色 (蓝) | `#1677ff` |
| 成功/交付 | `#10b981` |
| 警告 | `#f59e0b` |
| 错误 | `#ff4d4f` |
| 背景 | `#0a0e17` |
| 表面色 | `#111827` |
| 边框 | `#1e293b` |

## 路由结构

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 着陆页 | 产品介绍、功能特性、工作流展示 |
| `/login` | 登录页 | 邮箱登录 / GitHub OAuth 占位 |
| `/dashboard` | Dashboard | 项目列表、状态、搜索 |
| `/dashboard/projects/[id]` | 项目详情 | Pipeline 流水线可视化、CI/CD 层状态 |

## 启动

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 构建
npm run build

# 生产模式
npm start
```

开发模式默认在 `http://localhost:3000` 启动。

## 项目结构

```
src/
├── app/
│   ├── globals.css          # 全局样式 + CSS变量
│   ├── layout.tsx           # 根布局 (深色主题)
│   ├── page.tsx             # 着陆页
│   ├── not-found.tsx        # 404 页面
│   ├── login/
│   │   └── page.tsx         # 登录页
│   └── dashboard/
│       ├── page.tsx         # 项目列表
│       └── projects/
│           └── [id]/
│               └── page.tsx # 项目详情 + Pipeline
├── components/
│   ├── github-icon.tsx      # GitHub SVG 图标
│   └── ui/                  # shadcn/ui 组件
│       ├── button.tsx
│       ├── card.tsx
│       ├── input.tsx
│       ├── badge.tsx
│       ├── avatar.tsx
│       ├── select.tsx
│       ├── table.tsx
│       └── ...
└── lib/
    └── utils.ts             # cn() 工具函数
```

## 数据

当前所有数据使用 Mock 数据展示。后续接入后端 API 后，只需替换对应的数据请求即可。

Mock 数据位置：
- `src/app/dashboard/page.tsx` — Dashboard 项目列表
- `src/app/dashboard/projects/[id]/page.tsx` — 项目详情 + Pipeline
