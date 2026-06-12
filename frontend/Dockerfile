# =============================================================================
# yuleOSH Frontend — Next.js Production Dockerfile (Multi-stage Build)
# =============================================================================
# Build:
#   docker build -t yuleosh-frontend:latest .
# Run:
#   docker run -p 3000:3000 yuleosh-frontend:latest
# =============================================================================

# ── Stage 1: Dependencies ──────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app

# Install dependencies first (cached layer unless lockfile changes)
COPY package.json package-lock.json ./
RUN npm ci --only=production --prefer-offline --no-audit --no-fund

# ── Stage 2: Build ─────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Build-time args
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-https://yuleosh.io}
ENV NODE_ENV=production

# Copy deps from stage 1
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build Next.js application
RUN npm run build

# Prune devDependencies from node_modules
RUN npm prune --omit=dev --prefer-offline --no-audit

# ── Stage 3: Production runtime ────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

# Security: non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --ingroup nodejs nextjs

# Production environment
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Copy only what's needed for production
COPY --from=builder /app/public ./public

# Copy .next and its standalone output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Optional: copy node_modules if standalone doesn't include everything
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD node -e "http=require('http');http.get('http://127.0.0.1:${PORT}/api/health',r=>process.exit(r.statusCode===200?0:1))"

# Switch to non-root user
USER nextjs

EXPOSE 3000

# Start Next.js standalone server
CMD ["node", "server.js"]
