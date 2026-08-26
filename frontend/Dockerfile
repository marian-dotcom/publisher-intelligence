FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable

COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
RUN pnpm install --frozen-lockfile

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
# Same-origin routing target for backend path prefixes (see next.config.ts).
# Default matches the compose service name; override per environment.
ENV BACKEND_INTERNAL_URL=http://api:8000

RUN corepack enable
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/next.config.ts ./next.config.ts
COPY --from=build --chown=node:node /app/lib ./lib
RUN mkdir -p ./public && chown -R node:node /app

USER node
EXPOSE 3000
ENV PATH="/app/node_modules/.bin:$PATH"
CMD ["next", "start"]
