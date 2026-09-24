import { useMemo, useRef, useState } from 'react';
import { Mic, Pause, Play, RotateCcw, SkipForward, Square, Volume2, VolumeX } from 'lucide-react';
import { label, time } from './helpers';
import { Badge, Empty, ROLE_META } from './ui';
import { ROLES } from './types';
import type { Evidence, Meeting, Role, VoiceContributionInput, VoiceSettings, VoiceTurn } from './types';

type PlaybackState = 'idle' | 'playing' | 'paused' | 'failed';
type MicState = 'idle' | 'permission-needed' | 'recording' | 'processing' | 'denied' | 'failed';
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<{ 0: { transcript: string }; isFinal?: boolean }>;
}
declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const ROLE_TO_AGENT: Record<Role, string> = {
  oncology: 'oncology',
  radiology: 'radiology',
  pathology: 'pathology',
  surgery: 'surgery',
  protocol: 'radiation_oncology',
  patient: 'specialist_nurse',
  research: 'clinical_trial',
};

function roleForAgent(agentKey: string): Role | undefined {
  return ROLES.find(role => ROLE_TO_AGENT[role] === agentKey);
}

function caseQuestion(meeting: Meeting): string {
  const patient = String(meeting.case.pseudonym ?? 'the synthetic patient');
  const question = String(meeting.case.question ?? 'the MDT decision question');
  return `${patient}: ${question}`;
}

export function buildVoiceTurns(meeting: Meeting, detail: 'concise' | 'detailed'): VoiceTurn[] {
  const turns: VoiceTurn[] = [{
    id: 'chair-introduction',
    sequence: 1,
    agent_key: 'chair',
    speaker: 'MDO chair',
    category: 'chair',
    text: `This is a synthetic voice-enabled MDO rehearsal. The decision question is ${caseQuestion(meeting)}`,
    evidence_ids: [],
    timestamp_offset_seconds: 0,
  }];
  let sequence = 2;
  for (const role of ROLES) {
    const position = meeting.roles[role]?.position;
    if (!position) continue;
    const extra = detail === 'detailed' && position.uncertainties.length ? ` Unresolved points: ${position.uncertainties.slice(0, 3).join('; ')}` : '';
    turns.push({
      id: `${ROLE_TO_AGENT[role]}-assessment`,
      sequence,
      agent_key: ROLE_TO_AGENT[role],
      speaker: role === 'protocol' ? 'Radiation oncologist' : role === 'patient' ? 'Specialist nurse' : role === 'research' ? 'Clinical-trial specialist' : ROLE_META[role].person,
      category: 'specialist',
      text: `${position.position} Recommendation: ${position.recommendation}.${extra}`,
      evidence_ids: position.claims.slice(0, 3).flatMap(claim => claim.evidence_ids.slice(0, 3)),
      timestamp_offset_seconds: (sequence - 1) * 30,
    });
    sequence += 1;
  }
  const unresolved = meeting.frictions.filter(item => !item.resolved).map(item => item.question);
  turns.push({
    id: 'chair-final-summary',
    sequence,
    agent_key: 'chair',
    speaker: 'MDO chair',
    category: 'chair',
    text: unresolved.length
      ? `Agreement, disagreement and uncertainty remain visible. Unresolved questions: ${unresolved.slice(0, 3).join('; ')}`
      : `The spoken summary reflects the current proposal, but human review remains required. ${meeting.plan?.summary ?? ''}`,
    evidence_ids: meeting.plan?.evidence_ids ?? [],
    timestamp_offset_seconds: (sequence - 1) * 30,
  });
  turns.push({
    id: 'human-decision-checkpoint',
    sequence: sequence + 1,
    agent_key: 'chair',
    speaker: 'Human decision checkpoint',
    category: 'checkpoint',
    text: 'The discussion stops here. Voice contributions and transcripts are not approved clinical decisions without explicit confirmation in the existing human workflow.',
    evidence_ids: [],
    timestamp_offset_seconds: sequence * 30,
  });
  return turns;
}

export function agentRouteHint(text: string): string {
  const normalized = text.toLowerCase();
  const role = ROLES.find(item => normalized.includes(item) || normalized.includes(ROLE_META[item].person.toLowerCase()));
  return role ? ROLE_TO_AGENT[role] : 'chair';
}

