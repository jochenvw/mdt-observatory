import { useState } from 'react';
import { ArrowRight, ChevronDown, Eye, Heart, Layers, ScanLine, ShieldCheck } from 'lucide-react';
import { label, text } from './helpers';
import { recordData, recordText } from './presentation';
import { Badge, EvidenceTable, SectionHeading } from './ui';
import type { EvidenceSelection } from './ui';
import type { Data, Meeting, Role } from './types';
import { clinicalCaseKind, clinicalProfile } from './caseProfiles';

const panel = 'min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-5 sm:p-6';
export const object = (value: unknown): Data => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Data : {};
const rows = (value: unknown): Data[] => Array.isArray(value) ? value.map(object) : [];
const path = (value: unknown, ...keys: string[]): unknown => keys.reduce<unknown>((item, key) => object(item)[key], value);
const shown = (value: unknown) => recordText(text(value)).replace(/\*\*([^*]+)\*\*/g, '$1');
export function isConversionCase(data: Data): boolean {
  return !clinicalCaseKind(data)
    && shown(data.id ?? data.case_id ?? path(data.dossier, 'case', 'case_id')) === 'CASE-MDT-CRC-BRAF-2026-001'
    && Boolean(path(data.dossier, 'imaging', 'baseline_liver_MRI'));
}

const fieldLabels: Record<string, string> = {
  weight_kg_at_diagnosis: 'Weight at diagnosis (kg)', bmi: 'BMI (kg/m²)', ctDNA: 'ctDNA',
  ECOG_performance_status: 'ECOG performance status', baseline_CT_CAP: 'Baseline CT chest / abdomen / pelvis',
  baseline_liver_MRI: 'Baseline liver MRI', baseline_FDG_PET_CT: 'Baseline FDG PET/CT',
  StudyInstanceUID: 'Study instance UID', CEA_ug_L: 'CEA (µg/L)', CA19_9_kU_L: 'CA19-9 (kU/L)',
  BRAF_V600E_VAF_percent: 'BRAF V600E VAF (%)', APC_variant_VAF_percent: 'APC variant VAF (%)',
  TP53_variant_VAF_percent: 'TP53 variant VAF (%)', APC_pGlu1309fs_VAF_percent: 'APC p.Glu1309fs VAF (%)',
  TP53_R248Q_VAF_percent: 'TP53 R248Q VAF (%)', tumor_mutational_burden_mut_Mb: 'Tumor mutational burden (mut/Mb)',
  eGFR_mL_min_1_73m2: 'eGFR (mL/min/1.73 m²)', DWI_b_values_s_mm2: 'DWI b values (s/mm²)',
  estimated_FLR_percent: 'Estimated future liver remnant (%)',
  parenchymal_sparing_strategy_expected_remnant_percent: 'Predicted parenchymal-sparing remnant (%)',
  TNM_AJCC8: 'TNM / AJCC 8', HGVS_c: 'HGVS coding DNA', HGVS_p: 'HGVS protein',
  AE1_AE3: 'AE1/AE3', CA19_9: 'CA19-9', NTRK1_2_3_fusion: 'NTRK1/2/3 fusion',
  POLE_POLD1_pathogenic_variant: 'POLE/POLD1 pathogenic variant',
};
const units: Array<[string, string]> = [
  ['_x10e9_L', '×10⁹/L'], ['_mmol_mol', 'mmol/mol'], ['_mmol_L', 'mmol/L'], ['_umol_L', 'µmol/L'],
  ['_g_dL', 'g/dL'], ['_ug_L', 'µg/L'], ['_mg_L', 'mg/L'], ['_g_L', 'g/L'], ['_U_L', 'U/L'],
  ['_percent', '%'], ['_mmHg', 'mmHg'], ['_s_mm2', 's/mm²'], ['_mm', 'mm'], ['_cm', 'cm'],
  ['_mL', 'mL'], ['_kg', 'kg'], ['_fL', 'fL'], ['_bpm', 'bpm'], ['_kVp', 'kVp'],
  ['_MBq', 'MBq'], ['_min', 'min'], ['_C', '°C'], ['_T', 'T'],
];
export function recordLabel(key: string): string {
  if (fieldLabels[key]) return fieldLabels[key];
  const unit = units.find(([suffix]) => key.endsWith(suffix));
  const base = unit ? key.slice(0, -unit[0].length) : key;
  const name = base.split('_').map(word => /^(?:[A-Z0-9]+|ctDNA|pMMR|HbA1c|SUVmax|eGFR|S\d[a-b]?)$/.test(word) ? word : label(word)).join(' ');
  return `${recordText(name)}${unit ? ` (${unit[1]})` : ''}`;
}
export function RecordValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return value.length ? <ol className="space-y-3 border-l border-cp-border pl-4">{value.map((item, index) => <li key={index}><RecordValue value={item} /></li>)}</ol> : <span>None recorded</span>;
  if (value !== null && typeof value === 'object') return <dl className="space-y-3">{Object.entries(value).map(([key, item]) => <div key={key} className="min-w-0 border-b border-cp-border pb-3 last:border-0"><dt className="mb-1 text-xs font-semibold text-cp-text-muted">{recordLabel(key)}</dt><dd className="min-w-0 break-words text-sm leading-7">{typeof item === 'object' && item !== null ? <div className="mt-2 border-l border-cp-border pl-3"><RecordValue value={item} /></div> : <RecordValue value={item} />}</dd></div>)}</dl>;
  return <span className="whitespace-pre-line break-words">{shown(value)}</span>;
}
function RecordSection({ title, value, testId, collapsible = false }: { title: string; value: unknown; testId?: string; collapsible?: boolean }) {
  if (collapsible) return <details data-testid={testId} className={panel}><summary className="justify-between font-semibold">{title}<ChevronDown size={16} /></summary><div className="mt-4"><RecordValue value={value} /></div></details>;
  return <article data-testid={testId} className={panel}><h3 className="mb-4 text-lg">{title}</h3><RecordValue value={value} /></article>;
}

