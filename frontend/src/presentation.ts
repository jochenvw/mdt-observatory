import type { Data, Meeting, Position, Role, RoleState, Trace } from './types';
import { clinicalCaseKind } from './caseProfiles';

export const ROLE_FOCUS: Record<Role, string> = {
  radiology: 'Reviewing lesion measurements, interval change and imaging uncertainty.',
  oncology: 'Reviewing treatment choices alongside previous toxicity and tolerability.',
  surgery: 'Reviewing resectability, fitness and the information needed before a procedure.',
  pathology: 'Reviewing tissue findings, molecular results and diagnostic limitations.',
  research: 'Reviewing study quality and whether the evidence applies to this patient.',
  protocol: 'Checking Dutch and European pathways, access and conditions of applicability.',
  patient: 'Reviewing stated preferences, treatment burden and shared decision needs.',
};
const GENERIC_UPDATE = 'A team update was recorded. No additional clinical detail was provided.';
const TIMEOUT_ERROR = 'The specialist review did not respond in time. No new conclusion has been recorded. Retry the affected review or ask the chair to intervene.';
const CAPACITY_ERROR = 'Specialist review is delayed because the analysis service is busy. No new conclusion has been recorded. Wait or retry the affected review.';
const REVIEW_ERROR = 'This review could not be completed. Do not treat it as a new clinical conclusion. Retry the affected review or ask the chair to intervene.';
const technical = /actual azure call|azure|openai|deployment|model(?:[_ -](?:call|request|response|output|invocation|inference))|request[_ -]?id|response[_ -]?id|token(?:s|_usage| counts?)?\b|prompt[_ -]?(?:tokens|details)|completion_tokens|api[_ -]?key|traceback|http(?:x|exception)?\b|\b(?:sdk|sse|json|semaphore|rate.?limit|quota|telemetry|transport|provider|retry-after|finish_reason)\b|(?:get|search|assess|compare|check|review|calculate)_[a-z_]+|\b(?:req|resp|call)_[a-z0-9]+/i;
const technicalKey = /^(?:model|models|model_metadata|model_request_id|model_response_id|deployment|request_id|response_id|token_usage|usage|input_tokens|output_tokens|total_tokens|analysis_total_tokens|prompt|messages|api_key|endpoint|error_type|error_code|status_code|telemetry|transport|provider|tool|tools|retrieval|request|response)$/i;
const normalized = (value: string) => value.replace(/[^a-z0-9]/gi, '').toLowerCase();