export function VoiceMdoPanel({
  meeting, voice, evidence, inspect, submitContribution,
}: {
  meeting: Meeting;
  voice?: VoiceSettings;
  evidence: Evidence[];
  inspect: (selection: { ids: string[]; claim?: string }) => void;
  submitContribution: (body: VoiceContributionInput) => Promise<boolean>;
}) {
  const [detail, setDetail] = useState<'concise' | 'detailed'>('concise');
  const turns = useMemo(() => buildVoiceTurns(meeting, detail), [meeting, detail]);
  const [selectedAgent, setSelectedAgent] = useState(voice?.agents.find(agent => agent.role)?.key ?? 'oncology');
  const [activeIndex, setActiveIndex] = useState(0);
  const [playback, setPlayback] = useState<PlaybackState>('idle');
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [micState, setMicState] = useState<MicState>('permission-needed');
  const [confirmationMode, setConfirmationMode] = useState(true);
  const [transcript, setTranscript] = useState('');
  const [corrected, setCorrected] = useState('');
  const [addressedTo, setAddressedTo] = useState('');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const activeTurn = turns[Math.min(activeIndex, turns.length - 1)];
  const selectedRole = roleForAgent(selectedAgent);
  const selectedTurn = selectedRole ? turns.find(turn => turn.agent_key === selectedAgent) : undefined;

  const stopSpeaking = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    window.speechSynthesis?.cancel();
    setPlayback('idle');
  };
  const speakWithBrowser = (turn: VoiceTurn) => {
    if (!('speechSynthesis' in window)) { setPlayback('failed'); return; }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(turn.text);
    utterance.rate = speed;
    utterance.volume = muted ? 0 : 1;
    utterance.onend = () => setPlayback('idle');
    utterance.onerror = () => setPlayback('failed');
    window.speechSynthesis.speak(utterance);
    setPlayback('playing');
  };
  const playTurn = async (turn: VoiceTurn) => {
    stopSpeaking();
    setActiveIndex(turns.findIndex(item => item.id === turn.id));
    if (muted) { setPlayback('paused'); return; }
    try {
      if (!voice?.api_key_configured) throw new Error('ElevenLabs not configured');
      const response = await fetch('/api/voice/speech', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_key: turn.agent_key, text: turn.text }),
      });
      if (!response.ok) throw new Error(`Speech generation failed (${response.status})`);
      const audio = new Audio(URL.createObjectURL(await response.blob()));
      audio.playbackRate = speed;
      audio.muted = muted;
      audio.onended = () => setPlayback('idle');
      audio.onerror = () => { setPlayback('failed'); speakWithBrowser(turn); };
      audioRef.current = audio;
      await audio.play();
      setPlayback('playing');
    } catch {
      speakWithBrowser(turn);
    }
  };
  const pause = () => {
    audioRef.current?.pause();
    window.speechSynthesis?.pause();
    setPlayback('paused');
  };
  const resume = () => {
    if (audioRef.current) void audioRef.current.play();
    window.speechSynthesis?.resume();
    setPlayback('playing');
  };
  const skip = () => {
    stopSpeaking();
    setActiveIndex(index => Math.min(index + 1, turns.length - 1));
  };
  const startMic = () => {
    pause();
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) { setMicState('failed'); return; }
    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-GB';
    recognition.onresult = event => {
      const text = Array.from(event.results).map(result => result[0].transcript).join(' ').trim();
      setTranscript(text);
      setCorrected(current => current || text);
      setAddressedTo(current => current || agentRouteHint(text));
      setMicState('processing');
    };
    recognition.onerror = event => setMicState(event.error === 'not-allowed' ? 'denied' : 'failed');
    recognition.onend = () => setMicState(state => state === 'recording' ? 'processing' : state);
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setMicState('recording');
    } catch {
      setMicState('failed');
    }
  };
  const submitTranscript = async () => {
    const confirmed = (confirmationMode ? corrected : transcript).trim();
    if (!confirmed) return;
    const ok = await submitContribution({
      transcript,
      corrected_transcript: confirmationMode ? confirmed : null,
      addressed_to: addressedTo || null,
      confirmation_mode: confirmationMode,
    });
    if (ok) {
      setTranscript('');
      setCorrected('');
      setAddressedTo('');
      setMicState('permission-needed');
    }
  };

  return <section data-testid="voice-mdo-panel" className="voice-panel my-5 rounded-2xl border border-cp-border bg-cp-surface p-4">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="eyebrow">LISTEN TO MDO</p>
        <h2 className="text-xl">Voice-enabled multidisciplinary discussion</h2>
        <p className="mt-2 max-w-3xl text-xs leading-6 text-cp-text-muted">{voice?.external_processing_disclosure ?? 'Voice playback falls back to browser speech synthesis.'}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge tone={voice?.api_key_configured ? 'success' : 'warning'}>{voice?.api_key_configured ? 'ElevenLabs configured' : 'Browser voice fallback'}</Badge>
        <Badge>Captions always on</Badge>
        <Badge>{evidence.length} evidence sources available</Badge>
      </div>
    </div>
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button className="button" onClick={() => void playTurn(activeTurn)}><Play size={15} />Listen to the MDO</button>
          <button className="button secondary" onClick={() => selectedTurn && void playTurn(selectedTurn)}>Play selected agent</button>
          <button className="icon-button" aria-label="Pause spoken MDO" onClick={pause}><Pause size={16} /></button>
          <button className="icon-button" aria-label="Resume spoken MDO" onClick={resume}><Play size={16} /></button>
          <button className="icon-button" aria-label="Replay current speaker" onClick={() => void playTurn(activeTurn)}><RotateCcw size={16} /></button>
          <button className="icon-button" aria-label="Skip current speaker" onClick={skip}><SkipForward size={16} /></button>
          <button className="button danger" onClick={stopSpeaking}><Square size={15} />Stop speaking</button>
          <button className="icon-button" aria-label={muted ? 'Unmute voice playback' : 'Mute voice playback'} aria-pressed={muted} onClick={() => setMuted(value => !value)}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
        </div>
        <div className="mb-4 flex flex-wrap gap-2 text-xs">
          <label>Discussion detail <select value={detail} onChange={event => setDetail(event.target.value as 'concise' | 'detailed')}><option value="concise">Concise</option><option value="detailed">Detailed</option></select></label>
          <label>Agent <select value={selectedAgent} onChange={event => setSelectedAgent(event.target.value)}>{voice?.agents.map(agent => <option key={agent.key} value={agent.key}>{agent.label}</option>)}</select></label>
          <label>Speed <select value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value={0.75}>0.75×</option><option value={1}>1×</option><option value={1.25}>1.25×</option><option value={1.5}>1.5×</option></select></label>
          <button className="text-button" onClick={() => setActiveIndex(Math.max(0, turns.findIndex(turn => turn.id === 'chair-final-summary')))}>Jump to chair final summary</button>
          <button className="text-button" onClick={() => void playTurn(activeTurn)}>Regenerate failed audio</button>
        </div>
        <div className="rounded-xl border border-cp-border bg-cp-bg-elevated p-4" aria-live="polite">
          <div className="mb-2 flex flex-wrap items-center gap-2"><Badge tone={playback === 'failed' ? 'danger' : playback === 'playing' ? 'accent' : ''}>{label(playback)}</Badge><strong>{activeTurn.speaker}</strong></div>
          <p className="text-sm leading-7">{activeTurn.text}</p>
          {activeTurn.evidence_ids.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{activeTurn.evidence_ids.map(id => <button key={id} className="text-button" onClick={() => inspect({ ids: [id], claim: activeTurn.text })}>Evidence {id}</button>)}</div>}
        </div>
        <ol className="mt-4 space-y-2" aria-label="Live transcript with speaker names and timestamps">
          {turns.map((turn, index) => <li key={turn.id}><button className={`w-full rounded-lg border p-3 text-left text-xs leading-6 ${index === activeIndex ? 'border-cp-highlight bg-cp-accent-soft' : 'border-cp-border bg-cp-surface'}`} onClick={() => setActiveIndex(index)}><span className="mb-1 flex items-center justify-between gap-2"><strong>{time(new Date(Date.now() + turn.timestamp_offset_seconds * 1000).toISOString())} · {turn.speaker}</strong><span>{turn.category}</span></span>{turn.text}{turn.evidence_ids.length > 0 && <span className="mt-2 block text-cp-accent">Evidence {turn.evidence_ids.join(', ')}</span>}</button></li>)}
        </ol>
      </div>
      <aside className="min-w-0 rounded-xl border border-cp-border bg-cp-bg-elevated p-4">
        <div className="mb-3 flex items-center justify-between gap-3"><div><p className="eyebrow">JOIN DISCUSSION</p><h3>Microphone participation</h3></div><Badge tone={micState === 'denied' || micState === 'failed' ? 'danger' : micState === 'recording' ? 'accent' : ''}>{label(micState)}</Badge></div>
        <p className="mb-3 text-xs leading-6 text-cp-text-muted">Consent is required before recording or transcription. When you begin speaking, current playback is paused and preserved.</p>
        <div className="mb-3 flex flex-wrap gap-2">
          <button className="button" onClick={startMic}><Mic size={15} />Join discussion</button>
          <button className="button secondary" onMouseDown={startMic} onMouseUp={() => recognitionRef.current?.stop()} onKeyDown={event => { if (event.key === ' ') startMic(); }} onKeyUp={event => { if (event.key === ' ') recognitionRef.current?.stop(); }}>Push-to-talk</button>
          <button className="button secondary" onClick={() => recognitionRef.current?.stop()}>Mute microphone</button>
        </div>
        {micState === 'denied' && <div className="alert">Microphone access was denied. Use the text correction box to add a confirmed contribution instead.</div>}
        <label className="mb-2 flex items-center gap-2 text-xs"><input type="checkbox" checked={confirmationMode} onChange={event => setConfirmationMode(event.target.checked)} />Confirm and edit transcription before submission</label>
        <label className="mt-3 block text-xs">Speech-to-text transcription<textarea className="mt-1 w-full" value={transcript} onChange={event => { setTranscript(event.target.value); setCorrected(current => current || event.target.value); }} placeholder="Transcribed human speech appears here" /></label>
        {confirmationMode && <label className="mt-3 block text-xs">Corrected transcript<textarea className="mt-1 w-full" value={corrected} onChange={event => setCorrected(event.target.value)} placeholder="Review and correct before submitting" /></label>}
        <label className="mt-3 block text-xs">Address chair or specialist<input className="mt-1 w-full" value={addressedTo} onChange={event => setAddressedTo(event.target.value)} placeholder="chair, radiologist, surgeon..." /></label>
        <button className="button mt-3" disabled={!(confirmationMode ? corrected : transcript).trim()} onClick={() => void submitTranscript()}>Submit confirmed contribution</button>
        {turns.length === 0 && <Empty>Transcript sections appear after specialist positions are published.</Empty>}
      </aside>
    </div>
  </section>;
}
