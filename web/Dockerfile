FROM node:24-alpine AS build
WORKDIR /srv/web
COPY package.json pnpm-lock.yaml .npmrc ./
RUN corepack enable && npm_config_minimum_release_age=0 pnpm install --frozen-lockfile
COPY . .
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN pnpm build

FROM nginx:alpine
COPY --from=build /srv/web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
