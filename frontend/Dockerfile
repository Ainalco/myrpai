# Multi-stage build for production
FROM oven/bun:1-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json bun.lock ./

# Install dependencies
RUN bun install --frozen-lockfile

# Copy source code
COPY . .

# Build arguments for environment variables
ARG VITE_API_URL=/api
ARG VITE_API_TIMEOUT=90000
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_API_TIMEOUT=$VITE_API_TIMEOUT

# Build for production
RUN bun run build

# Production stage - serve with nginx
FROM mirror.gcr.io/library/nginx:alpine

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 3000

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
