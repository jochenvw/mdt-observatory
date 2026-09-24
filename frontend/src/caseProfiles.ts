import type { Data, Role } from './types';

export type ClinicalCaseKind = 'crc_conversion_response' | 'pancreatic_perioperative';
const caseKinds: Record<string, ClinicalCaseKind> = {
  'CASE-MDT-CRC-WT-2026-002': 'crc_conversion_response',
  'CASE-MDT-PDAC-PERIOP-2026-003': 'pancreatic_perioperative',
};

export function clinicalCaseKind(data: Data): ClinicalCaseKind | null {
  const id = String(data.id ?? data.case_id ?? '');
  if (caseKinds[id]) return caseKinds[id];
  return data.kind === 'crc_conversion_response' || data.kind === 'pancreatic_perioperative' ? data.kind : null;
}

interface ClinicalProfile {
  title: string;
  focus: [string, string, string];
  guidance: string;
  /** Example human answer when this specialty's agent asks for input: a reported finding. */
  reply?: string;
}
/** Default (BRAF) case: example radiologist answer to the imaging question. */
export const DEFAULT_RADIOLOGY_REPLY = 'I reviewed the liver MRI and chest CT: all nine liver sites are mapped with clear vessel margins, the remnant looks adequate, and the lung nodule is stable and not suspicious.';
const conversionProfiles: Record<Role, ClinicalProfile> = {
  radiology: {
    title: 'Colorectal response imaging',
    focus: ['Baseline site reconciliation', 'Disappearing lesions', 'Indeterminate findings'],
    guidance: 'Review all 11 baseline liver sites against current imaging: confirm which disappeared lesions are truly eliminated, assess the uncertain 7 mm IVa focus and state vessel and remnant limitations, without inventing a lesion map.',
    reply: 'I reviewed the baseline and current MRI: all 11 original liver sites are mapped, the disappeared lesions are marked for intra-operative ultrasound, and the 7 mm IVa focus is most likely residual disease to include in the plan. Vessel interfaces and the remnant look adequate for parenchymal-sparing treatment.',
  },
  oncology: {
    title: 'Conversion response and tolerability',
    focus: ['Treatment response', 'Cumulative toxicity', 'Treatment interruption'],
    guidance: 'Review the response after eight mFOLFOX6/bevacizumab cycles alongside grade 2 neuropathy, detectable ctDNA and the conditions for perioperative treatment interruption.',
  },
  surgery: {
    title: 'Colorectal local-treatment review',
    focus: ['Baseline site coverage', 'Clearance feasibility', 'Procedural sequence'],
    guidance: 'Assess whether every baseline liver site can be addressed, including disappearing lesions. State mapping gaps and fitness requirements before choosing the procedural sequence.',
  },
  pathology: {
    title: 'Colorectal tissue and plasma findings',
    focus: ['RAS/BRAF wild type', 'Tissue and plasma', 'Assay limitations'],
    guidance: 'Distinguish the RAS/BRAF wild-type tissue profile from persistent plasma ctDNA. Describe assay limits without treating molecular detection as an independent surgery veto.',
  },
  research: {
    title: 'Colorectal conversion evidence',
    focus: ['Conversion populations', 'Disappearing lesions', 'Evidence limits'],
    guidance: 'Review evidence applicable to RAS/BRAF wild-type conversion therapy and disappearing liver metastases. Separate systemic response, local clearance and survival endpoints; retain source access limits.',
  },
  protocol: {
    title: 'Colorectal sequencing conditions',
    focus: ['Treatment timing', 'Clearance conditions', 'Unresolved requirements'],
    guidance: 'List the conditions for local treatment versus further systemic therapy, including bevacizumab interruption, lesion reconciliation and toxicity. Do not infer pathway approval.',
  },
  patient: {
    title: 'Patient priorities and caregiving',
    focus: ['Stated goals', 'Caregiving responsibilities', 'Treatment burden'],
    guidance: 'Discuss independence, neuropathy and treatment burden alongside his responsibilities caring for his wife. Confirm support and preferences rather than assuming consent to a treatment sequence.',
  },
};
const pancreaticProfiles: Record<Role, ClinicalProfile> = {
  radiology: {
    title: 'Pancreatic response imaging',
    focus: ['Pancreatic head lesion', 'Vascular interfaces', 'Imaging limitations'],
    guidance: 'Review pancreatic tumour response and vascular interfaces. Distinguish technically plausible resection from physiological fitness; retain imaging uncertainty.',
    reply: 'I reviewed the pancreatic imaging: the SMV/portal interface looks reconstructable and no arterial involvement is seen. Aortic stenosis and cardiac reserve still need the echo and anaesthetic review before surgery.',
  },
  oncology: {
    title: 'Pancreatic treatment and recovery',
    focus: ['Treatment response', 'Tolerance and reserve', 'Perioperative sequence'],
    guidance: 'Weigh pancreatic treatment response against tolerance, frailty and recovery needs. Describe alternatives and uncertainties without equating anatomical response with operative fitness.',
  },
  surgery: {
    title: 'Surgical / perioperative review',
    focus: ['Technical feasibility', 'Physiological reserve', 'Recovery requirements'],
    guidance: 'Separate technical resectability from physiological approval. Review HFpEF, moderate aortic stenosis, renal-stage discrepancy, frailty and PONV; treat quoted risks as illustrative and unvalidated, with no automated ICU choice.',
  },
  pathology: {
    title: 'Pancreatic tissue findings',
    focus: ['Diagnostic specimen', 'Molecular findings', 'Sampling limitations'],
    guidance: 'Review the pancreatic diagnostic specimen and supplied molecular findings. Keep sampling limits and missing findings explicit; do not import another case’s biomarkers or treatment assumptions.',
  },
  research: {
    title: 'Pancreatic and perioperative evidence',
    focus: ['Population applicability', 'Risk-model validity', 'Source access'],
    guidance: 'Check pancreatic and perioperative evidence applicability, including comorbidity and frailty exclusions. Label the supplied risk estimates illustrative and unvalidated, not calibrated predictions.',
  },
  protocol: {
    title: 'Perioperative review conditions',
    focus: ['Multidisciplinary assessment', 'Optimisation requirements', 'Human escalation planning'],
    guidance: 'Identify cardiac, renal, frailty and anaesthetic review requirements. Preserve the stated CKD stage and eGFR discrepancy; postoperative monitoring or ICU choices require human review, not automatic allocation.',
  },
  patient: {
    title: 'Cognition, independence and recovery',
    focus: ['Cognition and independence', 'Recovery burden', 'Stated preferences'],
    guidance: 'Discuss cognition, independence, frailty and postoperative recovery in the patient’s own priorities. Explore acceptable burdens without assuming consent or selecting ICU care automatically.',
  },
};

export function clinicalProfile(data: Data, role: Role): ClinicalProfile | null {
  const kind = clinicalCaseKind(data);
  return kind === 'crc_conversion_response' ? conversionProfiles[role] : kind === 'pancreatic_perioperative' ? pancreaticProfiles[role] : null;
}
