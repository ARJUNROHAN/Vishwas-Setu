export const STAGE_LABEL = {
  SELF_DISCLOSURE: 'Self-disclosure', RULE_REVIEW: 'Rule review',
  SCRUTINY: 'Scrutiny', RE_SCRUTINY: 'Re-Scrutiny', EVC: 'EVC', SHC: 'SHC', SAC: 'SAC',
  DECISION: 'Decision', RETURNED: 'With institution',
}
export const STATUS_LABEL = {
  IN_PROGRESS: 'In processing', RETURNED: 'Returned to institution', READY_FOR_DECISION: 'Awaiting decision',
  APPROVED: 'Approved', REJECTED: 'Not approved', UNDER_APPEAL: 'Under appeal', WITHDRAWN: 'Withdrawn',
  MISSING: 'Missing', LEASE_REVIEW_REQUIRED: 'Lease review required', RENEWAL_SUBMITTED: 'Renewal submitted',
  AWAITING_VERIFICATION: 'Awaiting verification', RESPONDED: 'Responded', RESOLVED: 'Resolved', NOT_RESOLVED: 'Not resolved',
  UPLOADED: 'Uploaded', CLEAR: 'Clear', DEFICIENCY_FOUND: 'Deficiency found',
}
export const KIND_LABEL = {
  STAGE_SLA: 'Stage time limit', INSTITUTION_COMPLIANCE: 'Institution compliance', EVC_SCHEDULE: 'EVC scheduling',
  EVC_REPORT: 'EVC report', DECISION: 'Decision', UNDERTAKING: 'Undertaking', UNDERTAKING_VERIFY: 'Evidence verification',
  DOC_EXPIRY: 'Document renewal', DOC_VERIFY: 'Document verification', APPEAL_WINDOW: 'Appeal window',
  RULE_REVIEW: 'Rule review',
}
export const ROLE_SHORT = {
  INSTITUTION: 'Institution', SCRUTINY_OFFICER: 'Scrutiny officer', RESCRUTINY_OFFICER: 'Re-scrutiny officer',
  EVC_COORDINATOR: 'EVC coordinator', EVC_MEMBER: 'EVC member', SHC_MEMBER: 'SHC member', SAC_MEMBER: 'SAC member',
  REGIONAL_HEAD: 'Regional officer', BUREAU: 'Bureau officer', COMPETENT_AUTHORITY: 'Competent authority',
  RULE_ADMIN: 'Rule administrator', ADMIN: 'System admin',
}
export const ACTION_LABEL = {
  APPLICATION_SUBMITTED: 'Application submitted', STAGE_STARTED: 'Stage started', STAGE_COMPLETED: 'Stage outcome recorded',
  AUTO_ADVANCED: 'Moved to next stage', RETURNED_TO_INSTITUTION: 'Returned for compliance',
  RETURNED_FOR_CLARIFICATION: 'Returned for clarification', INSTITUTION_RESPONDED: 'Institution responded',
  REVERTED: 'Reverted', REASSIGNED: 'Reassigned', READY_FOR_DECISION: 'Placed for decision',
  DECISION_RECORDED: 'Decision recorded', APPEAL_FILED: 'Appeal filed', EVC_QUEUED: 'Placed in EVC queue',
  EVC_SCHEDULED: 'EVC scheduled', EVC_RESCHEDULED: 'EVC rescheduled', EVC_REPORT_UPLOADED: 'EVC report uploaded',
  OBLIGATION_OPENED: 'Deadline opened', OBLIGATION_CLOSED: 'Deadline closed', OBLIGATION_OVERDUE: 'Deadline missed',
  ESCALATED: 'Escalated', CLOCK_PAUSED: 'Clock paused', CLOCK_RESUMED: 'Clock resumed',
  UNDERTAKING_CREATED: 'Undertaking recorded', EVIDENCE_SUBMITTED: 'Evidence submitted',
  UNDERTAKING_VERIFIED: 'Evidence verified', UNDERTAKING_REJECTED: 'Evidence rejected', UNDERTAKING_LAPSED: 'Undertaking lapsed',
  DOCUMENT_RENEWAL_SUBMITTED: 'Renewal submitted', DOCUMENT_VERIFIED: 'Document verified', DOCUMENT_REJECTED: 'Document rejected',
  CONFIG_CHANGED: 'Configuration changed', LOGIN: 'Signed in', FILE_UPLOADED: 'File uploaded',
  DEMO_CLOCK_ADVANCED: 'Demo clock advanced', ROUTED: 'Route selected', DEFICIENCIES_RECORDED: 'Deficiencies recorded',
  DEFICIENCIES_VERIFIED: 'Re-scrutiny verified deficiencies', ROUTE_ASSIGNED: 'Route assigned after rule review',
  EVC_REPORT_SUBMITTED: 'EVC report submitted', ESCALATION_ACKNOWLEDGED: 'Escalation acknowledged',
  RULESET_PUBLISHED: 'Ruleset version published', DOCUMENT_SUBMITTED: 'Document submitted', FILE_DOWNLOADED: 'File downloaded',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function fmtDate(iso) {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`
}
export function fmtDateTime(iso) {
  if (!iso) return '—'
  return `${fmtDate(iso)}, ${iso.slice(11, 16)}`
}
export function daysText(days) {
  if (days == null) return ''
  const n = Math.round(days)
  if (n === 0) return 'due today'
  return n > 0 ? `in ${n} day${n === 1 ? '' : 's'}` : `${-n} day${n === -1 ? '' : 's'} overdue`
}
export function stateTone(state) {
  return { OVERDUE: 'critical', DUE_SOON: 'warning', UPCOMING: 'good', PAUSED: 'paused', CLOSED: 'good' }[state] || 'neutral'
}