export function CompleteCaseRecord({ data }: { data: Data }) {
  const dossier = object(recordData(data.dossier));
  const summary = Object.fromEntries(Object.entries(data).filter(([key]) => key !== 'dossier'));
  return <div data-testid="complete-case-record" className="space-y-4">
    <p className="text-sm leading-7 text-cp-text-muted">The complete supplied clinical record, grouped by source section. Dates, units, uncertainty and nested findings are retained. Source narrative is discussion material, not an adopted MDT decision.</p>
    <details className={`${panel} [&>summary]:font-semibold`}><summary>Case overview and source narrative</summary><div className="mt-5"><RecordValue value={recordData(summary)} /></div></details>
    {Object.entries(dossier).map(([key, value]) => <details key={key} data-testid={`record-section-${key}`} className={`${panel} [&>summary]:font-semibold`}>
      <summary>{recordLabel(key)}</summary><div className="mt-5"><RecordValue value={value} /></div>
    </details>)}
    {!Object.keys(dossier).length && <RecordValue value={recordData(summary)} />}
  </div>;
}
export function CaseTimeline({ data }: { data: Data }) {
  if (clinicalCaseKind(data)) return <section data-testid="case-timeline" className={`${panel} my-5`}>
    <SectionHeading eyebrow="SUPPLIED CLINICAL HISTORY" title="Treatment history and response" />
    <RecordValue value={recordData({ history: data.history, treatment: data.treatment, previous_treatment: data.previous_treatment })} />
    <p className="mt-4 text-xs leading-6 text-cp-text-muted">Dated findings and uncertainties are retained in the complete case record. No additional measurements or events have been inferred.</p>
  </section>;
  if (!isConversionCase(data)) return null;
  const dossier = object(data.dossier);
  const timeline = [
    { date: path(dossier, 'presenting_history', 'symptom_onset'), event: 'Symptom onset: fatigue, weight loss and right-upper-quadrant pressure' },
    ...rows(dossier.diagnostic_timeline),
  ];
  return <section data-testid="case-timeline" className={`${panel} my-5`}>
    <SectionHeading eyebrow="MAY–SEPTEMBER 2026 / SOURCE DATES" title="From diagnosis to the conversion question" />
    <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{timeline.map((item, index) => <li key={index} className="min-w-0 border-l-2 border-cp-accent bg-cp-bg-elevated p-3">
      <time dateTime={shown(item.date)} className="font-mono text-xs text-cp-accent">{shown(item.date)}</time><p className="mt-2 text-xs leading-6">{shown(item.event)}</p>
    </li>)}</ol>
    <BiomarkerTrends dossier={dossier} />
  </section>;
}
function BiomarkerTrends({ dossier }: { dossier: Data }) {
  const markers = object(dossier.tumor_markers);
  const response = object(path(dossier, 'response_assessment', 'biomarkers'));
  const markerRows: Data[] = [...Object.entries(markers).map(([key, value]) => ({ label: recordLabel(key), ...object(value) })), { label: 'Response assessment', ...response }];
  return <div data-testid="biomarker-trends" className="mt-5 border-t border-cp-border pt-5">
    <h3>Biochemical and molecular response</h3>
    <div className="mt-3 grid gap-3 sm:grid-cols-2"><div className="rounded-xl bg-cp-accent-soft p-4"><p className="text-xs text-cp-text-muted">CEA · µg/L</p><p className="mt-2 text-2xl">{shown(path(markers, 'baseline', 'CEA_ug_L'))} → {shown(path(markers, 'after_cycle_2', 'CEA_ug_L'))} → {shown(path(markers, 'after_cycle_4', 'CEA_ug_L'))}</p></div>
      <div className="rounded-xl bg-cp-bg-elevated p-4"><p className="text-xs text-cp-text-muted">BRAF V600E plasma VAF · %</p><p className="mt-2 text-2xl">{shown(path(dossier, 'baseline_ctDNA', 'findings', 'BRAF_V600E_VAF_percent'))} → {shown(path(response, 'ctDNA', 'BRAF_V600E_VAF_percent'))}</p><p className="mt-2 text-xs">Persistent detectable ctDNA; not an independent surgery veto.</p></div></div>
    <div className="mt-4 max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label="Dated biomarker results"><table><caption className="sr-only">CEA and CA19-9 with the dates in each source section</caption><thead><tr><th scope="col">Source section</th><th scope="col">Date</th><th scope="col">CEA (µg/L)</th><th scope="col">CA19-9 (kU/L)</th></tr></thead><tbody>{markerRows.map((item, index) => <tr key={index}><th scope="row">{shown(item.label)}</th><td>{shown(item.date)}</td><td>{shown(item.CEA_ug_L)}</td><td>{shown(item.CA19_9_kU_L)}</td></tr>)}</tbody></table></div>
    <p className="mt-3 text-xs leading-6 text-cp-text-muted">The marker table dates the post-cycle-4 values {shown(path(markers, 'after_cycle_4', 'date'))}; response biomarkers are dated {shown(response.date)}. Both source dates are retained, not reconciled. ctDNA baseline: {shown(path(dossier, 'baseline_ctDNA', 'date'))}; response: {shown(response.date)}.</p>
  </div>;
}
export function ManagementOptions({ data }: { data: Data }) {
  const options = Array.isArray(data.management_alternatives) ? data.management_alternatives : [];
  const original = isConversionCase(data);
  return <section data-testid="management-options" className="my-5 space-y-4">
    <SectionHeading eyebrow={`${original ? 'THREE ALTERNATIVES' : 'SOURCE MANAGEMENT ALTERNATIVES'} / HUMAN DECISION REQUIRED`} title={original ? 'Local clearance, more biological testing, or disease control?' : 'Management alternatives for discussion'} />
    <p className="text-sm leading-7 text-cp-text-muted">{original ? 'These competing source proposals are not selected treatments. Technical clearance is not proof of cure. The MDT and patient must judge the trade-offs, evidence limits and timing.' : 'These supplied alternatives are not selected treatments or operative approval. Review their sequence, benefits, burdens, evidence limits and the patient’s preferences with the MDT.'}</p>
    <div className="grid items-start gap-4 xl:grid-cols-3">{options.map((option, index) => <RecordSection key={index} title={`Option ${index + 1} · ${shown(object(option).name ?? object(option).title ?? 'For MDT discussion')}`} value={option} testId={`management-option-${index + 1}`} />)}</div>
    {!options.length && <p role="status">The management alternatives have not been supplied in this meeting record.</p>}
  </section>;
}
export function CaseClinical({ role, meeting, inspect }: { role: Role; meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  const profile = clinicalProfile(meeting.case, role);
  const context = object(meeting.roles[role]?.context);
  const sections = Object.entries(context).filter(([key]) => key !== 'workspace' && key !== 'question');
  const sourceKeys = new Set(['source_sections', 'source_tables', 'narrative']);
  const compositions: Record<Role, string> = {
    radiology: 'grid items-start gap-4 lg:grid-cols-2 [&>article]:border-t-4 [&>article]:border-t-cp-link',
    oncology: 'grid items-start gap-4 lg:grid-cols-2 [&>article:first-child]:lg:col-span-2 [&>article]:border-t-4 [&>article]:border-t-cp-accent',
    surgery: 'grid items-start gap-4 lg:grid-cols-2 [&>article]:border-l-4 [&>article]:border-l-cp-success',
    pathology: 'grid items-start gap-4 lg:grid-cols-2 [&>article]:rounded-none [&>article]:border-y-2 [&>article]:border-cp-border-strong',
    research: 'space-y-4 [&>article]:rounded-none [&>article]:border-t-4 [&>article]:border-double',
    protocol: 'space-y-4 [&>article]:border-l-4 [&>article]:border-l-cp-warning',
    patient: 'mx-auto max-w-4xl space-y-4 [&>article]:border-cp-highlight [&>article:first-child]:bg-cp-accent-soft',
  };
  return <section data-testid={`clinical-${role}`} data-case-kind={clinicalCaseKind(meeting.case)} className="space-y-5">
    <section className={`${panel} border-t-4 border-t-[var(--cp-role)]`}>
      <SectionHeading eyebrow="SPECIALTY SOURCE RECORDS" title={profile?.title ?? 'Clinical source review'} />
      {Boolean(context.workspace) && <p className="mb-3 text-sm font-semibold">{shown(context.workspace)}</p>}
      <h3 className="text-xs text-cp-text-muted">Question for this specialty</h3>
      <p className="mt-2 text-sm leading-7">{shown(context.question ?? meeting.case.question)}</p>
      <p className="mt-4 text-xs leading-6 text-cp-text-muted">Supplied findings and consultation contributions support this role’s review; they are not independent votes or approvals. Uncertainty and missing information remain part of the record.</p>
    </section>
    <div className={compositions[role]}>{sections.filter(([key]) => !sourceKeys.has(key)).map(([key, value]) => <RecordSection key={key} title={recordLabel(key)} value={value} testId={`clinical-source-${role}-${key}`} />)}</div>
    {!sections.length && <p role="status" className={panel}>Detailed source context for this specialty has not been supplied. Review the complete case record; no specialty findings have been inferred.</p>}
    {sections.filter(([key]) => sourceKeys.has(key)).map(([key, value]) => <RecordSection key={key} title={recordLabel(key)} value={value} testId={`clinical-source-${role}-${key}`} collapsible />)}
    {(role === 'research' || role === 'protocol') && <section className={panel}><SectionHeading eyebrow="SOURCE ACCESS AND APPLICABILITY" title="Evidence for review" /><EvidenceTable evidence={meeting.evidence} inspect={inspect} /></section>}
    {(role === 'oncology' || role === 'protocol') && <ManagementOptions data={meeting.case} />}
    <details className={panel}><summary className="font-semibold">Complete source clinical dossier</summary><div className="mt-5"><CompleteCaseRecord data={meeting.case} /></div></details>
  </section>;
}
const segmentPoints: Record<string, [number, number]> = { '8': [130, 85], '4a': [248, 95], '7': [72, 99], '6': [73, 177], '5': [155, 181], '3': [310, 150], '2': [328, 77], '1': [210, 63], '4b': [234, 175] };
function LiverMap({ lesions, current, date, overlay }: { lesions: Data[]; current?: Data; date: unknown; overlay: boolean }) {
  return <figure className="min-w-0 rounded-xl border border-cp-border bg-cp-bg-elevated p-3">
    <figcaption className="text-xs font-semibold">{current ? 'Current MRI' : 'Baseline MRI'} · {shown(date)}</figcaption>
    <svg viewBox="0 0 400 255" className="mt-2 h-auto w-full" role="img" aria-label={`${current ? 'Current' : 'Baseline'} illustrative liver segment map; nine lesion locations, not clinical imaging or surgical navigation`}>
      <path d="M33 93Q70 28 190 37Q250 22 361 52Q384 73 352 135Q307 183 221 221Q79 240 37 189Q13 148 33 93Z" fill="var(--cp-surface)" stroke="var(--cp-border-strong)" strokeWidth="2" />
      <path d="M199 43L208 203M250 50L230 190M49 135L173 134M278 118L348 108M108 50L112 207" fill="none" stroke="var(--cp-border)" strokeDasharray="5 5" />
      <path d="M209 30L206 91M238 40L242 143" fill="none" stroke="var(--cp-link)" strokeWidth="4" />
      <text x="170" y="23" fontSize="11" fill="var(--cp-link)">IVC</text><text x="250" y="29" fontSize="11" fill="var(--cp-link)">MHV</text>
      {lesions.map(lesion => {
        const segment = shown(lesion.segment);
        const [x, y] = segmentPoints[segment] ?? [200, 125];
        const measurement = current ? current[`S${segment}_mm`] : lesion.size_mm;
        const diameter = Number.parseFloat(shown(measurement));
        return <g key={segment}><circle cx={x} cy={y} r={Number.isFinite(diameter) ? 5 + diameter / 4 : 7} fill="var(--cp-accent-soft)" stroke="var(--cp-accent)" strokeWidth="2" /><text x={x} y={y + 4} textAnchor="middle" fontSize="12" fill="var(--cp-text)">S{segment}</text>{overlay && <text x={x} y={y + 30} textAnchor="middle" fontSize="10" fill="var(--cp-text-muted)">{shown(measurement)} mm</text>}</g>;
      })}
      <text x="200" y="249" textAnchor="middle" fontSize="10" fill="var(--cp-text-muted)">ILLUSTRATIVE · NOT CLINICAL IMAGING · NOT TO SCALE</text>
    </svg>
  </figure>;
}
function LiverReview({ dossier }: { dossier: Data }) {
  const [view, setView] = useState<'compare' | 'current'>('compare');
  const [overlay, setOverlay] = useState(true);
  const baseline = object(path(dossier, 'imaging', 'baseline_liver_MRI'));
  const response = object(path(dossier, 'response_assessment', 'liver_MRI'));
  const lesions = rows(baseline.metastatic_lesions);
  return <>
    <section className={`${panel} border-t-4 border-t-cp-link`}><SectionHeading eyebrow="RADIOLOGY / NINE BASELINE SITES" title="Radiology findings and response assessment" aside={<ScanLine />} />
      <div className="mb-4 flex flex-wrap justify-between gap-3"><div className="flex gap-2"><button className="rounded-lg border border-cp-border px-3 py-2 text-xs aria-pressed:bg-cp-accent-soft" aria-pressed={view === 'compare'} onClick={() => setView('compare')}><Layers size={14} className="mr-1 inline" />Compare</button><button className="rounded-lg border border-cp-border px-3 py-2 text-xs aria-pressed:bg-cp-accent-soft" aria-pressed={view === 'current'} onClick={() => setView('current')}>Current</button></div><button className="flex items-center gap-2 text-xs text-cp-accent" aria-pressed={overlay} onClick={() => setOverlay(value => !value)}><Eye size={15} />Overlay {overlay ? 'on' : 'off'}</button></div>
      <div data-testid="liver-segment-map" className={`grid gap-3 ${view === 'compare' ? 'lg:grid-cols-2' : ''}`}>{view === 'compare' && <LiverMap lesions={lesions} date={baseline.date} overlay={overlay} />}<LiverMap lesions={lesions} current={object(response.measurements)} date={response.date} overlay={overlay} /></div>
      <p className="mt-3 text-xs leading-6 text-cp-text-muted">Diagram only; not an acquired scan. Segment placement and circle sizes are illustrative. Clinical dimensions below are transcribed from the source MRI reports.</p>
      <div data-testid="liver-lesion-table" className="mt-5 max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label="All nine liver lesion measurements"><table><caption className="mb-3 text-left text-sm font-semibold">All original liver sites · baseline and current MRI</caption><thead><tr><th scope="col">Segment</th><th scope="col">Baseline · {shown(baseline.date)} (mm)</th><th scope="col">Current · {shown(response.date)} (mm)</th></tr></thead><tbody>{lesions.map(lesion => <tr key={shown(lesion.segment)}><th scope="row">S{shown(lesion.segment)}</th><td>{shown(lesion.size_mm)}</td><td>{shown(path(response, 'measurements', `S${shown(lesion.segment)}_mm`))}</td></tr>)}</tbody></table></div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2"><RecordSection title="Vessel interfaces: baseline" value={baseline.surgically_critical_relationships} /><RecordSection title="Vessel interfaces: current" value={response.vascular_relationship_changes} /></div>
      <p className="mt-4 border-l-4 border-cp-warning pl-4 text-sm leading-7">The stable 5 mm right-upper-lobe nodule remains indeterminate. PET cannot reliably classify a lesion this small; absent uptake is not evidence of benignity. Review serial thin-section chest CT.</p>
      <RecordValue value={{ baseline_volumetry: baseline.liver_volume, current_volumetry: response.volumetry, radiology_conclusion: response.radiology_conclusion }} />
    </section>
    <RecordSection title="Full imaging reports and acquisition details" value={{ imaging: dossier.imaging, response_assessment: dossier.response_assessment }} collapsible />
  </>;
}
function Contributions({ data, roles }: { data: Data; roles: RegExp }) {
  const contributions = Array.isArray(data.specialty_contributions) ? data.specialty_contributions : [];
  return <div className="space-y-4">{contributions.filter(item => roles.test(shown(path(item, 'specialty')))).map((item, index) => <RecordSection title={shown(path(item, 'specialty'))} value={item} key={index} />)}</div>;
}
export function ConversionClinical({ role, meeting, inspect }: { role: Role; meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  const data = meeting.case;
  const dossier = object(data.dossier);
  return <section data-testid={`clinical-${role}`} className="space-y-5">
    {role === 'radiology' && <LiverReview dossier={dossier} />}
    {role === 'oncology' && <>
      <div className={`${panel} border-cp-accent bg-cp-accent-soft`}><SectionHeading eyebrow="SYSTEMIC THERAPY / FOUR-CYCLE REVIEW" title="Systemic therapy response review" /><p className="text-sm leading-7">Balance further disease control against neuropathy, liver injury and loss of identifiable targets. Response does not establish the optimal time to interrupt treatment for surgery.</p><BiomarkerTrends dossier={dossier} /></div>
      <RecordSection title="Actual regimen, cycles and doses" value={path(dossier, 'prior_cancer_treatment', 'systemic_regimen')} testId="oncology-regimen" />
      <div className="grid gap-4 lg:grid-cols-2"><RecordSection title="Toxicity and tolerability" value={path(dossier, 'prior_cancer_treatment', 'maximum_toxicities')} /><RecordSection title="Supportive treatment and post-cycle-4 labs" value={{ supportive_treatment: path(dossier, 'prior_cancer_treatment', 'supportive_treatment'), post_cycle_4_labs: dossier.post_cycle_4_labs }} /></div>
      <Contributions data={data} roles={/medical oncology/i} /><ManagementOptions data={data} />
    </>}
    {role === 'surgery' && <>
      <div className={`${panel} border-t-4 border-t-cp-success`}><SectionHeading eyebrow="HPB · COLORECTAL · INTERVENTIONAL RADIOLOGY · RADIATION ONCOLOGY" title="Surgical resectability assessment" /><p className="text-sm leading-7">Seven runtime roles, with four procedural disciplines represented in this surgical review. These contributions are source discussion positions, not independent approvals.</p><div className="mt-5 grid gap-4 sm:grid-cols-2"><RecordSection title="Baseline major-resection FLR" value={path(dossier, 'imaging', 'baseline_liver_MRI', 'liver_volume')} /><RecordSection title="Predicted parenchymal-sparing remnant" value={path(dossier, 'response_assessment', 'liver_MRI', 'volumetry')} /></div></div>
      <RecordSection title="Liver clearance, colectomy sequence and contingencies" value={dossier.current_resectability_review} testId="surgery-sequence" />
      <Contributions data={data} roles={/hepatobiliary|colorectal surgery|interventional radiology|radiation oncology/i} />
      <p className={`${panel} text-sm leading-7`}>Confirm every baseline site, intraoperative ultrasound, vessel-safe margins and patient fitness. The source assigns no site-specific treatment to S5, S2 or S4b; no clearance strategy is invented for those sites. The segment 1/IVC heat-sink and access risks need expert review; SBRT/MR-guided treatment is a contingency for an unsafe residual focus, not a default substitute for clearing nine deposits.</p>
    </>}
    {role === 'pathology' && <>
      <div className={`${panel} space-y-5 border-y-2 border-cp-border-strong`}><SectionHeading eyebrow="COLORECTAL TISSUE / MOLECULAR DOSSIER" title="Molecular pathology findings" />{Object.entries(object(dossier.pathology)).map(([specimen, value]) => <article key={specimen} data-testid={`pathology-specimen-${specimen}`}><h3 className="mb-4 font-mono text-sm">{recordLabel(specimen)}</h3><div className="[&>dl]:grid [&>dl]:gap-5 [&>dl]:space-y-0 sm:[&>dl]:grid-cols-2"><RecordValue value={value} /></div></article>)}</div>
      <RecordSection title="Full molecular profile and variant-level findings" value={dossier.molecular_profile} testId="pathology-molecular" />
      <div className="grid gap-4 lg:grid-cols-2"><RecordSection title="Pharmacogenomics" value={dossier.pharmacogenomics} /><RecordSection title="Plasma assays and molecular response" value={{ baseline_ctDNA: dossier.baseline_ctDNA, response_ctDNA: path(dossier, 'response_assessment', 'biomarkers') }} /></div>
      <Contributions data={data} roles={/pathology/i} />
    </>}
    {role === 'research' && <>
      <div className={`${panel} border-cp-link`}><SectionHeading eyebrow="EVIDENCE COMPARISON / EUROPE FIRST" title="Evidence comparison across trials" /><h3>Appraisal lens</h3><p className="mt-3 text-sm leading-7">Source-supplied summaries below are not verified full-text extraction. Inspect each evidence item for its actual provenance and access; unresolved source references do not establish efficacy, local adoption or perioperative eligibility.</p>
        <div data-testid="research-scope-limits" className="mt-5 grid items-start gap-4 lg:grid-cols-3"><RecordSection title="BREAKWATER — systemic regimen" value="First-line BRAF V600E metastatic CRC systemic efficacy does not establish a conversion-hepatectomy pathway or optimal perioperative duration." /><RecordSection title="CAIRO5 — conversion framework" value="Initially unresectable colorectal liver metastases and repeated expert review are relevant. Different induction regimens and populations limit transfer; greater response or more local treatment is not proof of a survival advantage." /><RecordSection title="PROVENC3 — setting mismatch" value="Postoperative ctDNA in resected stage III colon cancer is not the same setting as conversion-stage IV disease. Do not transplant hazard ratios or use persistent ctDNA as a binary prohibition on metastasectomy." /></div>
      </div><div className={panel}><EvidenceTable evidence={meeting.evidence} inspect={inspect} /></div>
      <RecordSection title="Research questions and supplied context" value={{ unresolved_mdt_questions: dossier.unresolved_mdt_questions, research_context: meeting.roles.research?.context }} collapsible />
    </>}
    {role === 'protocol' && <>
      <section className={`${panel} border-l-4 border-l-cp-warning`}><SectionHeading eyebrow="CONDITIONAL CARE PATHWAY" title="Conditions before application" aside={<ShieldCheck />} /><p className="text-sm leading-7">No automatic clinical decision. The current alternatives require human review of complete liver clearance, extrahepatic uncertainty, biological control, toxicity, patient goals and perioperative timing.</p>
        <div data-testid="protocol-step-ACCESS" className="mt-4"><Badge tone="warning">Evidence and protocol access must be verified</Badge><p className="mt-3 text-sm leading-7">Source summaries and unresolved citation handles are not verified guidelines. Trial efficacy is not local hospital approval, Dutch reimbursement or a validated perioperative schedule. Missing full protocol details remain missing.</p></div>
        <div data-testid="protocol-step-IF" className="mt-5"><RecordValue value={{ source_questions: dossier.unresolved_mdt_questions, protocol_context: meeting.roles.protocol?.context, current_plan_conditions: meeting.plan?.conditions ?? [], specialist_uncertainties: meeting.roles.protocol?.position?.uncertainties ?? [] }} /></div>
      </section><ManagementOptions data={data} /><div className={panel}><EvidenceTable evidence={meeting.evidence} inspect={inspect} /></div>
    </>}
    {role === 'patient' && <>
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]"><section className={`${panel} border-cp-accent bg-cp-accent-soft`}><Heart className="mb-5 text-cp-accent" /><SectionHeading eyebrow="STATED GOALS / SHARED DECISION" title="Patient goals and shared decision-making" /><RecordValue value={path(dossier, 'patient', 'goals')} /><p className="mt-5 text-sm leading-7">Potentially curative is not predictably curative. Discuss operative burden, recurrence uncertainty and the risk of losing a local-treatment opportunity without assuming what the patient will choose.</p></section><RecordSection title="Patient context" value={{ living_situation: path(dossier, 'patient', 'living_situation'), occupation: path(dossier, 'patient', 'occupation'), functional_status: path(dossier, 'patient', 'ECOG_performance_status'), frailty: path(dossier, 'patient', 'frailty_screen') }} /></div>
      <RecordSection title="Treatment burden" value={{ toxicities: path(dossier, 'prior_cancer_treatment', 'maximum_toxicities'), symptom_support: path(dossier, 'prior_cancer_treatment', 'supportive_treatment') }} testId="patient-burden-discussion" />
      <Contributions data={data} roles={/palliative|supportive/i} />
      <p className={`${panel} flex items-start gap-3 text-sm leading-7`}><ArrowRight className="shrink-0 text-cp-accent" />Palliative/supportive care means symptom and decision support, not abandonment of curative intent. Human concurrence does not replace informed consent or a patient conversation.</p>
    </>}
    <details className={panel}><summary className="font-semibold">Complete source clinical dossier</summary><div className="mt-5"><CompleteCaseRecord data={data} /></div></details>
  </section>;
}
