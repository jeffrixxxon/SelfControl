# Сборка мини-аппа и раздача через Caddy (HTTPS-сертификат выпускается автоматически)
FROM node:20-alpine AS build
WORKDIR /web
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
