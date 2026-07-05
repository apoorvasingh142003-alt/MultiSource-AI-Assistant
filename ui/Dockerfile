# ── UI (Next.js inspector frontend) ──────────────────────────────────────────
FROM node:20-alpine

WORKDIR /ui

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .

# The browser calls the UI's own origin at /api/*; the Next server proxies those to the
# backend at API_PROXY_TARGET. In docker-compose that is the API service hostname.
ARG API_PROXY_TARGET=http://localhost:8000
ENV API_PROXY_TARGET=$API_PROXY_TARGET
# Client-inlined at build: whether to gate the app behind Google sign-in.
ARG NEXT_PUBLIC_AUTH_ENABLED=false
ENV NEXT_PUBLIC_AUTH_ENABLED=$NEXT_PUBLIC_AUTH_ENABLED
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
