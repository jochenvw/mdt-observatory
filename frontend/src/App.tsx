import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, Check, CheckCheck, ChevronRight, CircleDot, Download, Eraser, ExternalLink, Flag, GitBranch, LayoutDashboard, LayoutGrid, LoaderCircle, LockKeyhole, Maximize2, Menu, Moon, Network, Play, RefreshCw, ShieldCheck, Sparkles, Sun, Users, X } from 'lucide-react';
import { activitySummary, concurrenceActor, first, humanConcurred, label, roleAttention, time } from './helpers';
import { Specialist } from './Specialist';
import { Badge, BulletList, DataFields, Empty, EvidenceDrawer, EvidenceTable, eventSummary, Modal, ROLE_META, roleMetaFor, SectionHeading, Status } from './ui';
import type { EvidenceSelection } from './ui';
import { PHASES, ROLES } from './types';
import type { Meeting, Mode, Role, Workspace } from './types';
import { useMeeting } from './useMeeting';
import { clinicalActivity, PHASE_MEANING, presentMeeting, statusLabel } from './presentation';
import { useTheme } from './theme';
import { CaseTimeline, CompleteCaseRecord, isConversionCase, ManagementOptions } from './CaseDossier';
import { ROLE_LAYOUTS } from './roleLayouts';
import { CaseSelection } from './CaseSelection';
import { clinicalCaseKind } from './caseProfiles';

type Drafts = Partial<Record<Role, string>>;
const MODE_LABEL: Record<Mode, string> = { rehearsal: 'Scripted demonstration', azure: 'Live AI review' };

