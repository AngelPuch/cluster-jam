export enum AppRole {
  Client = 'cliente',
  Administrator = 'administrador',
}

export function readAppRole(metadata: unknown): AppRole | undefined {
  if (typeof metadata !== 'object' || metadata === null || Array.isArray(metadata)) {
    return undefined;
  }
  const role = (metadata as Record<string, unknown>).app_role;
  return role === AppRole.Client || role === AppRole.Administrator ? role : undefined;
}
