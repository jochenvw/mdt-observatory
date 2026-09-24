import { ArrowUpRight, CircleAlert, Globe2, LoaderCircle, Search } from 'lucide-react';
import { label, safeUrl } from './helpers';
import type { Meeting } from './types';
import { Badge, SectionHeading } from './ui';
import type { EvidenceSelection } from './ui';
import { identifierLabel, researchOperations, TIER_HEADING } from './researchOperations';

const STATE_TEXT = { not_searched: 'Not searched', searching: 'Searching…', completed: 'Searched', unavailable: 'Unavailable' } as const;
const STATE_TONE = { not_searched: '', searching: 'accent', completed: 'success', unavailable: 'danger' } as const;

/** Public searches the research specialty ran on top of the curated evidence set, and what they found. */
export function ResearchOperationsPanel({ meeting, inspect }: { meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  const ops = researchOperations(meeting);
  const recorded = ops.retrieval === 'RECORDED';
  const total = ops.found.reduce((sum, group) => sum + group.items.length, 0);
  return <section data-testid="research-operations" aria-label="Public literature and trial searches" className="card my-4 p-4">
    <SectionHeading
      eyebrow="PUBLIC SEARCHES · IN ADDITION TO THE CURATED EVIDENCE SET"
      title="Research operations"
      aside={ops.retrieval ? <Badge tone={recorded ? 'warning' : 'accent'}>{recorded ? `Recorded replay${ops.capturedAt ? ` · captured ${ops.capturedAt}` : ''}` : 'Live public search'}</Badge> : <Search size={20} />}
    />
    {recorded && <p data-testid="research-recorded-note" className="-mt-2 mb-3 text-xs leading-6 text-cp-text-muted">Rehearsal mode replays real search responses recorded earlier. Nothing is searched live, and results may be out of date.</p>}
    <ol data-testid="research-sources" aria-label="Sources" className="mb-4 flex list-none flex-wrap gap-2">{ops.sources.map(source => <li key={source.key} data-source={source.key} data-state={source.state} title={source.message || source.description} className={`flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 text-xs ${source.state === 'unavailable' ? 'border-cp-danger' : source.state === 'completed' ? 'border-cp-success' : 'border-cp-border'}`}>
      <span className="font-mono text-[9px] tracking-wider text-cp-text-soft">{source.tier}</span>
      <span className="font-semibold">{source.label}</span>
      <Badge tone={STATE_TONE[source.state]} pulse={source.state === 'searching'}>{source.state === 'completed' ? source.searches === 1 ? `${source.returned} of ${source.total.toLocaleString()} shown` : `${source.searches} searches · ${source.returned} shown` : STATE_TEXT[source.state]}</Badge>
    </li>)}</ol>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="min-w-0">
        <h3 className="mb-2 text-sm">Searches run <span className="font-normal text-cp-text-muted">({ops.runs.length})</span></h3>
        {ops.runs.length ? <ol data-testid="research-searches" className="list-none space-y-2">{ops.runs.map(run => <li key={run.id} data-status={run.status} className={`rounded-lg border-l-4 bg-cp-bg-elevated px-3 py-2 text-xs leading-6 ${run.status === 'running' ? 'border-cp-accent' : run.status === 'completed' && !run.checks.some(check => check.status === 'unavailable') ? 'border-cp-success' : 'border-cp-danger'}`}>
          <div className="flex items-start gap-2">{run.status === 'running' ? <LoaderCircle size={14} className="mt-1 shrink-0 motion-safe:animate-spin" /> : run.status === 'completed' ? <Globe2 size={14} className="mt-1 shrink-0 text-cp-success" /> : <CircleAlert size={14} className="mt-1 shrink-0 text-cp-danger" />}
            <div className="min-w-0"><p className="font-semibold">{run.tool === 'fetch_abstract' ? 'Opened an abstract' : run.checks.map(check => check.label).join(' + ') || run.summary.replace(/^Replaying a recorded search: /, '').replace(/ for “.*$/, '')}</p>
              {run.query && <p className="break-words">“{run.query}”</p>}
              <p className="text-cp-text-muted">{run.status === 'running' ? 'Searching…' : run.tool === 'fetch_abstract' ? run.summary : `${run.summary}${run.alreadyCurated ? ` · ${run.alreadyCurated} already in the curated set` : ''}`}</p>
              {run.checks.filter(check => check.status === 'unavailable').map(check => <p key={check.source} role="alert" className="text-cp-danger">{check.message || `${check.label} was unavailable.`}</p>)}
            </div></div>
        </li>)}</ol> : <p className="text-xs leading-6 text-cp-text-muted">No public search has been run in this review. The specialist is working from the curated evidence set.</p>}
      </div>
      <div className="min-w-0">
        <h3 className="mb-2 text-sm">Papers and trials found <span className="font-normal text-cp-text-muted">({total})</span></h3>
        {total ? <div data-testid="research-found" className="space-y-3">{ops.found.map(group => <div key={group.tier}>
          <p className="eyebrow mb-1">{TIER_HEADING[group.tier]}</p>
          <ul className="list-none space-y-2">{group.items.map(item => {
            const url = safeUrl(item.url);
            return <li key={item.id} data-evidence-id={item.id} className="rounded-lg border border-cp-border p-3 text-xs leading-6">
              <button className="min-h-0 w-full border-0 bg-transparent p-0 text-left font-semibold text-cp-text hover:text-cp-accent hover:underline" onClick={() => inspect({ ids: [item.id] })} aria-label={`Inspect ${item.title}`}>{item.title}</button>
              <p className="text-cp-text-muted">{item.authority} · {item.date}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <Badge>{label(item.kind)}</Badge>
                <Badge>{item.access === 'METADATA_ONLY' ? 'Record only' : label(item.access)}</Badge>
                <Badge tone="warning">Not appraised for this patient</Badge>
                {ops.cited.has(item.id) && <Badge tone="accent">Cited in position</Badge>}
                {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-cp-accent">{identifierLabel(item)}<ArrowUpRight size={12} /></a> : <span className="text-[11px] text-cp-text-muted">{identifierLabel(item)}</span>}
              </div>
            </li>;
          })}</ul>
        </div>)}</div> : <p className="text-xs leading-6 text-cp-text-muted">{ops.runs.some(run => run.status === 'running') ? 'Results will appear as each search returns.' : 'No new records were found beyond the curated evidence set.'}</p>}
      </div>
    </div>
    <p className="mt-4 border-t border-cp-border pt-3 text-[11px] leading-5 text-cp-text-muted">Searched records are leads, not appraised evidence. Only clinical concepts are sent to public sources — never names, dates or case identifiers. Patient applicability stays a human judgment.</p>
  </section>;
}
