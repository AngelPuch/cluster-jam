FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build
WORKDIR /workspace/services/profileService
COPY services/profileService/package.json services/profileService/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY services/profileService/nest-cli.json services/profileService/tsconfig*.json ./
COPY services/profileService/eslint.config.mjs services/profileService/.prettierrc ./
COPY services/profileService/src ./src
COPY services/profileService/test ./test
COPY contracts/openapi/profile/v1/openapi.json /workspace/contracts/openapi/profile/v1/openapi.json
RUN npm run build && npm run typecheck && npm run lint && npm run format:check \
    && npm test -- --runInBand && npm run test:e2e -- --runInBand \
    && node dist/commands/profile-openapi.command.js --check
RUN npm prune --omit=dev --ignore-scripts --no-audit --no-fund

FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS runtime
ARG SERVICE_VERSION=0.0.1
ARG VCS_REF=local
LABEL org.opencontainers.image.title="Cluster JAM Profile Service" \
    org.opencontainers.image.version="${SERVICE_VERSION}" \
    org.opencontainers.image.revision="${VCS_REF}" \
    org.opencontainers.image.source="https://github.com/AngelPuch/cluster-jam"
ENV NODE_ENV=production SERVICE_VERSION=${SERVICE_VERSION} HTTP_PORT=8080
WORKDIR /app
COPY --from=build /workspace/services/profileService/package.json ./package.json
COPY --from=build /workspace/services/profileService/node_modules ./node_modules
COPY --from=build /workspace/services/profileService/dist ./dist
USER node
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:8080/health/live',{signal:AbortSignal.timeout(2000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "dist/main.js"]
