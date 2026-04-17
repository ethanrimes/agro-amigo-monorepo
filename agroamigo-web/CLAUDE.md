# AgroAmigo Web

Next.js 15 web app for AgroAmigo -- agricultural market prices, product listings, input tracking, and a map view. Uses Supabase as the backend and Leaflet for maps.

## Prerequisites

- Node.js 18+ (tested with v24.12)
- npm 9+

## How to run (PowerShell)

This project is part of a monorepo. You must install dependencies from the **repo root** first, then start the dev server.

```powershell
# 1. Navigate to the repo root
cd C:\Users\ethankallett\Documents\Camp-AIR

# 2. Install all workspace dependencies (only needed once, or after pulling new changes)
npm install

# 3. Start the dev server
cd agroamigo-web
npm run dev
```

The site will be available at **http://localhost:3000** (or the next available port if 3000 is in use).

### Available scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server with hot reload |
| `npm run build` | Create a production build |
| `npm run start` | Serve the production build |

## Environment variables

The app needs a `.env.local` file in `agroamigo-web/` with Supabase credentials. This file already exists and is gitignored. See `.env.example` in `data-pipeline/` for reference values.

## Project structure

```
agroamigo-web/
├── src/
│   ├── app/           # Next.js App Router pages
│   │   ├── page.tsx           # Home / dashboard
│   │   ├── products/          # Product listings
│   │   ├── product/[id]/      # Product detail
│   │   ├── insumos/           # Agricultural inputs list
│   │   ├── insumo/[id]/       # Input detail
│   │   ├── markets/           # Market listings
│   │   ├── market/[id]/       # Market detail
│   │   ├── map/               # Leaflet map view
│   │   └── settings/          # App settings
│   ├── components/    # Shared UI components
│   ├── context/       # React context providers (Settings, Watchlist)
│   └── lib/           # Supabase client init
├── public/            # Static assets
├── package.json
├── next.config.mjs    # Transpiles @agroamigo/shared, configures image domains
└── tsconfig.json
```

## Shared package

The app depends on `@agroamigo/shared` (in `packages/shared/`), which provides shared types, API helpers, theme, and mock data. The monorepo workspace wiring handles the link automatically when you `npm install` from the root.
