type Role = 'owner' | 'admin' | 'member'
type PlanTier = 'trialing' | 'seedling' | 'oak' | 'redwood' | 'ancient_forest'

const PLAN_FEATURES: Record<string, Record<string, boolean | number | null>> = {
  trialing: { max_emails_per_sequence: 15, ai_filter: true, ai_send_timing: true, api_access: true },
  seedling: { max_emails_per_sequence: 3, ai_filter: false, ai_send_timing: false, api_access: false },
  oak: { max_emails_per_sequence: 7, ai_filter: true, ai_send_timing: true, api_access: false },
  redwood: { max_emails_per_sequence: 15, ai_filter: true, ai_send_timing: true, api_access: true },
  ancient_forest: { max_emails_per_sequence: null, ai_filter: true, ai_send_timing: true, api_access: true },
}

const ROLE_HIERARCHY: Record<Role, number> = { owner: 3, admin: 2, member: 1 }

export function hasRole(userRole: Role, requiredRole: Role): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole]
}

export function canAccess(planTier: string, feature: string): boolean {
  const features = PLAN_FEATURES[planTier] || PLAN_FEATURES.trialing
  const value = features[feature]
  if (typeof value === 'boolean') return value
  if (value === null) return true
  if (typeof value === 'number') return true
  return false
}

export function getFeatureLimit(planTier: string, feature: string): number | null {
  const features = PLAN_FEATURES[planTier] || PLAN_FEATURES.trialing
  const value = features[feature]
  if (typeof value === 'number') return value
  return null
}
