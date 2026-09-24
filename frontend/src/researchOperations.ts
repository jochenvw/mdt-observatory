import type { Data, Evidence, Meeting, SourceTier } from './types';

export interface SearchSource { key: string; label: string; tier: SourceTier; description: string }
/** Public sources the research specialty may search, in the order Dutch → EU → international → US → preprints. */
export const SEARCH_SOURCES: SearchSource[] = [
  { key: 'richtlijnendatabase', label: 'Richtlijnendatabase', tier: 'NL', description: 'Dutch national guidelines' },
  { key: 'ctis', label: 'EU CTIS', tier: 'EU', description: 'EU clinical trials register' },
  { key: 'europepmc', label: 'Europe PMC', tier: 'INTL', description: 'European literature index' },
  { key: 'pubmed', label: 'PubMed', tier: 'INTL', description: 'NCBI bibliographic database' },
  { key: 'clinicaltrials_gov', label: 'ClinicalTrials.gov', tier: 'US', description: 'US trial register' },
  { key: 'preprints', label: 'Preprints', tier: 'PREPRINT', description: 'Not peer reviewed' },
];
export const TIER_ORDER: SourceTier[] = ['NL', 'EU', 'INTL', 'US', 'PREPRINT'];
export const TIER_HEADING: Record<SourceTier, string> = {
  NL: 'Dutch', EU: 'European', INTL: 'International', US: 'US context · not EU standard of care', PREPRINT: 'Preprints · not peer reviewed',
};

export type SourceState = 'not_searched' | 'searching' | 'completed' | 'unavailable';
export interface SourceCheck { source: string; label: string; status: string; total: number; returned: number; message: string }
export interface SearchRun {
  id: number | string;
  tool: string;
  query: string;
  sources: string[];
  status: 'running' | 'completed' | 'unavailable' | 'refused';
  summary: string;
  found: number;
  alreadyCurated: number;
  checks: SourceCheck[];
}
export interface ResearchOperations {
  retrieval: 'LIVE' | 'RECORDED' | null;
  capturedAt: string | null;
  runs: SearchRun[];
  sources: Array<SearchSource & { state: SourceState; searches: number; returned: number; total: number; message: string }>;
  found: Array<{ tier: SourceTier; items: Evidence[] }>;
  cited: Set<string>;
}

const isSearch = (payload: Data) => payload.retrieval === 'LIVE' || payload.retrieval === 'RECORDED';
const str = (value: unknown) => (typeof value === 'string' ? value : '');
const num = (value: unknown) => (typeof value === 'number' ? value : 0);

/** Everything the research specialty searched and found, derived from the recorded meeting only. */
export function researchOperations(meeting: Meeting): ResearchOperations {
  const runs: SearchRun[] = [];
  let retrieval: ResearchOperations['retrieval'] = null;
  for (const event of meeting.events) {
    if (event.role !== 'research' || !isSearch(event.payload)) continue;
    const payload = event.payload;
    if (event.type === 'ToolStarted') {
      retrieval = payload.retrieval as 'LIVE' | 'RECORDED';
      runs.push({
        id: event.id, tool: str(payload.tool), query: str(payload.query),
        sources: Array.isArray(payload.sources) ? payload.sources.map(String) : [],
        status: 'running', summary: str(payload.summary), found: 0, alreadyCurated: 0, checks: [],
      });
    } else if (event.type === 'ToolCompleted') {
      const run = [...runs].reverse().find(item => item.status === 'running' && item.tool === payload.tool);
      if (!run) continue;
      const status = str(payload.status);
      run.status = status === 'completed' || status === 'unavailable' || status === 'refused' ? status : 'unavailable';
      run.summary = str(payload.summary) || run.summary;
      run.found = num(payload.result_count);
      run.alreadyCurated = Array.isArray(payload.already_curated) ? payload.already_curated.length : 0;
      run.checks = Array.isArray(payload.checks) ? (payload.checks as Data[]).map(check => ({
        source: str(check.source), label: str(check.label), status: str(check.status),
        total: num(check.total), returned: num(check.returned), message: str(check.message),
      })) : [];
    }
  }
  const searched = meeting.evidence.filter(item => item.retrieval === 'LIVE' || item.retrieval === 'RECORDED');
  retrieval ??= searched[0]?.retrieval === 'LIVE' || searched[0]?.retrieval === 'RECORDED' ? searched[0].retrieval : null;
  const capturedAt = retrieval === 'RECORDED' ? searched.find(item => item.retrieved_at)?.retrieved_at?.slice(0, 10) ?? null : null;
  const sources = SEARCH_SOURCES.map(source => {
    const checks = runs.filter(run => run.tool !== 'fetch_abstract').flatMap(run => run.checks).filter(check => check.source === source.key);
    const running = runs.some(run => run.status === 'running' && run.tool !== 'fetch_abstract' && run.sources.includes(source.key));
    const completed = checks.filter(check => check.status === 'completed');
    const state: SourceState = running ? 'searching' : completed.length ? 'completed' : checks.some(check => check.status === 'unavailable') ? 'unavailable' : 'not_searched';
    return {
      ...source, state, searches: checks.length,
      returned: completed.reduce((sum, check) => sum + check.returned, 0),
      total: completed.reduce((sum, check) => sum + check.total, 0),
      message: checks.find(check => check.status === 'unavailable')?.message ?? '',
    };
  });
  const found = TIER_ORDER.map(tier => ({ tier, items: searched.filter(item => (item.source_tier ?? 'INTL') === tier) })).filter(group => group.items.length);
  const position = meeting.roles.research?.position;
  const cited = new Set([...(position?.provenance ?? []), ...(position?.claims.flatMap(claim => claim.evidence_ids) ?? [])]);
  return { retrieval, capturedAt, runs, sources, found, cited };
}

/** The public record page for a searched item, by its registry or bibliographic identifier. */
export function identifierLabel(item: Evidence): string {
  const ids = item.identifiers ?? {};
  if (ids.nct) return ids.nct;
  if (ids.eu_ct_number) return ids.eu_ct_number;
  if (ids.pmid) return `PMID ${ids.pmid}`;
  if (ids.preprint) return ids.preprint;
  if (ids.doi) return `DOI ${ids.doi}`;
  return item.retrieved_via ?? 'Public record';
}