export default function App() {
  const api = useMeeting();
  const { config, pending } = api;
  const meeting = useMemo(() => presentMeeting(api.meeting), [api.meeting]);
  const [workspace, setWorkspace] = useState<Workspace>('cases');
  const [selectedCase, setSelectedCase] = useState('');
  const [showPlan, setShowPlan] = useState(false);
  const [mode, setMode] = useState<Mode>('rehearsal');
  const modeInitialized = useRef(false);
  const [evidence, setEvidence] = useState<EvidenceSelection | null>(null);
  const [showCase, setShowCase] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [comments, setComments] = useState<Drafts>({});
  const [reviewRole, setReviewRole] = useState<Role>('radiology');
  const [token, setToken] = useState('');
  const { theme, saved: themeSaved, toggle: toggleTheme, useSystem: useSystemTheme } = useTheme();

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [workspace]);
  useEffect(() => {
    setSelectedCase(current => api.cases.some(item => item.id === current) ? current : api.cases[0]?.id ?? '');
  }, [api.cases]);

  useEffect(() => {
    if (modeInitialized.current || api.loading || !config?.modes.length) return;
    modeInitialized.current = true;
    const initialMode = meeting?.mode ?? 'rehearsal';
    setMode(config.modes.includes(initialMode) ? initialMode : config.modes[0]);
  }, [api.loading, config, meeting?.mode]);
  const meetingId = meeting?.id;
  // The orchestrator opening a case, or returning the room to standby, resets every
  // participant screen: unsent drafts, review comments and open overlays from the
  // previous case must not carry into the next one. The chosen role workspace stays.
  useEffect(() => {
    setDrafts({});
    setComments({});
    setShowPlan(false);
    setShowCase(false);
    setEvidence(null);
  }, [meetingId]);
  const selectWorkspace = (value: Workspace) => {
    setWorkspace(value);
    setMobileNav(false);
    if (ROLES.includes(value as Role)) setReviewRole(value as Role);
  };
  const start = async (executionMode = mode) => {
    if (selectedCase && await api.start(executionMode, selectedCase)) { setWorkspace('central'); setReviewRole('radiology'); }
  };
  const isRole = ROLES.includes(workspace as Role);
  const roleLayout = isRole ? ROLE_LAYOUTS[workspace as Role] : null;
  const openQuestions = meeting?.frictions.filter(item => !item.resolved).length ?? 0;
  const activeRole = isRole ? workspace as Role : reviewRole;
  const steer = async () => {
    const guidance = (drafts[activeRole] ?? '').trim();
    if (guidance && await api.mutate('steer', { role: activeRole, guidance })) setDrafts(current => ({ ...current, [activeRole]: current[activeRole]?.trim() === guidance ? '' : current[activeRole] }));
  };
  const readyForAction = Boolean(meeting && !meeting.busy && !pending && meeting.phase !== 'DECISION_CAPTURED');

  return <div className={`app min-h-dvh bg-cp-bg text-cp-text ${workspace === 'wall' ? 'wall-mode' : ''}`}>
    <a className="skip-link sr-only fixed left-3 top-3 z-50 focus:not-sr-only focus:rounded-lg focus:border-2 focus:border-cp-accent focus:bg-cp-surface focus:p-3" href="#main">Skip to main content</a>
    <div className="demo-banner flex min-h-7 items-center justify-center gap-2 bg-cp-text px-3 py-1 text-center text-[9px] tracking-widest text-cp-bg"><ShieldCheck size={12} /><span>DEMONSTRATION SYSTEM · NOT FOR CLINICAL USE</span></div>
    <header className="app-header flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-cp-border bg-cp-bg-elevated px-3 py-3 sm:px-6">
      <button className="icon-button inline-flex size-9 shrink-0 items-center justify-center rounded-lg border-0! bg-[inherit]! text-cp-text-muted hover:bg-cp-surface-soft! hover:text-cp-accent mobile-menu lg:hidden" aria-label="Toggle workspace navigation" aria-expanded={mobileNav} onClick={() => setMobileNav(value => !value)}><Menu size={21} /></button>
      <button className="brand flex items-center gap-3 border-0! bg-[inherit]! p-0 text-left [&_strong]:block [&_strong]:text-sm [&_strong]:tracking-widest [&_strong_span]:text-cp-accent [&_small]:mt-1 [&_small]:block [&_small]:text-[7px] [&_small]:tracking-widest [&_small]:text-cp-text-soft max-sm:[&_strong]:text-[11px] max-sm:[&_strong]:tracking-wide max-sm:gap-2 max-sm:[&_.brand-mark]:size-8" aria-label="MDT Observatory home" onClick={() => selectWorkspace('central')}><span className="brand-mark flex size-10 shrink-0 items-center justify-center rounded-xl border border-cp-highlight bg-cp-accent-soft text-cp-accent"><Network size={25} /></span><span><strong>MDT <span>/</span> OBSERVATORY</strong><small>MULTIDISCIPLINARY TEAM REVIEW SYSTEM</small></span></button>
      <div className="header-actions ml-auto flex items-center gap-3">
        <span className={`connection hidden items-center gap-2 text-xs text-cp-text-muted md:inline-flex ${api.connection}`} role="status"><span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success" />{api.connection === 'online' ? 'Live connection' : label(api.connection)}</span>
        <button className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline guide-button hidden xl:inline-flex max-xl:hidden!" onClick={() => setShowGuide(true)}>Presenter guide <ArrowUpRight size={14} /></button>
        <div className="flex items-center gap-2">
          <button data-testid="theme-toggle" className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold secondary bg-cp-surface text-cp-text hover:bg-cp-surface-soft max-sm:size-9 max-sm:p-0" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} aria-pressed={theme === 'dark'} onClick={toggleTheme}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}<span className="hidden sm:inline">{theme === 'dark' ? 'Dark theme' : 'Light theme'}</span></button>
          <button data-testid="theme-system" className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline hidden sm:inline-flex max-sm:hidden!" onClick={useSystemTheme}>Use system</button>
        </div>
      </div>
    </header>
    <div className="shell grid min-h-[calc(100dvh-108px)] lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className={`sidebar hidden flex-col gap-5 border-r border-cp-border bg-cp-bg-elevated p-4 lg:sticky lg:top-0 lg:flex lg:max-h-dvh lg:self-start lg:overflow-y-auto ${mobileNav ? 'is-open flex! absolute left-0 top-27 z-30 w-72 max-w-[92vw] border-b border-cp-border shadow-[var(--cp-shadow)] lg:sticky lg:w-auto lg:shadow-none' : ''}`} aria-label="Demo control">
        <div className="sidebar-heading flex items-center justify-between gap-2 [&_.badge]:text-[8px]"><p className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">DEMO CONTROL</p><Badge>LIVE MDT</Badge></div>
        <nav aria-label="Meeting and role workspaces">
          <NavItem testId="view-cases" selected={workspace === 'cases'} onClick={() => selectWorkspace('cases')} icon={<LayoutGrid size={18} />} title="Case selection" detail="Choose or resume a case" />
          <NavItem testId="view-central" selected={workspace === 'central'} onClick={() => selectWorkspace('central')} icon={<LayoutDashboard size={18} />} title="Central MDT" detail={meeting ? statusLabel(meeting.phase) : 'Shared meeting state'} />
          <NavItem testId="view-chair" selected={workspace === 'chair'} onClick={() => selectWorkspace('chair')} icon={<GitBranch size={18} />} title="Chair / orchestrator" detail="Direct the meeting" />
          <NavItem testId="view-wall" selected={workspace === 'wall'} onClick={() => selectWorkspace('wall')} icon={<LayoutGrid size={18} />} title="Workspace wall" detail="All seven, at a glance" />
          <div className="nav-divider mb-2 mt-6 flex items-center justify-between gap-2 text-[10px] text-cp-text-soft"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">SPECIALIST WORKSPACES</span><span>07</span></div>
          {ROLES.map(role => { const meta = roleMetaFor(role, meeting); const Icon = meta.icon; const attention = meeting ? roleAttention(meeting, role) : null; return <NavItem key={role} testId={`view-${role}`} specialty={role} selected={workspace === role} onClick={() => selectWorkspace(role)} icon={<Icon size={18} />} title={meta.label} detail={attention?.title ?? meta.description} active={attention?.running} />; })}
        </nav>
        <div className="sidebar-bottom mt-auto pt-12 [&_strong]:text-xs [&_p]:my-4 [&_p]:text-[11px] [&_p]:leading-7 [&_p]:text-cp-text-muted [&_svg]:text-cp-accent"><div className="row flex items-center gap-2"><CircleDot size={17} /><strong>Human review required</strong></div><p>Specialty reviews are advisory. Every assessment, source and condition remains inspectable, and the clinical decision is recorded by people.</p><span className="mono font-mono text-[10px] tracking-wide">OBSERVATORY / {config?.version ?? '1.0'}</span></div>
      </aside>
      <main id="main" tabIndex={-1} data-specialty={isRole ? workspace : undefined} className={`mx-auto w-full min-w-0 max-w-[1900px] px-3 pb-6 sm:px-6 xl:px-8 ${roleLayout ? `${roleLayout.shell} ${roleLayout.canvas}` : ''}`}>
        {!themeSaved && <p data-testid="theme-storage-notice" role="status" className="mt-3 text-xs text-cp-text-muted">Theme changes apply to this visit; this browser cannot save a theme preference.</p>}
        <div className="page-toolbar flex min-h-18 flex-wrap items-center justify-between gap-3 py-4">
          <div className="breadcrumb flex items-center gap-2 text-xs text-cp-text-soft [&_strong]:font-medium [&_strong]:text-cp-text-muted"><span>Observatory</span><ChevronRight size={13} /><strong>{isRole ? roleMetaFor(workspace as Role, meeting).label : workspace === 'cases' ? 'Case selection' : workspace === 'central' ? 'Central MDT' : workspace === 'chair' ? 'Chair control' : 'Workspace wall'}</strong></div>
          <div className="row flex items-center gap-2 wrap flex-wrap toolbar-controls ml-auto max-w-full min-w-0 justify-end [&_.button]:text-xs [&_select]:max-w-full [&_select]:text-xs">
            {meeting && <Badge tone="accent">Current: {MODE_LABEL[meeting.mode]}</Badge>}
            <label className="sr-only" htmlFor="mode">{meeting ? 'Mode for next case' : 'Execution mode'}</label>
            <select data-testid="mode-select" id="mode" value={mode} onChange={event => { modeInitialized.current = true; setMode(event.target.value as Mode); }} disabled={!config || config.modes.length === 0 || pending || Boolean(meeting?.busy)}>
              {config?.modes.length ? config.modes.map(value => <option key={value} value={value}>{MODE_LABEL[value]}</option>) : <option value="rehearsal">Loading execution modes...</option>}
            </select>
            {workspace !== 'cases' && <button data-testid="choose-case" className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold secondary bg-cp-surface text-cp-text" onClick={() => selectWorkspace('cases')}><LayoutGrid size={14} />Choose case</button>}
            {meeting && <button className="icon-button inline-flex size-9 shrink-0 items-center justify-center rounded-lg border-0! bg-[inherit]! text-cp-text-muted hover:bg-cp-surface-soft! hover:text-cp-accent" aria-label="Export meeting and provenance as JSON" disabled={pending} onClick={() => void api.download()}><Download size={17} /></button>}
          </div>
        </div>
        {api.error && <div className="alert mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-cp-danger bg-cp-surface p-4 text-sm text-cp-danger [&>span]:min-w-0 [&>span]:flex-1 [&>span]:break-words global-alert" role="alert"><Flag size={18} /><span>{api.error}</span><button className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline" onClick={api.reconnect}>Reconnect</button><button className="icon-button inline-flex size-9 shrink-0 items-center justify-center rounded-lg border-0! bg-[inherit]! text-cp-text-muted hover:bg-cp-surface-soft! hover:text-cp-accent" aria-label="Dismiss error" onClick={api.clearError}><X size={17} /></button></div>}
        {meeting?.error && <div className="alert mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-cp-danger bg-cp-surface p-4 text-sm text-cp-danger [&>span]:min-w-0 [&>span]:flex-1 [&>span]:break-words" role="alert"><Flag size={18} /><span>{meeting.error}</span><button className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold secondary bg-cp-surface text-cp-text hover:bg-cp-surface-soft" disabled={pending || meeting.busy} onClick={() => void api.mutate('retry', {})}><RefreshCw size={15} />Retry specialist review</button></div>}
        {api.connection === 'reconnecting' && <div className="reconnect-notice mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-cp-warning bg-cp-surface p-4 text-sm" role="status"><RefreshCw size={15} />Connection interrupted. Reconnecting to the same meeting; your input is preserved.<button className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline" onClick={api.reconnect}>Reconnect now</button></div>}
        {workspace === 'cases' ? <CaseSelection cases={api.cases} selected={selectedCase} select={setSelectedCase} meeting={meeting} loading={api.loading} canStart={Boolean(selectedCase && config?.modes.length) && !pending && !api.loading && !meeting?.busy} mode={mode} start={() => void start()} resume={() => selectWorkspace('central')} clearRoom={() => void api.clearRoom()} pending={pending} /> : !meeting ? (isRole ? <RoleStandby role={workspace as Role} mode={mode} /> : <Welcome loading={api.loading} canStart={!api.loading} start={() => selectWorkspace('cases')} mode={mode} />) : <>
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_260px]">
          <div className="min-w-0">
          {!isRole && <PhaseRail meeting={meeting} compact />}
          {workspace === 'central' && <>
            <h1 className="mb-2 text-3xl">Multidisciplinary team review</h1>
            <p className="mb-5 max-w-3xl text-sm leading-7 text-cp-text-muted">Seven specialties review the same patient record independently, publish their own positions, and resolve the questions where those positions conflict. Every step below is recorded and inspectable; the decision remains with the clinical team.</p>
            <div className="mb-5 grid items-start gap-4 md:grid-cols-2"><Timeline meeting={meeting} />{meeting.plan ? <PlanPanel compact showPlan={() => setShowPlan(true)} meeting={meeting} role={activeRole} setRole={setReviewRole} comment={comments[activeRole] ?? ''} setComment={value => setComments(current => ({ ...current, [activeRole]: value }))} pending={pending} mutate={api.mutate} inspect={setEvidence} /> : <FrictionPanel meeting={meeting} pending={pending} followup={() => void api.mutate('followup', {})} />}</div>
            <div className="mb-5"><ConsensusPanel meeting={meeting} openRole={selectWorkspace} /></div>
            <div className="section-heading mb-5 flex items-center justify-between gap-4 [&_.eyebrow]:mb-1 [&>svg]:text-[var(--cp-role,var(--cp-accent))] meeting-section-heading"><div><p className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">SPECIALTY POSITIONS</p><h2>{meeting.plan ? 'The specialties behind the plan' : 'Specialty reviews in progress'}</h2></div><button className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline" onClick={() => selectWorkspace('wall')}><Maximize2 size={15} />Open wall view</button></div>
            <div className="role-grid mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{ROLES.map(role => <RoleCard key={role} role={role} meeting={meeting} open={() => selectWorkspace(role)} />)}</div>
            <MeetingSignals meeting={meeting} inspect={setEvidence} />
            <details className="my-5 rounded-xl border border-cp-border bg-cp-surface p-4"><summary>Case timeline and treatment history</summary><CaseTimeline data={meeting.case} /></details>
            {(isConversionCase(meeting.case) || clinicalCaseKind(meeting.case)) && <ManagementOptions data={meeting.case} />}
          </>}
          {workspace === 'chair' && <><div className="mb-5 grid items-start gap-4 md:grid-cols-2"><Timeline meeting={meeting} /><div className="min-w-0"><Chair meeting={meeting} pending={pending} followup={() => void api.mutate('followup', {})} retry={() => void api.mutate('retry', {})} openRole={selectWorkspace} clearRoom={() => void api.clearRoom()} />{meeting.plan && <PlanPanel compact showPlan={() => setShowPlan(true)} meeting={meeting} role={activeRole} setRole={setReviewRole} comment={comments[activeRole] ?? ''} setComment={value => setComments(current => ({ ...current, [activeRole]: value }))} pending={pending} mutate={api.mutate} inspect={setEvidence} />}</div></div><FrictionPanel meeting={meeting} pending={pending} followup={() => void api.mutate('followup', {})} /></>}
          {workspace === 'wall' && <><div className="section-heading mb-5 flex items-center justify-between gap-4 [&_.eyebrow]:mb-1 [&>svg]:text-[var(--cp-role,var(--cp-accent))]"><div><p className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">ONE CASE · SEVEN INDEPENDENT WORKSPACES</p><h1>Specialty workspaces</h1></div><Badge pulse={meeting.busy} tone="accent">{meeting.busy ? 'Reviews in progress' : `${openQuestions} open questions`}</Badge></div><div className="wall-grid mb-6 grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{ROLES.map(role => <RoleCard key={role} role={role} meeting={meeting} open={() => selectWorkspace(role)} expanded />)}</div><FrictionPanel meeting={meeting} pending={pending} followup={() => void api.mutate('followup', {})} />{meeting.plan && <PlanPanel meeting={meeting} role={activeRole} setRole={setReviewRole} comment={comments[activeRole] ?? ''} setComment={value => setComments(current => ({ ...current, [activeRole]: value }))} pending={pending} mutate={api.mutate} inspect={setEvidence} />}</>}
          {isRole && <Specialist role={workspace as Role} meeting={meeting} pending={pending} guidance={drafts[workspace as Role] ?? ''} setGuidance={value => setDrafts(current => ({ ...current, [workspace]: value }))} steer={steer} mutate={api.mutate} inspect={setEvidence} review={meeting.plan && <PlanPanel compact showPlan={() => setShowPlan(true)} meeting={meeting} role={workspace as Role} comment={comments[workspace as Role] ?? ''} setComment={value => setComments(current => ({ ...current, [workspace]: value }))} pending={pending} mutate={api.mutate} inspect={setEvidence} />} />}
          </div>
          <aside data-testid="case-rail" aria-label="Case snapshot" className="min-w-0 xl:sticky xl:top-4"><CaseHeader meeting={meeting} showCase={() => setShowCase(true)} compact /></aside>
          </div>
          <footer className="meeting-footer flex flex-wrap items-center justify-between gap-3 py-6 text-[10px] text-cp-text-muted"><span className="row flex items-center gap-2"><span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success" />{meeting.closed_at ? `Decision captured ${time(meeting.closed_at)}` : 'Live shared state · changes recorded with provenance'}</span><span className="mono font-mono text-[10px] tracking-wide">ROUND {String(meeting.round).padStart(2, '0')} / {meeting.id.slice(0, 8)}</span>{readyForAction && <button className="text-button inline-flex items-center gap-1.5 border-0! bg-[inherit]! py-1 text-xs font-medium text-cp-accent hover:underline" onClick={() => selectWorkspace('chair')}>Chair controls <ArrowRight size={13} /></button>}</footer>
        </>}
      </main>
    </div>
    {evidence && <EvidenceDrawer selection={evidence} evidence={meeting?.evidence ?? []} close={() => setEvidence(null)} />}
    {showCase && meeting && <Modal testId="case-record-drawer" title="The complete case context" close={() => setShowCase(false)} wide><div data-testid="case-dossier"><CompleteCaseRecord data={meeting.case} /></div></Modal>}
    {showPlan && meeting && <Modal title="Current MDT proposal and conditions" close={() => setShowPlan(false)} wide><PlanPanel readOnly meeting={meeting} role={activeRole} comment="" setComment={() => {}} pending={pending} mutate={api.mutate} inspect={setEvidence} /></Modal>}
    {showGuide && <Modal title="A 60–90 second presenter flow" close={() => setShowGuide(false)}>
      <p className="text-sm leading-7 text-cp-text-muted">Use Scripted demonstration for repeatable pacing. Live AI review can take longer. The meeting advances when specialist review steps complete.</p>
      <ol className="my-6 space-y-5 text-sm leading-7">
        <li><strong>00–15s · Activate the case</strong><p>Start case. Watch seven agents take different paths through the same patient.</p></li>
        <li><strong>15–35s · Make the disagreement visible</strong><p>Open Radiology. Review the supplied imaging reports, available measurements and unresolved findings. Where a diagram is available, it is illustrative rather than clinical imaging.</p></li>
        <li><strong>35–50s · Guide the review</strong><p>Use or ignore a saved review preference. Send focused clinical guidance and wait for the revised position.</p></li>
        <li><strong>50–65s · Focus on unresolved questions</strong><p>Return to Central MDT or Chair. Request targeted follow-up once agents are idle. Inspect a claim and its source limitations.</p></li>
        <li><strong>65–90s · Bring the decision back to people</strong><p>Compare the alternatives, review conditions and concur as each required human role, or object with a reason. Export the captured decision.</p></li>
      </ol><p className="text-sm leading-7 text-cp-text-muted">No timer advances the clinical workflow. If work fails, use Retry specialist review in Chair control.</p>
    </Modal>}
    {api.needsAuth && <Modal title="Presenter access" close={() => { setToken(''); api.dismissAuth(); }}><p>Enter the presenter secret to access this meeting. It is used only to establish access and is not saved by this page.</p><form onSubmit={event => { event.preventDefault(); const secret = token; setToken(''); void api.authenticate(secret); }}><label htmlFor="presenter-token">Presenter secret</label><input id="presenter-token" type="password" autoComplete="current-password" value={token} onChange={event => setToken(event.target.value)} required autoFocus />{api.error && <p role="alert" className="error-text my-3 text-sm text-cp-danger">{api.error}</p>}<button className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold primary border-cp-accent! bg-cp-accent! text-cp-accent-fg! hover:bg-cp-accent-hover!" disabled={pending || !token.trim()}><LockKeyhole size={16} />Unlock presenter controls</button></form></Modal>}
  </div>;
}

function NavItem({ selected, onClick, icon, title, detail, active = false, testId, specialty }: { selected: boolean; onClick: () => void; icon: React.ReactNode; title: string; detail: string; active?: boolean; testId: string; specialty?: Role }) {
  return <button data-testid={testId} aria-label={title} className={`nav-item my-1 flex w-full items-center gap-3 rounded-xl border border-cp-bg-elevated bg-[inherit] px-3 py-3 text-left text-cp-text-muted hover:bg-cp-surface-soft [&>span:first-of-type]:min-w-0 [&>span:first-of-type]:flex-1 [&_strong]:block [&_strong]:text-xs [&_strong]:font-semibold [&_small]:mt-1 [&_small]:block [&_small]:truncate [&_small]:text-[10px] [&_small]:text-cp-text-soft ${specialty ? `${ROLE_LAYOUTS[specialty].shell} [&>svg:first-child]:text-[var(--cp-role)]` : ''} ${selected ? 'selected border-l-4! border-[var(--cp-role,var(--cp-accent))]! bg-[color-mix(in_srgb,var(--cp-role,var(--cp-accent))_9%,var(--cp-surface))]! text-cp-text!' : ''}`} aria-current={selected ? 'page' : undefined} onClick={onClick}>{icon}<span><strong>{title}</strong><small>{detail}</small></span>{active ? <span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success pulse motion-safe:animate-pulse" /> : selected ? <ChevronRight size={14} /> : null}</button>;
}
function Welcome({ loading, canStart, start, mode }: { loading: boolean; canStart: boolean; start: () => void; mode: Mode }) {
  return <div className="welcome pt-2">
    <section className="welcome-hero grid items-center gap-8 border-b border-cp-border pb-10 pt-6 xl:grid-cols-[1.2fr_1fr]"><div className="welcome-copy [&>h1]:mt-6 [&>h1]:text-4xl [&>h1]:font-medium [&>h1]:leading-tight [&>h1]:tracking-tight sm:[&>h1]:text-5xl [&>h1>span]:text-cp-accent"><Badge tone="accent"><span className="status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success" />MULTIDISCIPLINARY TEAM DEMONSTRATION</Badge><h1>Multidisciplinary team review.<br /><span>Seven specialty workspaces, one shared decision.</span></h1><p className="welcome-description mt-6 text-sm leading-8 text-cp-text-muted">Each specialty reviews the case independently and publishes a position.<br />The chair identifies unresolved questions between positions.<br />Clinical staff review the positions and confirm the plan.</p><div className="welcome-action mt-7 flex flex-wrap items-center gap-5 [&_strong]:text-xs [&_small]:mt-1 [&_small]:block [&_small]:text-[10px] [&_small]:text-cp-text-muted"><button data-testid="start-case" className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold primary border-cp-accent! bg-cp-accent! text-cp-accent-fg! hover:bg-cp-accent-hover! large min-h-12! px-6! py-3! text-sm!" onClick={start} disabled={!canStart}>{loading ? <LoaderCircle className="spin motion-safe:animate-spin" size={18} /> : <Play size={18} />}{loading ? 'Connecting…' : 'Start case'}<ArrowRight size={18} /></button><div><strong>A live, end-to-end demonstration</strong><small>{MODE_LABEL[mode]} · 60–90 second presenter flow</small></div></div></div><div className="orbit" aria-hidden="true"><div className="orbit-ring outer" /><div className="orbit-ring inner" /><div className="orbit-center"><Network size={34} /><strong>SHARED<br />MDT STATE</strong><small>Human supervised</small></div>{ROLES.map((role, index) => { const Icon = ROLE_META[role].icon; return <div className={`orbit-node orbit-${index}`} key={role}><Icon size={20} /><span>{ROLE_META[role].label}</span></div>; })}</div></section>
    <div className="welcome-principles my-9 grid gap-6 lg:grid-cols-3 [&>article]:flex [&>article]:gap-3 [&_h3]:mb-2 [&_h3]:text-sm [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><article><span className="principle-number font-mono text-xs text-cp-accent">01</span><div><h3>Specialty review</h3><p>Seven clinical perspectives, focused reviews and structured positions. No finding is a decision by itself.</p></div></article><article><span className="principle-number font-mono text-xs text-cp-accent">02</span><div><h3>Unresolved questions surfaced</h3><p>Disagreement is surfaced, evidence is challenged, and only unresolved questions return.</p></div></article><article><span className="principle-number font-mono text-xs text-cp-accent">03</span><div><h3>Human review and sign-off</h3><p>Visible guidance, explicit concurrence and a source trail behind every important claim.</p></div></article></div>
    <SectionHeading eyebrow="SPECIALTY WORKSPACES" title="One workspace per specialty" aside={<span className="muted text-sm leading-7 text-cp-text-muted">Activate one case. Watch every workspace respond.</span>} />
    <div className="ready-roles grid grid-cols-2 overflow-hidden rounded-2xl border border-cp-border bg-cp-surface sm:grid-cols-4 2xl:grid-cols-7 [&>div]:flex [&>div]:flex-col [&>div]:items-start [&>div]:border-b [&>div]:border-r [&>div]:border-cp-border [&>div]:p-5 [&_svg]:mb-4 [&_svg]:text-cp-accent [&_h3]:text-sm [&_p]:mt-2 [&_p]:text-xs [&_p]:leading-6 [&_p]:text-cp-text-muted">{ROLES.map(role => { const meta = ROLE_META[role]; const Icon = meta.icon; return <div key={role}><Icon size={24} /><h3>{meta.label}</h3><p>{meta.description}</p><span className="ready-label mt-auto pt-5 font-mono text-[9px] tracking-wide text-cp-text-soft">AWAITING CASE</span></div>; })}</div>
  </div>;
}
export function RoleStandby({ role, mode }: { role: Role; mode: Mode }) {
  const meta = ROLE_META[role];
  const layout = ROLE_LAYOUTS[role];
  const Icon = meta.icon;
  return <section data-testid={`standby-${role}`} data-standby="true" aria-label={`${meta.label} workspace standby`} className={layout.shell}>
    <div className={`workspace-heading mb-4 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3 p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] ${layout.header}`}>
      <div aria-hidden="true" className="role-emblem flex size-16 shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-[var(--cp-role)] text-[var(--cp-role)]"><Icon size={28} /><span className="font-mono text-[10px] tracking-widest">{meta.short}</span></div>
      <div className="role-heading-copy min-w-0"><p className="role-eyebrow font-mono text-[10px] tracking-widest text-cp-text-muted">{meta.person} / SPECIALIST WORKSPACE</p><h1 className="role-title mt-2 text-2xl sm:text-3xl">{layout.title}</h1><p className="role-subtitle mt-2 text-sm leading-6 text-cp-text-muted">{meta.title}</p></div>
      <div className="role-state col-span-2 sm:col-span-1"><Badge>Standby</Badge></div>
    </div>
    <div data-testid="standby-notice" role="status" className="rounded-2xl border border-cp-border bg-cp-surface p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-cp-border text-cp-text-muted"><LoaderCircle size={24} className="motion-safe:animate-spin" /></span>
        <div className="min-w-0">
          <h2 className="text-xl">Waiting for the orchestrator to open a case</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-cp-text-muted">This screen is connected to the meeting room and is up to date. It stays empty until a case is activated. When the orchestrator opens one, this workspace fills with the {meta.label.toLowerCase()} review for that patient, and the reasoning is shown here step by step as it is produced.</p>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-cp-text-muted">No patient record is loaded. Nothing from a previous meeting is shown here.</p>
          <p className="mt-4 font-mono text-[10px] tracking-widest text-cp-text-soft">CONNECTED · {MODE_LABEL[mode].toUpperCase()} · NO ACTIVE CASE</p>
        </div>
      </div>
      <div className="mt-7 border-t border-cp-border pt-5">
        <p className="eyebrow mb-3 font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">WHAT THIS SPECIALTY WILL BE RESPONSIBLE FOR</p>
        <ol className="grid gap-3 sm:grid-cols-3 list-none [&>li]:flex [&>li]:items-center [&>li]:gap-3 [&>li]:rounded-xl [&>li]:border [&>li]:border-cp-border [&>li]:bg-cp-bg-elevated [&>li]:p-4 [&>li]:text-[13px] [&>li]:leading-6 [&_span]:font-mono [&_span]:text-[11px] [&_span]:text-cp-text-soft">{layout.focus.map((focus, index) => <li key={focus}><span>{String(index + 1).padStart(2, '0')}</span>{focus}</li>)}</ol>
      </div>
    </div>
  </section>;
}
function CaseHeader({ meeting, showCase, compact = false }: { meeting: Meeting; showCase: () => void; compact?: boolean }) {
  const data = meeting.case;
  const name = first(data, ['pseudonym', 'patient', 'name', 'patient_name', 'patient_id', 'id', 'case_id'], 'Case activating');
  const question = first(data, ['question', 'clinical_question', 'case_question', 'current_clinical_question'], 'Establishing the multidisciplinary case question…');
  const diagnosis = first(data, ['diagnosis', 'disease', 'summary'], 'Loading patient context');
  const age = first(data, ['age', 'age_years']);
  const stage = first(data, ['stage', 'disease_stage']);
  const positions = ROLES.filter(role => meeting.roles[role]?.position).length;
  const open = meeting.frictions.filter(item => !item.resolved).length;
  const context = [
    { title: 'History', value: first(data, ['history', 'important_history']) },
    { title: 'Biomarkers', value: first(data, ['biomarkers', 'molecular_findings']) },
    { title: 'Treatment', value: first(data, ['treatment', 'previous_treatment', 'treatment_history']) },
  ].filter(item => item.value);
  if (compact) return <section data-testid="specialty-case-summary" className="rounded-xl border border-cp-border bg-cp-surface p-4">
    <p className="font-mono text-[10px] tracking-widest text-cp-accent">CASE AT A GLANCE</p><p className="mt-3 break-words text-xs font-semibold">{name}{age ? ` / ${age}${/^\d+$/.test(age) ? ' years' : ''}` : ''}</p>
    <h2 className="mt-3 text-sm leading-6">{diagnosis}</h2>{stage && <p className="mt-2 text-xs leading-6 text-cp-text-muted">{stage}</p>}
    <div className="mt-4 border-t border-cp-border pt-3"><h3 className="text-xs">Treatment context</h3><p className="mt-2 line-clamp-4 text-xs leading-6 text-cp-text-muted">{first(data, ['treatment', 'previous_treatment', 'treatment_history'], 'See the complete case record.')}</p></div>
    <details className="mt-4 border-t border-cp-border pt-3"><summary>The shared MDT question <ChevronRight size={13} /></summary><p className="text-xs leading-6">{question}</p><dl className="mt-3 space-y-3">{context.map(item => <div key={item.title}><dt className="text-xs font-semibold">{item.title}</dt><dd className="mt-1 text-xs leading-6 text-cp-text-muted">{item.value}</dd></div>)}</dl></details>
    <button data-testid="view-case-record" className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-lg border border-cp-border px-3 py-2 text-xs font-medium text-cp-accent" onClick={showCase}>View case record <ArrowUpRight size={14} /></button>
  </section>;
  return <section className="case-header overflow-hidden rounded-2xl border border-cp-border bg-cp-surface px-5 pt-5 sm:px-7 sm:pt-6">
    <div className="case-identity flex items-start gap-4 [&_h1]:mb-2 [&_h1]:mt-1 [&_h1]:text-2xl [&_.row]:text-xs [&_.row]:text-cp-text-muted">
      <div className="case-avatar flex size-12 shrink-0 items-center justify-center rounded-xl bg-cp-accent-soft text-cp-accent"><Users size={24} /></div>
      <div className="min-w-0"><p className="eyebrow break-words font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">CASE / {name}</p><h1>{diagnosis}</h1>
        <div className="row flex flex-wrap items-center gap-2">{age && <span>{age}{/^\d+$/.test(age) ? ' years' : ''}</span>}{stage && <><span>/</span><span>{stage}</span></>}
          <button data-testid="view-case-record" className="inline-flex items-center gap-1.5 py-1 text-xs font-medium text-cp-accent hover:underline" onClick={showCase}>View case record <ArrowUpRight size={14} /></button>
        </div>
      </div>
    </div>
    {context.length > 0 && <dl className="case-context-summary mt-5 grid gap-4 border-t border-cp-border pt-4 sm:grid-cols-3 [&_dt]:font-mono [&_dt]:text-[10px] [&_dt]:uppercase [&_dt]:text-cp-text-soft [&_dd]:mt-1 [&_dd]:break-words [&_dd]:text-xs [&_dd]:leading-6 [&_dd]:text-cp-text-muted">{context.map(item => <div key={item.title}><dt>{item.title}</dt><dd>{item.value}</dd></div>)}</dl>}
    <div className="case-question my-5 border-l-2 border-cp-accent pl-4"><span className="font-mono text-[10px] tracking-widest text-cp-accent">THE QUESTION BEFORE THE TEAM</span><p className="mt-1 text-base leading-7">{question}</p></div>
    <div className="case-stats -mx-5 grid grid-cols-2 gap-y-4 border-t border-cp-border bg-cp-bg-elevated px-5 py-4 sm:-mx-7 sm:grid-cols-4 sm:px-7 [&>div]:flex [&>div]:flex-wrap [&>div]:items-center [&>div]:gap-2 [&>div]:border-r [&>div]:border-cp-border [&>div]:px-3 [&_strong]:text-3xl [&_strong]:font-medium [&_strong_span]:text-base [&_strong_span]:text-cp-text-soft [&_small]:text-[10px] [&_small]:text-cp-text-muted">
      <div><strong>7<span>/7</span></strong><small>specialist agents</small></div><div><strong>{String(meeting.round).padStart(2, '0')}</strong><small>current round</small></div><div className={open ? '[&_strong]:text-cp-accent' : ''}><strong>{String(open).padStart(2, '0')}</strong><small>open questions</small></div><div><strong>{positions}<span>/7</span></strong><small>positions received</small></div>
    </div>
  </section>;
}
function PhaseRail({ meeting, compact = false }: { meeting: Meeting; compact?: boolean }) {
  if (compact) return <section data-testid="phase" data-phase={meeting.phase} aria-label="Meeting progress" className="my-3 flex flex-wrap items-center gap-3 text-xs text-cp-text-muted">
    <Status value={meeting.phase} /><span>Round {meeting.round}</span><span>{meeting.frictions.filter(item => !item.resolved).length} open MDT questions</span>
    {meeting.busy && <span className="inline-flex items-center gap-2"><LoaderCircle size={13} className="motion-safe:animate-spin" />Specialists reviewing</span>}
  </section>;
  const steps = [
    { name: 'Activate', phases: ['IDLE', 'CASE_LOADING'] },
    { name: 'Investigate', phases: ['INITIAL_ANALYSIS'] },
    { name: 'Collect positions', phases: ['POSITION_COLLECTION'] },
    { name: 'Resolve friction', phases: ['FRICTION_ANALYSIS', 'TARGETED_DISCUSSION', 'POSITION_UPDATE'] },
    { name: 'Propose plan', phases: ['PLAN_PROPOSAL'] },
    { name: 'Human review', phases: ['CONCURRENCE'] },
    { name: 'Capture decision', phases: ['DECISION_CAPTURED'] },
  ];
  const active = steps.findIndex(step => step.phases.includes(meeting.phase));
  return <section data-testid="phase" data-phase={meeting.phase} className="phase-rail my-6 [&>ol]:flex [&>ol]:gap-2 [&>ol]:overflow-x-auto [&>ol]:pb-2 [&_li]:flex [&_li]:min-w-28 [&_li]:flex-1 [&_li]:items-center [&_li]:gap-2 [&_li]:border-b-2 [&_li]:border-cp-border [&_li]:py-3 [&_li]:text-xs" aria-label="Meeting progress"><div className="phase-top mb-3 flex flex-wrap items-center gap-3 [&>.eyebrow]:flex [&>.eyebrow]:items-center [&>.eyebrow]:gap-1"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft"><GitBranch size={13} />MEETING PROGRESS</span><Status value={meeting.phase} />{meeting.busy && <span className="working-label ml-auto inline-flex items-center gap-2 text-xs text-cp-text-muted"><LoaderCircle size={13} className="spin motion-safe:animate-spin" />Specialists reviewing the case</span>}</div><ol>{steps.map((step, index) => <li key={step.name} className={index === active ? 'current border-cp-accent! font-semibold text-cp-accent [&_.phase-number]:bg-cp-accent [&_.phase-number]:text-cp-accent-fg' : index < active ? 'passed border-cp-border-strong! [&_.phase-number]:text-cp-success' : ''} aria-current={index === active ? 'step' : undefined}><span className="phase-number inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-cp-border font-mono text-[9px]">{index < active ? <Check size={12} /> : index + 1}</span><span>{step.name}</span>{index === 3 && <GitBranch size={12} />}</li>)}</ol>{PHASE_MEANING[meeting.phase] && <p data-testid="phase-meaning" className="mt-3 max-w-4xl text-[13px] leading-6 text-cp-text-muted">{PHASE_MEANING[meeting.phase]}</p>}<details className="state-detail mt-2 [&_summary]:text-xs [&>div]:my-3 [&>div]:flex [&>div]:flex-wrap [&>div]:gap-2 [&>p]:text-[13px] [&>p]:leading-6 [&>p]:text-cp-text-muted"><summary>Review meeting stages <ChevronRight size={12} /></summary><div>{PHASES.map(phase => <Badge key={phase} tone={meeting.phase === phase ? 'accent' : ''}>{statusLabel(phase)}</Badge>)}<Badge tone={meeting.phase === 'ERROR' ? 'danger' : ''}>Review needs attention</Badge></div><p>Unresolved questions → focused discussion → revised specialist assessments → review of remaining differences. Objections return the plan to focused discussion.</p></details></section>;
}
function distinctUncertainty(meeting: Meeting, role: Role): string | null {
  const own = meeting.roles[role]?.trace.uncertainties ?? [];
  if (!own.length) return null;
  const shared = new Set<string>();
  for (const other of ROLES) if (other !== role) for (const item of meeting.roles[other]?.trace.uncertainties ?? []) shared.add(item);
  return own.find(item => !shared.has(item)) ?? own[0];
}
function RoleCard({ role, meeting, open, expanded = false }: { role: Role; meeting: Meeting; open: () => void; expanded?: boolean }) {
  const meta = roleMetaFor(role, meeting);
  const Icon = meta.icon;
  const state = meeting.roles[role];
  const working = Boolean(state && /ANALYZ|SEARCH|CHECK|REASSESS|RUNNING|WORKING/i.test(state.status));
  return <article className={`role-card relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-cp-border bg-cp-surface px-4 pt-4 ${working ? 'working border-cp-accent!' : ''} ${expanded ? 'expanded [&_.card-assessment]:line-clamp-5!' : ''} ${state?.error ? 'has-error border-cp-danger!' : ''}`}><div className="role-card-top mb-3 flex items-center gap-2"><span className="role-icon flex size-9 shrink-0 items-center justify-center rounded-lg bg-cp-accent-soft text-cp-accent"><Icon size={21} /></span><span className="role-number ml-auto font-mono text-[9px] tracking-wider text-cp-text-soft">{meta.short} / 0{ROLES.indexOf(role) + 1}</span><button className="icon-button inline-flex size-9 shrink-0 items-center justify-center rounded-lg border-0! bg-[inherit]! text-cp-text-muted hover:bg-cp-surface-soft! hover:text-cp-accent" onClick={open} aria-label={`Open ${meta.label} workspace`}><ArrowUpRight size={18} /></button></div><button className="role-title border-0! bg-[inherit]! p-0 text-left [&_h3]:text-base [&>span]:mt-1 [&>span]:block [&>span]:text-xs [&>span]:text-cp-text-soft" onClick={open}><h3>{meta.label}</h3><span>{meta.description}</span></button><div className="role-status mt-4 flex flex-wrap gap-1.5"><Status value={state?.status ?? 'IDLE'} />{state?.position && <Badge tone={state.position.autonomy === 'ESCALATE' ? 'danger' : ''}>{state.position.autonomy}</Badge>}</div><p className="card-assessment my-4 line-clamp-3 min-h-15 text-xs leading-6">{state?.error ?? state?.position?.position ?? state?.trace.assessment ?? 'Waiting for case activation.'}</p>
    {expanded && <><div className="wall-context border-t border-cp-border py-3 [&>p]:mt-1 [&>p]:line-clamp-3 [&>p]:text-[13px] [&>p]:leading-6 [&>p]:text-cp-text-muted"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">WHAT THIS SPECIALTY IS RESPONSIBLE FOR</span><p>{ROLE_LAYOUTS[role].focus.slice(0, 3).join(' · ')}</p></div><div className="wall-finding border-t border-cp-border py-3 [&>p]:mt-1 [&>p]:line-clamp-3 [&>p]:text-[13px] [&>p]:leading-6"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">ITS OWN FINDING</span><p>{state?.trace.observations[0] ?? 'No finding recorded yet for this specialty.'}</p></div>{(state?.trace.uncertainties.length ?? 0) > 0 && <div className="wall-uncertainties border-t border-cp-warning py-3 [&>p]:mt-1 [&>p]:text-[13px] [&>p]:leading-6"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">WHAT IT CANNOT YET SETTLE</span><p>{distinctUncertainty(meeting, role)}</p></div>}</>}
    <div className="role-card-bottom -mx-4 mt-auto flex items-center gap-2 border-t border-cp-border bg-cp-bg-elevated px-4 py-3 [&>span:nth-child(2)]:min-w-0 [&>span:nth-child(2)]:truncate [&>span:nth-child(2)]:text-[10px] [&>span:nth-child(2)]:text-cp-text-soft [&_small]:ml-auto [&_small]:text-cp-accent"><span className={`status-dot inline-block size-1.5 shrink-0 rounded-full bg-cp-success ${working ? 'pulse motion-safe:animate-pulse' : ''}`} /><span>{state?.activity.length ? activitySummary(state.activity.at(-1)!, role) : working ? 'Specialist investigating' : 'Awaiting specialist activity'}</span>{state?.revision ? <small>v{state.revision}</small> : null}</div>
  </article>;
}
function FrictionPanel({ meeting, pending, followup }: { meeting: Meeting; pending: boolean; followup: () => void }) {
  const open = meeting.frictions.filter(item => !item.resolved);
  const resolved = meeting.frictions.filter(item => item.resolved);
  const allowed = !pending && !meeting.busy && meeting.phase !== 'DECISION_CAPTURED' && meeting.phase !== 'ERROR' && meeting.frictions.length > 0;
  return <section className={`panel min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-5 sm:p-6 friction-panel mb-6 border-t-4! border-t-cp-accent! ${open.length === 0 && resolved.length ? 'converged border-t-cp-success!' : ''}`}><SectionHeading eyebrow="UNRESOLVED QUESTIONS" title={open.length ? `${open.length} question${open.length === 1 ? '' : 's'} standing between positions and a plan` : resolved.length ? 'No unresolved questions remain.' : 'Where the discussion will focus'} aside={<Badge tone={open.length ? 'warning' : 'success'}>{open.length ? `${open.filter(item => item.blocking).length} blocking` : resolved.length ? `${resolved.length} resolved` : 'Collecting perspectives'}</Badge>} />
    {!open.length && !resolved.length && <div className="friction-empty flex items-start gap-5 py-3 [&_h3]:text-base [&_p]:mt-2 [&_p]:text-sm [&_p]:leading-7 [&_p]:text-cp-text-muted"><div className="friction-symbol flex size-12 shrink-0 items-center justify-center rounded-xl bg-cp-accent-soft text-cp-accent"><GitBranch size={28} /></div><div><h3>Collecting specialty positions</h3><p>The chair compares the published positions and lists here any contradiction, missing evidence or unresolved uncertainty that must be settled before a plan can be proposed.</p></div></div>}
    <div className="friction-list grid gap-4 xl:grid-cols-2 [&>*:only-child]:col-span-full">{open.map((item, index) => <article className="friction-item rounded-xl border border-cp-border p-4 sm:p-5" key={item.id}><div className="friction-question flex items-start gap-4 [&_h3]:mt-2 [&_h3]:text-base"><span className="friction-index font-mono text-2xl text-cp-accent">0{index + 1}</span><div><div className="row flex items-center gap-2 wrap flex-wrap"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">{item.blocking ? 'BLOCKING QUESTION' : 'OPEN QUESTION'}</span><Badge>{item.id}</Badge></div><h3>{item.question}</h3></div></div><div className="friction-positions my-4 flex flex-wrap gap-3 border-y border-cp-border py-3 [&>div]:flex [&>div]:items-center [&>div]:gap-2 [&>div]:text-xs">{item.roles.map(role => <div key={role}><span>{ROLE_META[role]?.label ?? label(role)}</span><ArrowRight size={14} /><Status value={meeting.roles[role]?.position?.stance ?? 'PENDING'} /></div>)}</div>{item.missing.length > 0 && <div className="missing-evidence mt-4"><span className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">WHAT WOULD MOVE THIS FORWARD</span><BulletList items={item.missing} /></div>}</article>)}</div>
    {resolved.length > 0 && <details className="resolved-frictions mt-4 border-t border-cp-border pt-4 [&>div]:py-3 [&_h4]:flex [&_h4]:gap-2 [&_p]:mt-2 [&_p]:text-xs [&_p]:text-cp-text-muted"><summary><CheckCheck size={18} />{resolved.length} resolved question{resolved.length === 1 ? '' : 's'}<ChevronRight size={14} /></summary>{resolved.map(item => <div key={item.id}><h4><Check size={15} />{item.question}</h4><p>{item.resolution ?? 'Resolved by the MDT service.'}</p></div>)}</details>}
    {open.length > 0 && <div className="friction-footer mt-5 flex flex-wrap items-center justify-between gap-4 [&>p]:flex [&>p]:items-center [&>p]:gap-2 [&>p]:text-xs [&>p]:text-cp-text-muted"><p><GitBranch size={16} />Next round involves only the relevant specialists.</p><button data-testid="followup" className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold primary border-cp-accent! bg-cp-accent! text-cp-accent-fg! hover:bg-cp-accent-hover!" disabled={!allowed} onClick={followup}>{meeting.busy ? <LoaderCircle size={16} className="spin motion-safe:animate-spin" /> : <ArrowRight size={16} />}{meeting.busy ? 'Agents working…' : 'Request targeted follow-up'}</button></div>}
  </section>;
}

interface PlanProps {
  compact?: boolean;
  readOnly?: boolean;
  showPlan?: () => void;
  meeting: Meeting;
  role: Role;
  setRole?: (role: Role) => void;
  comment: string;
  setComment: (comment: string) => void;
  pending: boolean;
  mutate: (action: string, body: unknown) => Promise<boolean>;
  inspect: (selection: EvidenceSelection) => void;
}
function PlanPanel({ meeting, role, setRole, comment, setComment, pending, mutate, inspect, compact = false, readOnly = false, showPlan }: PlanProps) {
  const plan = meeting.plan;
  if (!plan) return null;
  const planVersion = plan.version;
  const captured = meeting.phase === 'DECISION_CAPTURED';
  const reviewable = meeting.phase === 'CONCURRENCE' && !meeting.busy && !pending;
  const humanCount = ROLES.filter(item => concurrenceActor(meeting, item) === 'human').length;
  const agentCount = ROLES.filter(item => concurrenceActor(meeting, item) === 'agent').length;
  const concurrenceCount = humanCount + agentCount;
  const current = humanConcurred(meeting, role);
  async function respond(action: 'concur' | 'object') {
    const submitted = comment.trim();
    if (await mutate(action, { role, comment: submitted, plan_version: planVersion })) setComment('');
  }
  return <section data-testid={compact ? 'review-desk' : undefined} className={`plan-panel overflow-hidden rounded-2xl border border-cp-accent bg-cp-surface ${compact ? '' : 'my-6'} ${captured ? 'captured border-cp-success!' : ''}`} aria-label={captured ? 'Captured MDT decision' : 'Proposed MDT plan'}>
    {!compact && <>
    <div className="plan-hero flex flex-wrap items-center gap-5 border-b border-cp-highlight bg-cp-accent-soft p-5 sm:p-7 [&_h2]:my-2 [&_h2]:text-3xl [&_h2]:font-medium [&_p:last-child]:text-sm [&_p:last-child]:text-cp-text-muted [&>.badge]:ml-auto"><div className="plan-emblem flex size-14 shrink-0 items-center justify-center rounded-full border border-cp-accent text-cp-accent">{captured ? <CheckCheck size={33} /> : <Network size={33} />}</div><div><p className="eyebrow font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">{captured ? 'DECISION CAPTURED / PROVENANCE PRESERVED' : 'SPECIALIST POSITIONS → MULTIDISCIPLINARY PLAN'}</p><h2>{captured ? 'Decision captured.' : 'Specialist positions inform the proposed plan.'}</h2><p>{captured ? 'The recorded outcome remains a demonstration, not a clinical instruction.' : 'A proposal from the team. The decision stays with people.'}</p></div><Badge>VERSION {plan.version}</Badge></div>
    <div className="plan-body grid gap-7 p-5 sm:p-7 xl:grid-cols-[minmax(0,1.25fr)_minmax(300px,1fr)] [&>div:first-child>h3]:text-2xl"><div><h3>{plan.title}</h3><p className="plan-summary mt-4 text-sm leading-8 text-cp-text-muted">{plan.summary}</p><h4>Proposed next steps</h4><ol className="plan-actions my-4 list-none space-y-4 [&>li]:flex [&>li]:gap-3 [&>li>span]:font-mono [&>li>span]:text-cp-accent [&_p]:text-sm [&_p]:leading-7">{plan.actions.map((action, index) => <li key={index}><span>{String(index + 1).padStart(2, '0')}</span><p>{action}</p></li>)}</ol>{plan.conditions.length > 0 && <div className="plan-conditions my-5 rounded-r-xl border-l-2 border-cp-warning bg-cp-bg-elevated px-4 pb-3 pt-1"><h4>Conditions & retained uncertainty</h4><BulletList items={plan.conditions} /></div>}<button className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold secondary bg-cp-surface text-cp-text hover:bg-cp-surface-soft" onClick={() => inspect({ ids: plan.evidence_ids, claim: plan.summary })}><ExternalLink size={15} />Inspect plan evidence - {plan.evidence_ids.length} sources</button></div>
      <div className="concurrence-panel border-t border-cp-border pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0 [&>.muted]:my-3 [&>.muted]:text-xs"><div className="row flex items-center gap-2 between justify-between"><h3>Concurrence</h3><Badge tone={concurrenceCount === 7 ? 'success' : ''}>{concurrenceCount} / 7</Badge></div><p className="muted text-sm leading-7 text-cp-text-muted">{humanCount} human, {agentCount} agent - version {plan.version}. AUTO agent concurrence follows demo policy; it is not human sign-off.</p><div className="concurrence-list [&>div]:flex [&>div]:items-center [&>div]:justify-between [&>div]:gap-3 [&>div]:border-b [&>div]:border-cp-border [&>div]:py-3 [&>div]:text-xs [&>div>span:last-child]:inline-flex [&>div>span:last-child]:items-center [&>div>span:last-child]:gap-1 [&>div>span:last-child]:text-right [&>div>span:last-child]:text-[10px] [&>div>span:last-child]:text-cp-text-muted">{ROLES.map(item => { const concur = meeting.concurrences[item]; const actor = concurrenceActor(meeting, item); const agent = concur?.actor === 'agent' && concur.plan_version === plan.version; const stale = concur && concur.plan_version !== plan.version; return <div key={item} className={actor ? 'signed [&_svg]:text-cp-success' : ''}><span>{ROLE_META[item].label}</span><span>{actor === 'human' ? <><Check size={14} />Human concurred</> : actor === 'agent' ? <><Check size={14} />Auto-concurred (demo policy)</> : stale ? 'Review new version' : agent ? 'Agent support - human pending' : 'Awaiting review'}</span></div>; })}</div>
      </div></div>
    </>}
    {compact && <div className="border-b border-cp-border bg-cp-accent-soft p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-base">{captured ? 'Decision captured' : current ? 'Your review is recorded' : 'Your review'}</h2><Badge>VERSION {plan.version}</Badge></div><p className="mt-2 text-xs leading-6">{humanCount} human, {agentCount} agent · {plan.conditions.length} retained conditions. Agent support is not human sign-off.</p><button className="mt-2 inline-flex min-h-9 items-center gap-2 text-xs font-semibold text-cp-accent" onClick={showPlan}>Read proposal, conditions and evidence <ArrowUpRight size={14} /></button></div>}
    {!captured && !readOnly && <form className="concurrence-form p-4 [&_label]:mt-3 [&_select]:w-full [&>.muted]:mt-3 [&>.muted]:text-xs" onSubmit={event => { event.preventDefault(); if (reviewable && !current) void respond('concur'); }}>
      {setRole ? <><label htmlFor="review-role">Review as human specialist</label><select data-testid="review-role" id="review-role" value={role} onChange={event => setRole(event.target.value as Role)}>{ROLES.map(item => <option key={item} value={item}>{ROLE_META[item].person}</option>)}</select></> : <p className="font-mono text-[10px] tracking-wide text-cp-text-soft">REVIEWING AS {ROLE_META[role].person}</p>}
      <label htmlFor="review-comment">Review comment <span className="text-xs text-cp-text-muted">(required to object)</span></label><textarea id="review-comment" value={comment} onChange={event => setComment(event.target.value)} rows={2} placeholder="Record concurrence conditions or an objection..." maxLength={2000} />
      <div className="review-actions mt-3 flex flex-wrap gap-3 [&>button]:min-h-10 [&>button]:flex-1 [&>button]:rounded-xl [&>button]:border [&>button]:px-3 [&>button]:py-2 [&>button]:text-xs [&>button]:font-semibold">{current ? <Badge tone="success"><Check size={15} />Human concurrence recorded</Badge> : <button data-testid={`concur-${role}`} type="submit" className="inline-flex items-center justify-center gap-2 border-cp-accent bg-cp-accent text-cp-accent-fg" disabled={!reviewable}><Check size={15} />Concur</button>}<button data-testid={`object-${role}`} type="button" className="inline-flex items-center justify-center gap-2 border-cp-border bg-cp-surface text-cp-danger" disabled={!reviewable || !comment.trim()} onClick={() => void respond('object')}><Flag size={15} />Object</button></div>
      {!reviewable && !pending && <p className="text-xs leading-6 text-cp-text-muted">Review opens when the chair reaches the concurrence phase.</p>}
    </form>}
        {captured && <div className="capture-stamp mt-5 flex items-center gap-3 text-cp-success [&_strong]:block [&_strong]:text-sm [&_strong]:text-cp-text [&_span]:mt-1 [&_span]:block [&_span]:text-xs [&_span]:text-cp-text-muted"><CheckCheck size={20} /><div><strong>Recorded {time(meeting.closed_at ?? plan.created_at)}</strong><span>Export the full meeting from the toolbar.</span></div></div>}
    {meeting.objections.length > 0 && <details className="plan-objections border-t border-cp-border bg-cp-bg-elevated p-5"><summary><Flag size={15} />Objections & discussion history ({meeting.objections.length})</summary>{meeting.objections.map((objection, index) => <DataFields key={index} data={objection} compact />)}</details>}
  </section>;
}
function Timeline({ meeting }: { meeting: Meeting }) {
  return <section data-testid="meeting-activity" className="panel min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-5 sm:p-6 timeline-panel"><SectionHeading eyebrow="MEETING ACTIVITY LOG" title="Meeting activity" aside={<Badge>{meeting.events.length} recorded steps</Badge>} /><p className="mb-4 text-xs leading-6 text-cp-text-muted">Every review step each specialty takes is recorded here in sequence, newest first.</p>{meeting.events.length ? <ol className="meeting-timeline max-h-[30rem] list-none overflow-y-auto [&>li]:grid [&>li]:grid-cols-[58px_8px_minmax(0,1fr)] [&>li]:gap-3 [&>li]:pb-5 [&_time]:pt-0.5 [&_time]:font-mono [&_time]:text-[11px] [&_time]:text-cp-text-soft [&_strong]:text-sm [&_p]:mt-1.5 [&_p]:break-words [&_p]:text-[13px] [&_p]:leading-6 [&_p]:text-cp-text-muted">{meeting.events.slice(-20).reverse().map(event => { const entry = clinicalActivity({ ...event.payload, type: event.type }, event.role ?? undefined); return <li key={event.id}><time>{time(event.timestamp)}</time><span className={`timeline-node mt-2 size-1.5 rounded-full ${entry.failure ? 'bg-cp-warning' : 'bg-cp-accent'}`} /><div><div className="row flex items-center gap-2 wrap flex-wrap"><strong>{entry.title}</strong>{event.role && <Badge>{ROLE_META[event.role]?.label ?? label(event.role)}</Badge>}</div><p>{eventSummary(event.payload, event.type, event.role ?? undefined)}</p></div></li>; })}</ol> : <Empty>Meeting events will appear as the case activates.</Empty>}</section>;
}
const STANCE_TONE: Record<string, string> = { SUPPORT: 'success', CONDITIONAL: 'warning', UNCERTAIN: 'danger' };
export function ConsensusPanel({ meeting, openRole }: { meeting: Meeting; openRole: (role: Role) => void }) {
  const published = ROLES.filter(role => meeting.roles[role]?.position);
  const counts = { SUPPORT: 0, CONDITIONAL: 0, UNCERTAIN: 0 } as Record<string, number>;
  for (const role of published) counts[meeting.roles[role]!.position!.stance] += 1;
  const revised = published.filter(role => (meeting.roles[role]?.revision ?? 0) > 1);
  const open = meeting.frictions.filter(item => !item.resolved);
  const resolved = meeting.frictions.filter(item => item.resolved);
  const signed = ROLES.filter(role => concurrenceActor(meeting, role));
  const captured = meeting.phase === 'DECISION_CAPTURED';
  const headline = captured ? 'The team reached a recorded decision'
    : meeting.plan ? `${signed.length} of 7 specialties have recorded a review of the proposal`
    : open.length ? `${open.length} question${open.length === 1 ? '' : 's'} still separate the specialties`
    : published.length < ROLES.length ? `${published.length} of 7 specialties have published a position`
    : 'All specialties have published a position';
  return <section data-testid="consensus-panel" className="panel min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-5 sm:p-6 consensus-panel">
    <SectionHeading eyebrow="AGREEMENT ACROSS THE TEAM" title={headline} aside={<Badge tone={captured ? 'success' : open.length ? 'warning' : ''}>{captured ? 'Decision recorded' : `${resolved.length} of ${meeting.frictions.length || 0} questions resolved`}</Badge>} />
    <p className="mb-5 text-[13px] leading-6 text-cp-text-muted">Each specialty reaches its own position first. Where positions conflict, the chair returns only the disputed question to the specialties it involves; revised positions and recorded concurrence are shown below.</p>
    <div className="mb-5 grid gap-3 sm:grid-cols-3 [&>div]:rounded-xl [&>div]:border [&>div]:border-cp-border [&>div]:bg-cp-bg-elevated [&>div]:p-4 [&_strong]:block [&_strong]:text-2xl [&_strong]:font-medium [&_span]:mt-1 [&_span]:block [&_span]:text-[11px] [&_span]:leading-5 [&_span]:text-cp-text-muted">
      <div><strong data-testid="consensus-support">{counts.SUPPORT + counts.CONDITIONAL}</strong><span>specialties support the direction{counts.CONDITIONAL ? `; ${counts.CONDITIONAL} only under stated conditions` : ''}</span></div>
      <div><strong data-testid="consensus-revised">{revised.length}</strong><span>positions revised after the focused discussion</span></div>
      <div><strong data-testid="consensus-signed">{signed.length}</strong><span>reviews recorded against the current proposal version</span></div>
    </div>
    <ol className="consensus-list list-none [&>li]:flex [&>li]:flex-wrap [&>li]:items-center [&>li]:gap-3 [&>li]:border-t [&>li]:border-cp-border [&>li]:py-3 [&>li:first-child]:border-t-0">{ROLES.map(role => {
      const state = meeting.roles[role];
      const stance = state?.position?.stance;
      const actor = concurrenceActor(meeting, role);
      return <li key={role} data-testid={`consensus-${role}`}>
        <button className="min-w-44 border-0! bg-[inherit]! p-0 text-left text-sm font-medium hover:text-cp-accent" onClick={() => openRole(role)}>{ROLE_META[role].label}</button>
        {stance ? <Badge tone={STANCE_TONE[stance] ?? ''}>{statusLabel(stance)}</Badge> : <Badge>Position pending</Badge>}
        {(state?.revision ?? 0) > 1 && <Badge tone="accent">Revised after discussion</Badge>}
        <span className="ml-auto text-right text-[11px] leading-5 text-cp-text-muted">{actor === 'human' ? 'Clinician concurrence recorded' : actor === 'agent' ? 'Auto-concurred under demonstration policy; not human sign-off' : meeting.plan ? 'Awaiting review of the proposal' : stance ? 'Position published for comparison' : 'Review not yet complete'}</span>
      </li>;
    })}</ol>
  </section>;
}
function MeetingSignals({ meeting, inspect }: { meeting: Meeting; inspect: (selection: EvidenceSelection) => void }) {
  const review = ROLES.filter(role => meeting.roles[role]?.position?.autonomy !== 'AUTO' && meeting.roles[role]?.position);
  return <section className="panel min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-5 sm:p-6 signals-panel"><SectionHeading eyebrow="REVIEW STATUS" title="Human review status" /><div className="signal-stat mb-6 flex items-start gap-3 [&>svg]:text-cp-accent [&_strong]:text-sm [&_p]:mt-2 [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><Users size={22} /><div><strong>{review.length} specialist review signal{review.length === 1 ? '' : 's'}</strong><p>{review.length ? review.map(role => ROLE_META[role].label).join(' · ') : 'Review and escalation signals appear with published positions.'}</p></div></div><div className="signal-stat mb-6 flex items-start gap-3 [&>svg]:text-cp-accent [&_strong]:text-sm [&_p]:mt-2 [&_p]:text-xs [&_p]:leading-7 [&_p]:text-cp-text-muted"><ShieldCheck size={22} /><div><strong>{meeting.evidence.length} inspectable sources</strong><p>Access, geography and patient applicability travel with every source.</p></div></div><button data-testid="open-evidence" className="button inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-cp-border px-4 py-2 text-xs font-semibold secondary bg-cp-surface text-cp-text hover:bg-cp-surface-soft" onClick={() => inspect({ ids: [] })}>Open evidence library <ArrowUpRight size={15} /></button><div className="signal-footnote mt-5 flex gap-3 border-t border-cp-border pt-5 text-xs leading-7 text-cp-text-muted"><Sparkles size={17} /><p>Specialist assessments support discussion. Review requirements are demonstration policy, not a substitute for clinical judgment.</p></div></section>;
}
function Chair({ meeting, pending, followup, retry, openRole, clearRoom }: { meeting: Meeting; pending: boolean; followup: () => void; retry: () => void; openRole: (role: Role) => void; clearRoom: () => void }) {
  const errors = ROLES.filter(role => meeting.roles[role]?.error);
  const open = meeting.frictions.filter(item => !item.resolved);
  const captured = meeting.phase === 'DECISION_CAPTURED';
  return <section className="mb-4 min-w-0 rounded-2xl border border-cp-border bg-cp-surface p-4">
    <p className="font-mono text-[10px] tracking-widest text-cp-accent">CHAIR / PROCESS ORCHESTRATION</p><h1 className="mt-2 text-2xl">Chair controls</h1>
    <p role="status" className="my-3 text-sm leading-6">{captured ? 'The decision is on record.' : meeting.busy ? 'Specialist review is running.' : open.length ? `${open.length} questions need focused review.` : meeting.plan ? 'Human review is needed for the proposal.' : 'Collecting specialist perspectives.'}</p>
    <div className="flex flex-wrap gap-2">
      <button className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cp-accent bg-cp-accent px-3 py-2 text-xs font-semibold text-cp-accent-fg" disabled={pending || meeting.busy || !open.length || meeting.phase === 'ERROR' || captured} onClick={followup}><GitBranch size={16} />Request targeted round</button>
      <button className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cp-border px-3 py-2 text-xs" disabled={pending || meeting.busy || (!errors.length && meeting.phase !== 'ERROR')} onClick={retry}><RefreshCw size={16} />Retry specialist review{errors.length ? ` (${errors.length})` : ''}</button>
    </div>
    <div data-testid="room-control" className="mt-4 border-t border-cp-border pt-4">
      <p className="eyebrow mb-2 font-mono text-[10px] leading-relaxed tracking-widest text-cp-text-soft">PARTICIPANT SCREENS</p>
      <p className="mb-3 max-w-2xl text-xs leading-6 text-cp-text-muted">{captured ? 'The decision is recorded and remains exportable. Returning the room to standby clears every participant screen so the next case starts from an empty workspace.' : 'Every participant screen follows this room live. Returning the room to standby clears them all; the meeting record is retained and stays exportable.'}</p>
      <button data-testid="clear-room" className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-cp-border px-3 py-2 text-xs" disabled={pending || meeting.busy} onClick={clearRoom}><Eraser size={16} />Return room to standby</button>
    </div>
    <details className="mt-4 border-t border-cp-border pt-3"><summary>Delegation monitor</summary><p className="mb-3 text-xs leading-6 text-cp-text-muted">The chair coordinates review; it does not decide which treatment is correct.</p>{ROLES.map(role => <button className="flex w-full items-center justify-between gap-2 border-0 border-b border-cp-border py-2 text-left text-xs" onClick={() => openRole(role)} key={role}><span>{ROLE_META[role].label}</span><Status value={meeting.roles[role]?.status ?? 'IDLE'} /><ArrowUpRight size={15} /></button>)}</details>
    <details className="mt-3 border-t border-cp-border pt-3"><summary>Evidence behind the discussion</summary><ChairEvidence meeting={meeting} /></details>
  </section>;
}
function ChairEvidence({ meeting }: { meeting: Meeting }) {
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  return <><EvidenceTable evidence={meeting.evidence} inspect={setSelection} />{selection && <EvidenceDrawer selection={selection} evidence={meeting.evidence} close={() => setSelection(null)} />}</>;
}