export function recordText(value: string): string {
  return value.replace(/synthetic|syntetic/gi, 'demonstration').replace(/SYN-/gi, 'CASE-');
}
/** Recorded clinical prose for display, with internal pathway markers in clinician words. */
export function outcomeText(value: string): string {
  return recordText(value).replace(/\bPROTOCOL_NOT_PUBLIC\b/g, 'Local pathway unavailable').replace(/\bPROTOCOL_FOUND\b/g, 'Protocol available for review');
}
/** Preserve source clinical fields (including scanner models), without changing stored records. */
export function recordData(value: unknown): unknown {
  if (typeof value === 'string') return recordText(value);
  if (Array.isArray(value)) return value.map(recordData);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [recordText(key), recordData(item)]));
  return value;
}
/** Clinical source prose may discuss risk models; that is not provider telemetry. */
export function clinicalSourceData(data: Data): Data {
  const clean = (value: unknown): unknown => {
    if (typeof value === 'string') return recordText(value).replace(/\bPROTOCOL_NOT_PUBLIC\b/g, 'Local pathway unavailable');
    if (Array.isArray(value)) return value.map(clean);
    if (value && typeof value === 'object') return clinicalSourceData(value as Data);
    return value;
  };
  return Object.fromEntries(Object.entries(data).filter(([key]) => key === 'response' || !technicalKey.test(key)).map(([key, value]) => [recordText(key), clean(value)]));
}
export function isTechnical(value: string): boolean {
  return technical.test(value) || /^\s*[{[]/.test(value) || /\b[A-Z][A-Za-z0-9_]*(?:Error|Exception)\b/.test(value) || /no rehearsal fallback/i.test(value);
}
function isTechnicalFailure(value: string): boolean {
  return isTechnical(value) && /error|failed|failure|timeout|exception|no rehearsal fallback/i.test(value);
}
export function clinicalError(value: unknown, status?: number): string {
  const message = recordText(value instanceof Error ? value.message : typeof value === 'string' ? value : '');
  if ([TIMEOUT_ERROR, CAPACITY_ERROR, REVIEW_ERROR].includes(message)) return message;
  if (status === 401 || /presenter.*(?:secret|access)|authentication|unauthorized/i.test(message)) {
    return /invalid|incorrect/i.test(message) ? 'The presenter secret was not accepted. Please try again.' : 'Presenter access is required to continue this meeting.';
  }
  if (/\bstart a new case\b/i.test(message)) return 'This meeting belongs to an earlier case. Start a new case to continue with the current dossier. The existing record remains available for review and export.';
  if (/selected case is not available/i.test(message)) return 'The selected case is not available. Reconnect to refresh the available cases; the current meeting has not been replaced.';
  if (/timeout|timed out/i.test(message)) return TIMEOUT_ERROR;
  if (/\bAPIConnectionError\b/.test(message)) return REVIEW_ERROR;
  if (status === 409 || /busy|already running|stale|plan.?version/i.test(message)) return 'The team is busy or the plan has changed. Review the latest meeting state and try again.';
  if (status === 422) return 'Please complete the required review information and submit again.';
  if (status === 429 || /429|rate.?limit|quota (?:is busy|exhausted|exceeded)|capacity|retry.after/i.test(message)) return CAPACITY_ERROR;
  if (/refreshing|meeting update|reconnect|fetch|network|connection/i.test(message)) return 'The meeting update could not be received. Your saved findings remain available. Reconnect before continuing.';
  if (!isTechnical(message) && /\b(?:tissue|biopsy|specimen|lesion|imaging|pathology|consent|guideline|evidence|patient|treatment|concurrence|clinical|comment|memory|meeting|review|plan)\b/i.test(message) && !(status && status >= 500)) return message;
  if (status && status >= 500 || /exception|failed|failure|error|unavailable/i.test(message) || isTechnical(message)) return REVIEW_ERROR;
  return 'This action could not be completed. Review the meeting state and try again.';
}
export function clinicalText(value: string, fallback = 'Clinical detail has not yet been provided.'): string {
  value = recordText(value).replace(/\bPROTOCOL_NOT_PUBLIC\b/g, 'Local pathway unavailable');
  if (value === 'PROTOCOL_FOUND') return 'Protocol available for review';
  if (isTechnicalFailure(value)) return clinicalError(value);
  return isTechnical(value) ? fallback : value || fallback;
}
export function clinicalItems(items: string[]): string[] {
  return [...new Set(items.flatMap(item => {
    if (!isTechnical(item)) return [clinicalText(item, '')];
    return /error|failed|failure|timeout|exception|429/i.test(item) ? [clinicalError(item)] : [];
  }))];
}
export function clinicalData(data: Data): Data {
  const clean = (value: unknown): unknown => {
    if (typeof value === 'string') return isTechnical(value) && /error|fail|exception|timeout/i.test(value) ? clinicalError(value) : clinicalText(value, 'See the clinical assessment; detailed audit information is retained in the export.');
    if (Array.isArray(value)) return value.map(clean);
    if (value && typeof value === 'object') return clinicalData(value as Data);
    return value;
  };
  return Object.fromEntries(Object.entries(data).filter(([key]) => !technicalKey.test(key)).map(([key, value]) => [recordText(key), key === 'dossier' ? recordData(value) : clean(value)]));
}

const TOOL_TASKS: Array<[RegExp, string]> = [
  [/compar.*imag|growth|diameter|volum/i, 'Compare current and prior lesion measurements, growth and measurement limitations.'],
  [/imag|radiolog/i, 'Review imaging reports, lesion measurements and comparison caveats.'],
  [/toxicity|treatment|oncolog|systemic/i, 'Review prior treatment, adverse effects and options requiring MDT discussion.'],
  [/surg|operab|resect|fitness/i, 'Review anatomical feasibility, patient fitness and procedural constraints.'],
  [/patholog|molecular|histolog|biomarker|specimen/i, 'Review tissue provenance, histology and molecular findings.'],
  [/applicab|scrutin|critical|match/i, 'Assess study applicability, population differences and limitations for this patient.'],
  [/dutch|richtlijn|esmo|guideline/i, 'Check relevant Dutch and European guidance and its conditions.'],
  [/protocol|ctis|trial/i, 'Review trial or institutional pathway availability and access limitations.'],
  [/pubmed|evidence|research|study|studies/i, 'Compare available research evidence, study design and patient relevance.'],
  [/patient.*(?:prefer|context)|preference|burden|support/i, 'Review stated patient preferences, treatment burden and support needs.'],
  [/patient|case|context|summary|timeline|history/i, 'Review the recorded diagnosis, history and current multidisciplinary question.'],
  [/memory/i, 'Consider an explicitly selected role-scoped memory alongside the case facts.'],
];
const EVENTS: Record<string, [string, string]> = {
  caseactivated: ['Case opened', 'The team is reviewing the recorded clinical question.'],
  caseloaded: ['Case available', 'Specialist workspaces have received the case context.'],
  casecontextupdated: ['Case context updated', 'Review the updated patient information before drawing conclusions.'],
  roleanalysisstarted: ['Specialist review started', 'The specialist is reviewing the case from their clinical perspective.'],
  reviewretryscheduled: ['Review taking longer', 'Another review attempt is scheduled. No new conclusion has been recorded.'],
  observationadded: ['Clinical observation', 'A specialist observation was recorded.'],
  evidencefound: ['Evidence available', 'A source is available for review of quality, access and applicability.'],
  uncertaintyraised: ['Uncertainty raised', 'A limitation or unanswered clinical question needs review.'],
  positiondrafted: ['Position drafted', 'A specialist has drafted an assessment for the MDT.'],
  positionpublished: ['Position published', 'A specialist position is available for multidisciplinary review.'],
  positionupdated: ['Position revised', 'Review the revised assessment and any remaining conditions.'],
  frictiondetected: ['Clinical question unresolved', 'Specialist positions require focused discussion before a plan can be agreed.'],
  frictionresolved: ['Question addressed', 'Review the recorded resolution and any retained uncertainty.'],
  targeteddiscussion: ['Focused discussion', 'Only the unresolved clinical questions are being revisited.'],
  followuprequested: ['Focused review requested', 'The chair has requested review of unresolved questions.'],
  guidancereceived: ['Human guidance received', 'The specialist will reconsider the assessment using the clinician’s guidance.'],
  humanguidance: ['Human guidance received', 'The specialist has received a clinician’s review instruction.'],
  memoryused: ['Memory considered', 'The selected memory is visible to the specialist; it does not become clinical evidence.'],
  memoryignored: ['Memory set aside', 'The selected memory will not guide this review.'],
  memoryforgotten: ['Memory forgotten', 'The selected memory has been removed from future consideration.'],
  evidencerequested: ['Focused review requested', 'The chair has asked the relevant specialties to revisit the unresolved questions.'],
  analysisretried: ['Specialist review restarted', 'A further review attempt has begun. No new conclusion has been recorded yet.'],
  analysisinterrupted: ['Review interrupted', 'A specialist review stopped before completing. No new clinical conclusion has been recorded.'],
  concurrenceinvalidated: ['Concurrence reset', 'The plan changed, so previously recorded concurrence no longer applies and must be given again.'],
  planproposed: ['MDT plan proposed', 'A conditional multidisciplinary plan is ready for review.'],
  planupdated: ['MDT plan revised', 'Review the new plan version before giving concurrence.'],
  concurrencegiven: ['Concurrence recorded', 'A role’s concurrence has been recorded against the reviewed plan version.'],
  objectionraised: ['Clinical objection raised', 'The objection returns the relevant question to focused discussion.'],
  decisioncaptured: ['MDT decision captured', 'The agreed demonstration decision and its conditions have been recorded.'],
  roomcleared: ['Meeting closed on the shared screens', 'The meeting was cleared from the room. The record stays available for review and export.'],
  caseclosed: ['Meeting concluded', 'The decision, evidence and review history remain available for inspection.'],
};
export interface ClinicalActivity { title: string; summary: string; failure: boolean }
const ROLE_NAME: Record<Role, string> = {
  radiology: 'Radiology', oncology: 'Oncology', surgery: 'Surgery', pathology: 'Pathology',
  research: 'Research', protocol: 'Protocol', patient: 'Patient perspective',
};
const AUTONOMY_NOTE: Record<string, string> = {
  AUTO: 'It carries no review flag of its own.',
  REVIEW: 'The specialty has flagged it for human review.',
  ESCALATE: 'The specialty has escalated it for expert clinical judgment.',
};
const MEMORY_ACTION: Record<string, [string, string]> = {
  use: ['Memory considered', 'A clinician applied a saved review preference. It is visible to the specialty as context and does not become clinical evidence.'],
  ignore: ['Memory set aside', 'A clinician set a saved review preference aside. It will not guide this review.'],
  forget: ['Memory forgotten', 'A clinician removed a saved review preference from future consideration.'],
};
export const DOCUMENT_NAME: Record<string, string> = { patient: 'Patient summary', clinician: 'Colleague letter' };
/** Why an outcome document failed, in words a reviewer can act on. Never hides the failure. */
export function documentError(message: string | null | undefined): string {
  const value = (message ?? '').trim();
  if (/not configured/i.test(value)) return 'The language model that writes outcome documents is not configured on this server. Nothing was drafted, and no scripted text was substituted.';
  if (/restart/i.test(value)) return 'The server restarted while this document was being drafted. Nothing was kept; regenerate to try again.';
  if (/authenticat|access denied|401|403/i.test(value)) return 'The drafting service refused access. Nothing was drafted; restore access, then regenerate.';
  if (/quota|busy|429|rate.?limit/i.test(value)) return 'The drafting service is busy. Nothing was drafted; regenerate in a moment.';
  if (/timed out|timeout/i.test(value)) return 'Drafting did not finish in time. No scripted text was substituted; regenerate to try again.';
  if (!value || isTechnical(value)) return 'Drafting failed. No scripted text was substituted; regenerate to try again.';
  return recordText(value);
}
function communicationActivity(item: Data, type: string): ClinicalActivity | null {
  if (!type.startsWith('communication')) return null;
  const several = Array.isArray(item.audiences);
  const name = several ? 'Outcome documents' : DOCUMENT_NAME[String(item.audience)] ?? 'Outcome document';
  const note = typeof item.summary === 'string' ? item.summary.trim() : '';
  const revision = typeof item.revision === 'number' && item.revision > 1 ? ` · revision ${item.revision}` : '';
  const reviewer = typeof item.reviewer === 'string' && item.reviewer.trim() ? item.reviewer.trim() : 'A clinician';
  if (type === 'communicationdraftingstarted') return { title: `${name}: drafting${revision}`, summary: 'The writing skill is drafting from the recorded outcome only. A named clinician reviews it before use.', failure: false };
  if (type === 'communicationactivity') {
    if (item.activity === 'ReviewRetryScheduled') return { title: `${name}: waiting`, summary: 'The language model is busy; drafting will retry automatically.', failure: false };
    return { title: `${name}: drafting`, summary: note && !isTechnical(note) ? recordText(note) : 'The writing skill is working on the draft.', failure: false };
  }
  if (type === 'communicationdrafted') return { title: `${name} ready for review${revision}`, summary: note && !isTechnical(note) ? note : 'A draft is ready for clinician review.', failure: false };
  if (type === 'communicationfailed') return { title: `${name} could not be drafted`, summary: documentError(note), failure: true };
  if (type === 'communicationapproved') return { title: `${name} approved`, summary: note ? recordText(note) : `${reviewer} approved the draft.`, failure: false };
  if (type === 'communicationchangesrequested') return { title: `${name}: changes requested`, summary: `${reviewer} asked for: ${recordText(note)}`, failure: false };
  return null;
}
/** Narrates a recorded meeting event for clinicians, without provider or transport detail. */
function structuredActivity(item: Data, type: string, role?: Role): ClinicalActivity | null {
  const who = role ? ROLE_NAME[role] : null;
  if (type === 'phasechanged') {
    const phase = typeof item.phase === 'string' ? item.phase : '';
    const label = PHASE_LABELS[phase];
    if (!label) return null;
    return { title: `Meeting stage: ${label}`, summary: PHASE_MEANING[phase] ?? '', failure: phase === 'ERROR' };
  }
  if (type === 'humanguidancereceived' || type === 'guidancereceived' || type === 'humanguidance') {
    const note = typeof item.summary === 'string' && item.summary.trim() ? clinicalText(item.summary, '') : '';
    return {
      title: who ? `Clinician guidance to ${who}` : 'Clinician guidance received',
      summary: note || `A clinician sent a focused review instruction${who ? ` to ${who}` : ''}. The specialty will reconsider its assessment.`,
      failure: false,
    };
  }
  if (type === 'memoryaction') {
    const known = MEMORY_ACTION[typeof item.action === 'string' ? item.action : ''];
    return known ? { title: known[0], summary: known[1], failure: false } : null;
  }
  if (type === 'roleanalysisstarted') {
    const round = typeof item.round === 'number' ? item.round : null;
    return {
      title: who ? `${who} review started` : 'Specialist review started',
      summary: `${who ?? 'The specialty'} is reviewing the same patient record from its own perspective${round && round > 1 ? `, in discussion round ${round}` : ''}. ${role ? ROLE_FOCUS[role] : ''}`.trim(),
      failure: false,
    };
  }
  if (type === 'positionpublished' || type === 'positionupdated') {
    const revision = typeof item.revision === 'number' ? item.revision : null;
    const autonomy = typeof item.autonomy === 'string' ? AUTONOMY_NOTE[item.autonomy] : undefined;
    const revised = type === 'positionupdated';
    return {
      title: who ? `${who} ${revised ? 'revised its position' : 'published a position'}` : revised ? 'Position revised' : 'Position published',
      summary: [
        `${who ?? 'A specialty'} ${revised ? 'revised its assessment after the focused discussion' : 'published an assessment for the team to compare'}${revision ? ` (revision ${revision})` : ''}.`,
        autonomy,
      ].filter(Boolean).join(' '),
      failure: false,
    };
  }
  if (type === 'concurrencegiven') {
    const human = item.actor === 'human';
    return {
      title: who ? `${who} concurrence recorded` : 'Concurrence recorded',
      summary: `${human ? 'A clinician' : `${who ?? 'The specialty'}`} recorded concurrence with the reviewed plan version.${human ? '' : ' Human sign-off is still required for the roles that carry it.'}`,
      failure: false,
    };
  }
  if (type === 'frictiondetected') {
    const question = typeof item.question === 'string' ? clinicalText(item.question, '') : '';
    return {
      title: 'Clinical question unresolved',
      summary: question ? `The specialties do not yet agree: ${question}` : 'Specialist positions require focused discussion before a plan can be agreed.',
      failure: false,
    };
  }
  return null;
}
export function clinicalActivity(item: Data, role?: Role): ClinicalActivity {
  const type = typeof item.type === 'string' ? normalized(item.type) : '';
  const communication = communicationActivity(item, type);
  if (communication) return communication;
  const raw = [item.summary, item.message, item.question, item.resolution, item.assessment, item.position, item.comment, item.detail].find(value => typeof value === 'string' && value.trim()) as string | undefined;
  const error = item.error === true ? raw || type : item.error ?? (/failed|failure|error|unavailable/.test(type) ? raw || type : null);
  if (error) return { title: 'Review needs attention', summary: clinicalError(error, typeof item.status_code === 'number' ? item.status_code : undefined), failure: true };
  const task = typeof item.tool === 'string' ? TOOL_TASKS.find(([pattern]) => pattern.test(item.tool as string))?.[1] : undefined;
  const focus = role ? ROLE_FOCUS[role] : 'Reviewing case information and evidence for the multidisciplinary assessment.';
  if (item.model || item.deployment || item.model_request_id || ['modelstarted', 'modelcompleted', 'modelrequested', 'modelresponse', 'inferencecompleted'].includes(type) || !task && raw && isTechnical(raw) && type === 'observationadded') {
    return { title: 'Specialist assessment', summary: focus, failure: false };
  }
  const structured = structuredActivity(item, type, role);
  if (structured) return structured;
  const known = EVENTS[type];
  const isTool = /^(toolstarted|toolcompleted|toolresult|toolrequested)$/.test(type) || Boolean(task);
  if (!known && !isTool) return { title: 'Team update', summary: GENERIC_UPDATE, failure: false };
  const genericSummary = raw && /^(?:inspected|loaded|retrieved|received|reviewed)\s+(?:(?:role.scoped|case|patient)\s+)?context\.?$/i.test(raw.trim());
  const safeSummary = raw && !isTechnical(raw) && !genericSummary && raw.trim().length > 12 ? clinicalText(raw) : undefined;
  return {
    title: known?.[0] ?? (/started|requested/.test(type) ? 'Review in progress' : 'Review step completed'),
    summary: safeSummary ?? task ?? known?.[1] ?? focus,
    failure: type === 'uncertaintyraised' || type === 'reviewretryscheduled',
  };
}

export const PHASE_LABELS: Record<string, string> = {
  IDLE: 'Awaiting case', CASE_LOADING: 'Opening case', INITIAL_ANALYSIS: 'Initial specialist review',
  POSITION_COLLECTION: 'Collecting specialist positions', FRICTION_ANALYSIS: 'Reviewing disagreement',
  TARGETED_DISCUSSION: 'Focused clinical discussion', POSITION_UPDATE: 'Updating specialist positions',
  PLAN_PROPOSAL: 'Proposing the MDT plan', CONCURRENCE: 'Reviewing the plan',
  DECISION_CAPTURED: 'Decision captured', ERROR: 'Review needs attention',
};
/** Plain-language meaning of each meeting stage for clinicians following the demonstration. */
export const PHASE_MEANING: Record<string, string> = {
  IDLE: 'No case is open. Select a case to begin the multidisciplinary review.',
  CASE_LOADING: 'The patient record is being distributed to each specialty workspace.',
  INITIAL_ANALYSIS: 'Each specialty is reviewing the same record independently, from its own clinical perspective.',
  POSITION_COLLECTION: 'Specialties are publishing their assessments so the team can compare them side by side.',
  FRICTION_ANALYSIS: 'The published positions are being compared to identify where the specialties actually disagree.',
  TARGETED_DISCUSSION: 'Only the unresolved clinical questions are being revisited, by the specialties they involve.',
  POSITION_UPDATE: 'Specialties are revising their assessments in light of the focused discussion.',
  PLAN_PROPOSAL: 'A conditional multidisciplinary plan has been drawn from the agreed positions.',
  CONCURRENCE: 'Each required specialty is reviewing the proposed plan and recording concurrence or objection.',
  DECISION_CAPTURED: 'The agreed plan, its conditions and the review history have been recorded.',
  ERROR: 'A specialist review did not complete. No new clinical conclusion has been recorded.',
};
export function statusLabel(value: string): string {
  if (/ERROR|FAIL/i.test(value)) return 'Review needs attention';
  return PHASE_LABELS[value] ?? ({
    PUBLISHED: 'Position published', READY: 'Ready for review', ANALYZING: 'Reviewing case',
    ANALYSING: 'Reviewing case', SEARCHING: 'Reviewing evidence', CHECKING: 'Checking applicability',
    REASSESSING: 'Reconsidering assessment', RUNNING: 'Review in progress', WORKING: 'Review in progress',
    COMPLETED: 'Review completed', COMPLETE: 'Review completed', FAILED: 'Review needs attention',
    SUPPORT: 'Supports plan', CONDITIONAL: 'Conditional support', UNCERTAIN: 'Uncertain',
    AUTO: 'Automatic publication', REVIEW: 'Human review requested', ESCALATE: 'Expert judgment needed',
    AVAILABLE: 'Available', USED: 'Used', IGNORED: 'Ignored', FORGOTTEN: 'Forgotten', PENDING: 'Awaiting review',
  } as Record<string, string>)[value] ?? 'Review update';
}

function clinicalTrace(trace: Trace): Trace {
  return {
    assessment: clinicalText(trace.assessment, 'The specialist assessment is being prepared.'),
    hypothesis: trace.hypothesis ? clinicalText(trace.hypothesis, 'The clinical hypothesis is not yet available.') : '',
    observations: clinicalItems(trace.observations),
    uncertainties: clinicalItems(trace.uncertainties),
    evidence_checking: clinicalItems(trace.evidence_checking),
    next_action: trace.next_action && !isTechnicalFailure(trace.next_action) ? clinicalText(trace.next_action, 'Continue reviewing the unresolved clinical questions.') : '',
  };
}
function clinicalPosition(position: Position, meeting: Meeting): Position {
  return {
    ...position,
    position: clinicalText(position.position, 'A specialist position is being prepared.'),
    recommendation: clinicalText(position.recommendation, 'Review the available evidence and unresolved conditions with the team.'),
    claims: position.claims.map(claim => ({ ...claim, claim: clinicalText(claim.claim, 'Inspect the linked evidence before interpreting this claim.') })),
    uncertainties: clinicalItems(position.uncertainties),
    questions_for_mdt: clinicalItems(position.questions_for_mdt),
    provenance: clinicalItems(position.provenance).map(item => meeting.evidence.find(source => source.id === item)?.title ?? item),
    trace: clinicalTrace(position.trace),
  };
}
/** Presentation-only copy: raw snapshots and exported audit records stay unchanged. */
export function presentMeeting(meeting: Meeting | null): Meeting | null {
  if (!meeting) return null;
  const roles: Partial<Record<Role, RoleState>> = {};
  for (const [key, role] of Object.entries(meeting.roles)) {
    if (!role) continue;
    roles[key as Role] = {
      ...role, context: clinicalCaseKind(meeting.case) ? clinicalSourceData(role.context) : clinicalData(role.context), trace: clinicalTrace(role.trace),
      position: role.position ? clinicalPosition(role.position, meeting) : null,
      guidance: role.guidance.map(item => clinicalText(item, 'Clinician guidance was recorded for this review.')),
      error: role.error ? clinicalError(role.error) : isTechnicalFailure(role.trace.next_action) ? clinicalError(role.trace.next_action) : null,
    };
  }
  return {
    ...meeting, roles, case: clinicalCaseKind(meeting.case) ? { ...clinicalSourceData(meeting.case), dossier: recordData(meeting.case.dossier) } : clinicalData(meeting.case),
    evidence: meeting.evidence.map(source => ({
      ...source, title: clinicalText(source.title), passage: clinicalText(source.passage, ''),
      authority: clinicalText(source.authority), limitations: clinicalItems(source.limitations),
      scrutiny: Object.fromEntries(Object.entries(source.scrutiny).map(([key, value]) => [key, clinicalText(value)])),
    })),
    error: meeting.error ? clinicalError(meeting.error) : null,
    frictions: meeting.frictions.map(item => ({ ...item, question: clinicalText(item.question), missing: clinicalItems(item.missing), resolution: item.resolution ? clinicalText(item.resolution) : null })),
    memories: meeting.memories.map(item => ({ ...item, text: clinicalText(item.text), source: clinicalText(item.source, 'Source recorded in the meeting record.') })),
    objections: meeting.objections.map(clinicalData),
    plan: meeting.plan ? { ...meeting.plan, title: clinicalText(meeting.plan.title, 'Proposed MDT plan'), summary: clinicalText(meeting.plan.summary), actions: clinicalItems(meeting.plan.actions), conditions: clinicalItems(meeting.plan.conditions) } : null,
  };
}
