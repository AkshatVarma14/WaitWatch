# Stage 1: Build static assets using pinned Node Alpine image
FROM node:22-alpine3.20 AS builder

WORKDIR /app

# Copy dependency manifests
COPY package.json package-lock.json ./

# Install dependencies strictly
RUN npm ci

# Copy application source files
COPY index.html vite.config.ts tsconfig*.json eslint.config.js ./
COPY public/ ./public/
COPY src/ ./src/

# Configurable build arguments
ARG VITE_API_URL=http://localhost:8000
ARG VITE_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
ARG VITE_POLLING_INTERVAL_SEC=30

ENV VITE_API_URL=${VITE_API_URL} \
    VITE_MAP_TILE_URL=${VITE_MAP_TILE_URL} \
    VITE_POLLING_INTERVAL_SEC=${VITE_POLLING_INTERVAL_SEC}

# Build production bundle
RUN npm run build

# Stage 2: Serve with lightweight pinned Nginx Alpine image
FROM nginx:1.30.6-alpine AS runtime

# Remove default site configuration
RUN rm -rf /etc/nginx/conf.d/default.conf /usr/share/nginx/html/*

# Copy custom Nginx configuration and compiled assets
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Native healthcheck using alpine built-in wget
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
