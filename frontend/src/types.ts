export const ROLES = ['radiology', 'oncology', 'surgery', 'pathology', 'research', 'protocol', 'patient'] as const;
export type Role = typeof ROLES[number];
export type Mode = 'rehearsal' | 'azure';
export type Workspace = 'join' | 'cases' | 'central' | 'chair' | 'wall' | 'outcome' | Role;
export interface CaseSummary { id: string; title: string; patient_label: string; stage: string; question: string; preferred_language?: string }
export const PHASES = ['IDLE', 'CASE_LOADING', 'INITIAL_ANALYSIS', 'POSITION_COLLECTION', 'FRICTION_ANALYSIS', 'TARGETED_DISCUSSION', 'POSITION_UPDATE', 'PLAN_PROPOSAL', 'CONCURRENCE', 'DECISION_CAPTURED'] as const;
export type Phase = typeof PHASES[number] | 'ERROR';
export type Data = Record<string, unknown>;
export interface Trace {
  assessment: string;
  observations: string[];
  hypothesis: string;
  uncertainties: string[];
  evidence_checking: string[];
  next_action: string;
}
export interface Claim { claim: string; evidence_ids: string[] }
export interface Position {
  role: Role;
  case_id: string;
  position: string;
  confidence: number;
  autonomy: 'AUTO' | 'REVIEW' | 'ESCALATE';
  claims: Claim[];
  uncertainties: string[];
  recommendation: string;
  questions_for_mdt: string[];
  human_intervention: boolean;
  provenance: string[];
  stance: 'SUPPORT' | 'CONDITIONAL' | 'UNCERTAIN';
  friction_keys: string[];
  trace: Trace;
}
export interface RoleState {
  role: Role;
  label: string;
  status: string;
  context: Data;
  trace: Trace;
  position: Position | null;
  activity: Data[];
  guidance: string[];
  revision: number;
  error: string | null;
}
export interface Evidence {
  id: string;
  title: string;
  url: string;
  date: string;
  authority: string;
  region: 'NL' | 'EU' | 'INTERNATIONAL' | 'US';
  kind: string;
  access:
    | 'PUBLIC_FULL_TEXT'
    | 'PUBLIC_ABSTRACT_ONLY'
    | 'METADATA_ONLY'
    | 'LICENSED_INTERNAL'
    | 'NOT_ACCESSIBLE';
  patient_match: 'HIGH' | 'PARTIAL' | 'LOW' | 'NOT_ASSESSED';
  passage: string;
  limitations: string[];
  scrutiny: Record<string, string>;
  synthetic: boolean;
  retrieval: 'CURATED' | 'LIVE' | 'RECORDED';
  retrieved_at?: string;
  retrieved_via?: string;
  source_tier?: SourceTier;
  endpoint?: string;
  query?: string;
  identifiers?: Record<string, string>;
}
export type SourceTier = 'NL' | 'EU' | 'INTL' | 'US' | 'PREPRINT';
export interface Friction {
  id: string;
  question: string;
  roles: Role[];
  missing: string[];
  blocking: boolean;
  resolved: boolean;
  resolution: string | null;
}
export interface Memory {
  id: string;
  role: Role;
  clinician_id: string;
  category: 'FACTUAL_PATIENT' | 'INSTITUTIONAL_PRACTICE' | 'CLINICIAN_PREFERENCE' | 'EXPERIENTIAL_NUDGE';
  text: string;
  source: string;
  date: string;
  status: 'AVAILABLE' | 'USED' | 'IGNORED' | 'FORGOTTEN';
}
export interface Plan {
  version: number;
  direction: 'INVESTIGATE_FURTHER' | 'PROCEED_TREATMENT';
  title: string;
  decision: string;
  summary: string;
  actions: string[];
  conditions: string[];
  resolved_requirements: RequirementResolution[];
  evidence_ids: string[];
  created_at: string;
}
export interface RequirementResolution {
  requirement_id: string;
  role: Role;
  status: 'CONFIRMED';
  human_input: string;
  finding: string;
  timestamp: string;
}
export interface Concurrence {
  role: Role;
  plan_version: number;
  actor: 'human' | 'agent';
  comment: string;
  timestamp: string;
}
export interface MeetingEvent {
  id: number;
  meeting_id: string;
  type: string;
  role: Role | null;
  payload: Data;
  timestamp: string;
}
export const AUDIENCES = ['patient', 'clinician'] as const;
export type Audience = typeof AUDIENCES[number];
export type CommunicationStatus = 'DRAFTING' | 'DRAFT' | 'CHANGES_REQUESTED' | 'APPROVED' | 'FAILED';
export interface CommunicationSection { id: string; heading: string; paragraphs: string[]; bullets: string[]; columns: string[]; rows: string[][]; source_refs: string[] }
export interface GlossaryTerm { term: string; meaning: string }
export interface CommunicationCitation { evidence_id: string; title: string; authority: string; access: string; verification: string }
export interface CommunicationChecks {
  word_count: number;
  word_target: [number, number];
  sentence_count: number;
  average_sentence_words: number;
  longest_sentence_words: number;
  reading_ease: number;
  reading_formula: string;
  grade_level: number | null;
  reading_target: string;
  language: string;
  detected_language: string | null;
  unexplained_terms: string[];
  uncovered_refs: string[];
  unsupported_numbers: string[];
  unresolved_citations: string[];
  unknown_refs: string[];
}
export interface CommunicationReview { action: 'approve' | 'request_changes' | 'regenerate'; reviewer: string; role: Role | null; actor: 'human'; comment: string; plan_version: number; revision: number; timestamp: string }
export interface Communication {
  audience: Audience;
  plan_version: number;
  revision: number;
  status: CommunicationStatus;
  generated_by: 'rehearsal' | 'azure';
  author_role: string;
  language: string;
  title: string;
  sections: CommunicationSection[];
  glossary: GlossaryTerm[];
  questions_to_ask: string[];
  citations: CommunicationCitation[];
  checks: CommunicationChecks | null;
  reviews: CommunicationReview[];
  requested_changes: string[];
  approved_by: string | null;
  approved_role: Role | null;
  approved_at: string | null;
  approved_revision: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}
export interface Meeting {
  id: string;
  phase: Phase;
  mode: Mode;
  case: Data;
  roles: Partial<Record<Role, RoleState>>;
  evidence: Evidence[];
  frictions: Friction[];
  requirement_resolutions?: RequirementResolution[];
  memories: Memory[];
  plan: Plan | null;
  concurrences: Partial<Record<Role, Concurrence>>;
  objections: Data[];
  events: MeetingEvent[];
  round: number;
  busy: boolean;
  error: string | null;
  created_at: string;
  closed_at: string | null;
  communications?: Partial<Record<Audience, Communication>>;
}
export interface Config { modes: Mode[]; default_mode: Mode; auth_required: boolean; presenter: boolean; version: string }
