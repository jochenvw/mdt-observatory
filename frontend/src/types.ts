export const ROLES = ['radiology', 'oncology', 'surgery', 'pathology', 'research', 'protocol', 'patient'] as const;
export type Role = typeof ROLES[number];
export type Mode = 'rehearsal' | 'azure';
export type Workspace = 'cases' | 'central' | 'chair' | 'wall' | Role;
export interface CaseSummary { id: string; title: string; patient_label: string; stage: string; question: string }
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
  access: 'PUBLIC_FULL_TEXT' | 'PUBLIC_ABSTRACT_ONLY' | 'LICENSED_INTERNAL' | 'NOT_ACCESSIBLE';
  patient_match: 'HIGH' | 'PARTIAL' | 'LOW';
  passage: string;
  limitations: string[];
  scrutiny: Record<string, string>;
  synthetic: boolean;
  retrieval: string;
}
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
  title: string;
  summary: string;
  actions: string[];
  conditions: string[];
  evidence_ids: string[];
  created_at: string;
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
export interface Meeting {
  id: string;
  phase: Phase;
  mode: Mode;
  case: Data;
  roles: Partial<Record<Role, RoleState>>;
  evidence: Evidence[];
  frictions: Friction[];
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
}
export interface VoiceAgent {
  key: string;
  label: string;
  persona: string;
  elevenlabs_voice_id: string;
  preview_text: string;
  role: Role | null;
}
export interface VoiceSettings {
  provider: 'elevenlabs';
  api_key_configured: boolean;
  external_processing_disclosure: string;
  fallback: 'browser_speech_synthesis';
  agents: VoiceAgent[];
}
export interface VoiceTurn {
  id: string;
  sequence: number;
  agent_key: string;
  speaker: string;
  category: 'chair' | 'specialist' | 'human' | 'checkpoint';
  text: string;
  evidence_ids: string[];
  timestamp_offset_seconds: number;
}
export interface VoiceContributionInput {
  transcript: string;
  corrected_transcript?: string | null;
  addressed_to?: string | null;
  confirmation_mode: boolean;
}
export interface VoiceContributionAccepted {
  meeting: Meeting;
  routed_to: string[];
  turns: VoiceTurn[];
}
export interface Config { modes: Mode[]; auth_required: boolean; version: string; voice: VoiceSettings }
