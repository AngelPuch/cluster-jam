FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build

WORKDIR /workspace/services/authService
COPY services/authService/package.json services/authService/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY services/authService/nest-cli.json services/authService/tsconfig*.json ./
COPY services/authService/eslint.config.mjs services/authService/.prettierrc ./
COPY services/authService/src ./src
COPY services/authService/test ./test
COPY contracts/openapi/auth/v1/openapi.json /workspace/contracts/openapi/auth/v1/openapi.json
RUN npm run build \
    && npx tsc --noEmit -p test/tsconfig.spec.json \
    && npx eslint "{src,apps,libs,test}/**/*.ts" --max-warnings=0 \
    && npm test -- --runInBand \
    && npm run test:e2e -- --runInBand \
    && node dist/commands/auth-openapi.command.js --check
RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS runtime

ARG SERVICE_VERSION=0.0.1
ARG VCS_REF=local
LABEL org.opencontainers.image.title="Cluster JAM Auth Service" \
    org.opencontainers.image.version="${SERVICE_VERSION}" \
    org.opencontainers.image.revision="${VCS_REF}" \
    org.opencontainers.image.source="https://github.com/AngelPuch/cluster-jam"
ENV NODE_ENV=production \
    SERVICE_VERSION=${SERVICE_VERSION} \
    HTTP_PORT=8080
WORKDIR /app
COPY --from=build /workspace/services/authService/package.json ./package.json
COPY --from=build /workspace/services/authService/node_modules ./node_modules
COPY --from=build /workspace/services/authService/dist ./dist
USER node
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:8080/health/live',{signal:AbortSignal.timeout(2000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "dist/main.js"]
