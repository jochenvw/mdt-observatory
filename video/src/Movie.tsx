import React, {type CSSProperties, type ReactNode} from 'react';
import {
  AbsoluteFill, Audio, Easing, Img, interpolate, OffthreadVideo,
  Sequence, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import story from './story.json';
import timing from '../assets/generated/timing.json';
import captions from '../assets/generated/captions.json';
import clips from '../assets/generated/clips.json';
import record from '../assets/generated/record.json';
import './style.css';

export type MovieProps = {captions: boolean; music: boolean};
type Rect = {x: number; y: number; w: number; h: number};
type Scene = typeof story.scenes[number];
type Glyph = 'human' | 'agent' | 'scan' | 'tissue' | 'heart' | 'evidence' | 'tools' | 'check' | 'question' | 'document' | 'arrow';
const BLUE = '#0078d4';
const asset = (file: string) => staticFile(`generated/${file}`);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const ease = Easing.bezier(0.16, 1, 0.3, 1);
const reveal = (f: number, at = 0, duration = 20) => interpolate(f, [at, at + duration], [0, 1], {...clamp, easing: ease});
const useSeconds = () => useCurrentFrame() / useVideoConfig().fps;

function Icon({kind, size = 32, color = 'currentColor'}: {kind: Glyph; size?: number; color?: string}) {
  const shapes: Record<Glyph, ReactNode> = {
    human: <><circle cx="16" cy="9" r="5" /><path d="M5 29v-4a11 11 0 0 1 22 0v4" /></>,
    agent: <><rect x="6" y="6" width="20" height="20" rx="6" /><path d="M12 2v4m8-4v4M12 26v4m8-4v4M2 12h4m-4 8h4m20-8h4m-4 8h4" /><path d="m11 17 4-6 3 10 3-6" /></>,
    scan: <><path d="M3 11V3h8m10 0h8v8M3 21v8h8m10 0h8v-8" /><circle cx="16" cy="16" r="7" /><path d="M10 16h12m-6-6v12" /></>,
    tissue: <><path d="m13 3 9 9-4 4-9-9zM16 14l-5 5m-6-1v5a6 6 0 0 0 6 6h16M22 13a9 9 0 0 1 1 16" /><path d="M9 22h9" /></>,
    heart: <path d="M16 28 4 17C-4 6 9-1 16 9 23-1 36 6 28 17Z" />,
    evidence: <><path d="M16 7C12 3 6 3 2 5v22c5-2 10-2 14 1 4-3 9-3 14-1V5c-4-2-10-2-14 2Z" /><path d="M16 7v21" /></>,
    tools: <><path d="m5 27 13-13m-2-9a9 9 0 0 0 11 11l-5-5 1-6 5 5A9 9 0 0 0 16 5Z" /><circle cx="5" cy="27" r="2" /></>,
    check: <path d="m5 16 7 7L28 7" />,
    question: <><circle cx="16" cy="16" r="13" /><path d="M11 11a5 5 0 0 1 10 0c0 4-5 4-5 8m0 4v1" /></>,
    document: <><path d="M5 2h14l8 8v20H5zM19 2v9h8M10 17h12m-12 5h12" /></>,
    arrow: <path d="M3 16h25m-9-9 9 9-9 9" />,
  };
  return <svg width={size} height={size} viewBox="0 0 32 32" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{shapes[kind]}</svg>;
}

function Enter({children, at = 0, style, className = ''}: {children: ReactNode; at?: number; style?: CSSProperties; className?: string}) {
  const frame = useCurrentFrame();
  const p = reveal(frame, at * 25);
  return <div className={className} style={{opacity: p, transform: `translateY(${(1 - p) * 24}px)`, ...style}}>{children}</div>;
}

function Shot({name, box, crop = {x: 0, y: 0, w: 1920, h: 1080}, zoom = 0.025,
  motion, className = ''}: {name: string; box: Rect; crop?: Rect; zoom?: number; motion?: boolean; className?: string}) {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const scale = Math.max(box.w / crop.w, box.h / crop.h);
  const camera = 1 + Math.min(frame / Math.min(durationInFrames, 500), 1) * zoom;
  const imageStyle: CSSProperties = {
    position: 'absolute', maxWidth: 'none', width: 1920 * scale, height: 1080 * scale,
    left: -crop.x * scale, top: -crop.y * scale,
  };
  return <div className={`shot ${className}`} style={{left: box.x, top: box.y, width: box.w, height: box.h}}>
    <div style={{position: 'absolute', inset: 0, transform: `scale(${camera})`, transformOrigin: '50% 45%'}}>
      {motion ? <OffthreadVideo muted src={asset(`${name}.mp4`)} style={imageStyle} /> :
        <Img src={asset(`${name}.png`)} style={imageStyle} />}
    </div>
  </div>;
}

function Tag({children, tone = 'blue', style}: {children: ReactNode; tone?: 'blue' | 'amber' | 'green' | 'white'; style?: CSSProperties}) {
  return <div className={`tag ${tone}`} style={style}>{children}</div>;
}

function Heading({eyebrow, title, subtitle}: {eyebrow: string; title: string; subtitle?: string}) {
  return <div className="heading">
    <div className="eyebrow">{eyebrow}</div>
    <h1>{title}</h1>
    {subtitle && <p>{subtitle}</p>}
  </div>;
}

function Person({x, y, name, color = BLUE, index = 0, agent = false, scale = 1}:
  {x: number; y: number; name: string; color?: string; index?: number; agent?: boolean; scale?: number}) {
  const frame = useCurrentFrame();
  const p = reveal(frame, index * 6, 20);
  const skin = ['#c98e6b', '#925e46', '#dfb598', '#ad7656', '#e6bd9f'][index % 5];
  const hair = ['#273d51', '#303944', '#674639', '#253446', '#654c3c'][index % 5];
  return <div style={{position: 'absolute', left: x, top: y, width: 210, height: 265,
    transform: `scale(${scale}) translateY(${(1 - p) * 15}px)`, transformOrigin: 'center top', opacity: p}}>
    <svg width="210" height="190" viewBox="0 0 210 190">
      <ellipse cx="106" cy="182" rx="77" ry="7" fill="#0d4474" opacity=".09" />
      <path d="M38 179v-27c0-35 28-55 68-55s67 20 67 55v27" fill={index === 2 ? color : '#ffffff'} stroke="#c7d7e5" strokeWidth="2" />
      <path d="m78 108 28 47 28-47" fill={color} opacity=".9" />
      <path d="m78 108-13 24 22 8-5 39m52-71 13 24-22 8 5 39" fill="none" stroke="#d7e4ee" strokeWidth="2" />
      <path d="M94 86v25q12 15 24 0V86" fill={skin} />
      <ellipse cx="106" cy="60" rx="34" ry="41" fill={skin} />
      <path d={index % 2 === 0 ? 'M73 61C61 7 119 1 139 37l-3 22-13-31c-8 13-27 20-50 15Z' :
        'M70 74V39c0-41 73-40 73 5v38l-11-30c-11-2-24-12-31-23-5 18-19 25-25 24Z'} fill={hair} />
      <path d="M89 61h9m16 0h9" stroke={hair} strokeWidth="3" strokeLinecap="round" />
      <path d="M100 81q6 4 12 0" fill="none" stroke="#895746" strokeWidth="2" strokeLinecap="round" />
      <rect x="49" y="145" width="28" height="19" rx="3" fill="#e4f2ff" />
      <path d="M60 149v10m-5-5h10" stroke={color} strokeWidth="2" />
    </svg>
    <div className="person-name">{name}</div>
    <div className="person-kind">HUMAN SPECIALIST</div>
    {agent && <div className="person-agent" style={{borderColor: `${color}50`, color}}>
      <Icon kind="agent" size={22} /> ROLE AGENT
    </div>}
  </div>;
}

function Room({closing = false}: {closing?: boolean}) {
  const t = useSeconds();
  const zoom = closing ? 1 : interpolate(t, [0, 8, 15], [0.97, 1, 1.06], clamp);
  const activityFrames = Math.floor((clips.find(clip => clip.name === 'activity')?.duration ?? 4) * 25);
  const screen = {x: 505, y: closing ? 355 : 230, w: 915, h: closing ? 340 : 470};
  return <div style={{position: 'absolute', inset: 0, transform: `scale(${zoom})`, transformOrigin: '50% 48%'}}>
    <div className="room-light" />
    {closing ? <Shot name="consensus" box={screen} crop={{x: 240, y: 205, w: 1385, h: 514}} zoom={0.01} /> : <>
      <Sequence durationInFrames={200}><Shot name="central-active" box={screen}
        crop={{x: 0, y: 25, w: 1630, h: 838}} zoom={0.01} /></Sequence>
      <Sequence from={200} durationInFrames={activityFrames}><Shot name="activity" motion box={screen}
        crop={{x: 220, y: 170, w: 1410, h: 725}} zoom={0} /></Sequence>
      <Sequence from={200 + activityFrames}><Shot name="central" box={screen}
        crop={{x: 230, y: 205, w: 1390, h: 715}} zoom={0.01} /></Sequence>
    </>}
    <div className="wall-stand" />
    <div className="meeting-table" />
    <Person x={210} y={505} name="Oncologist" index={0} agent={closing} color="#b43d6f" />
    <Person x={500} y={580} name="Radiologist" index={1} agent={closing} />
    <Person x={850} y={602} name="Chair" index={2} color="#315b87" />
    <Person x={1200} y={580} name="Pathologist" index={3} agent={closing} color="#6750a4" />
    <Person x={1490} y={505} name="Surgeon" index={4} agent={closing} color="#168477" />
    {!closing && <>
      <Enter at={8} style={{position: 'absolute', top: 251, left: 81, width: 292, height: 235, overflow: 'hidden', borderRadius: 16}}>
        <Img src={asset('patient-summary.png')} style={{width: '100%', borderRadius: 16, boxShadow: '0 10px 25px #32577512'}} />
      </Enter>
      {['Imaging', 'Pathology', 'Evidence'].map((text, i) =>
        <Enter key={text} at={8 + i * .65} style={{position: 'absolute', top: 275 + i * 76, left: 1505}}>
          <div className="source-chip"><Icon kind={i === 0 ? 'scan' : 'document'} size={24} />{text}</div>
        </Enter>)}
    </>}
  </div>;
}

function Opening() {
  return <><Heading eyebrow="THE MULTIDISCIPLINARY TUMOUR BOARD" title="Different expertise. One patient." />
    <Room />
    <Tag style={{position: 'absolute', left: 751, top: 859}}>Actual MDT Observatory interface</Tag>
  </>;
}

const roleItems = [
  {human: 'Oncologist', agent: 'Oncology agent', shot: 'oncology', color: '#b43d6f', icon: 'heart' as Glyph},
  {human: 'Radiologist', agent: 'Radiology agent', shot: 'radiology', color: BLUE, icon: 'scan' as Glyph},
  {human: 'Pathologist', agent: 'Pathology agent', shot: 'pathology', color: '#6750a4', icon: 'tissue' as Glyph},
];

function Partners() {
  const t = useSeconds();
  const active = Math.min(2, Math.floor(t / 8));
  return <><Heading eyebrow="ROLE-SPECIFIC SUPPORT" title="A specialist. An agent. A shared task." />
    {roleItems.map((role, i) => <Enter key={role.human} at={i * 1.25} style={{
      position: 'absolute', left: 76, top: 265 + i * 193, width: 557}}>
      <div className={`pair ${active === i ? 'selected' : ''}`} style={{borderColor: active === i ? role.color : '#d9e5f0'}}>
        <div className="pair-human"><Icon kind="human" size={42} color={role.color} /><div><small>HUMAN</small><strong>{role.human}</strong></div></div>
        <div className="pair-link">Steer <span>↔</span> Review</div>
        <div className="pair-agent"><Icon kind="agent" size={34} color={role.color} /><div><small>ROLE AGENT</small><strong>{role.agent}</strong></div></div>
      </div>
    </Enter>)}
    {roleItems.map((role, i) => <Sequence key={role.shot} from={i * 8 * 25} durationInFrames={(i === 2 ? 9 : 8) * 25}>
      <Shot name={role.shot} box={{x: 705, y: 260, w: 1135, h: 583}}
        crop={{x: 240, y: 200, w: 1365, h: 700}} />
      <Tag style={{position: 'absolute', left: 737, top: 858}}>{role.human}'s actual workspace</Tag>
    </Sequence>)}
  </>;
}

function Inside() {
  const frame = useCurrentFrame();
  const layers = [
    {name: 'Model', body: 'Interpret information. Communicate.', icon: 'agent' as Glyph},
    {name: 'Permitted tools', body: 'Read records. Compare findings. Retrieve evidence.', icon: 'tools' as Glyph},
    {name: 'Role + context', body: 'Specialty. Patient case. Shared questions.', icon: 'human' as Glyph},
  ];
  return <><Heading eyebrow="UNDER THE SURFACE" title="What makes an agent useful?" />
    <div className="agent-spine" />
    {layers.map((layer, i) => <Enter key={layer.name} at={i * 1.1} className="agent-layer"
      style={{top: 286 + i * 174, boxShadow: `0 ${18 + i * 3}px 45px #005ba914`,
        transform: `translateX(${Math.sin(frame / 130 + i) * 3}px)`}}>
      <div className="layer-icon"><Icon kind={layer.icon} size={40} /></div>
      <div><small>0{i + 1}</small><h2>{layer.name}</h2><p>{layer.body}</p></div>
    </Enter>)}
    <svg className="connector" style={{left: 819, top: 467, width: 166, height: 105}} viewBox="0 0 166 105">
      <path d="M0 30h112q25 0 25 25v5h25M162 75H52q-25 0-25-25v-5H0" fill="none" stroke="#0078d4" strokeWidth="2" strokeDasharray="6 9" strokeDashoffset={-frame / 2} />
    </svg>
    <Shot name="evidence-access" box={{x: 988, y: 267, w: 851, h: 567}}
      crop={{x: 1210, y: 72, w: 708, h: 472}} zoom={0.006} />
    <Tag style={{position: 'absolute', left: 1020, top: 851}}>Source access and limitations stay visible</Tag>
    <Enter at={15} style={{position: 'absolute', left: 76, top: 844}}>
      <Tag tone="amber">This film: scripted rehearsal, not live inference</Tag>
    </Enter>
  </>;
}

const perspectives = [
  {name: 'Radiology', purpose: 'Imaging and interval change', shot: 'radiology-source', icon: 'scan' as Glyph},
  {name: 'Pathology', purpose: 'Tissue and molecular findings', shot: 'pathology-source', icon: 'tissue' as Glyph},
  {name: 'Oncology', purpose: 'Response and treatment burden', shot: 'oncology-source', icon: 'heart' as Glyph},
  {name: 'Surgery', purpose: 'Anatomy and procedural feasibility', shot: 'surgery-source', icon: 'tools' as Glyph},
  {name: 'Chair', purpose: 'Shared facts and unresolved questions', shot: 'chair', icon: 'human' as Glyph},
];
function Perspectives() {
  const t = useSeconds();
  const cuts = [0, 3, 5, 7.2, 9.3, 15];
  const active = Math.max(0, cuts.slice(0, -1).findLastIndex(at => t >= at));
  return <><Heading eyebrow="THE SAME SYNTHETIC CASE" title="One case. Different working views." />
    <div className="perspective-tabs">{perspectives.map((role, i) =>
      <div className={active === i ? 'active' : ''} key={role.name}>
        <Icon kind={role.icon} size={25} />{role.name}
      </div>)}</div>
    {perspectives.map((role, i) => <Sequence key={role.name} from={Math.round(cuts[i] * 25)}
      durationInFrames={Math.round(cuts[i + 1] * 25) - Math.round(cuts[i] * 25)}>
      <Shot name={role.shot} box={role.name === 'Radiology' ? {x: 315, y: 294, w: 1290, h: 589} : {x: 155, y: 294, w: 1610, h: 589}}
        crop={role.name === 'Chair' ? {x: 230, y: 205, w: 1377, h: 505} :
          role.name === 'Radiology' ? {x: 278, y: 99, w: 1320, h: 604} :
            {x: 270, y: 75, w: 1320, h: 483}} zoom={0.008} />
      <div className="purpose" style={role.name === 'Radiology' ? {left: 345, top: 824, fontSize: 18} : undefined}>
        <Icon kind={role.icon} size={25} />{role.name === 'Radiology' ? 'Illustrative diagram · not acquired clinical imaging' : role.purpose}
      </div>
    </Sequence>)}
  </>;
}

const messages = [
  {role: 'Radiology agent', at: 1.0, text: 'Response is visible. All nine original liver sites still need clearance review.', color: BLUE, icon: 'scan' as Glyph, x: 112, y: 292},
  {role: 'Oncology agent', at: 7.6, text: 'Response alone does not settle the choice between local and systemic treatment.', color: '#b43d6f', icon: 'heart' as Glyph, x: 1039, y: 292},
  {role: 'Surgical perspective', at: 14.9, text: 'Review vessel margins, remaining liver function and the indeterminate lung nodule.', color: '#168477', icon: 'tools' as Glyph, x: 112, y: 547},
  {role: 'Evidence + protocol', at: 21.8, text: 'Treatment evidence has limits. The local pathway is not available for full review.', color: '#8a651c', icon: 'evidence' as Glyph, x: 1039, y: 547},
];
function Conversation() {
  const frame = useCurrentFrame();
  return <><Heading eyebrow="PUBLIC POSITIONS → SHARED QUESTIONS" title="Find the question that matters." />
    <div style={{opacity: .20}}>
      <Shot name="wall" box={{x: 74, y: 232, w: 1772, h: 657}} crop={{x: 220, y: 170, w: 1640, h: 610}} zoom={.04} />
    </div>
    <svg className="connector" viewBox="0 0 1920 1080">
      {messages.map((m, i) => <g key={m.role} opacity={reveal(frame, m.at * 25)}>
        <path d={`M${m.x + (i % 2 ? 0 : 770)} ${m.y + 90} Q960 ${m.y + 90} 960 837`} fill="none" stroke={m.color} strokeWidth="2" opacity=".6" strokeDasharray="7 10" strokeDashoffset={-frame * .8} />
      </g>)}
    </svg>
    {messages.map(m => <Enter key={m.role} at={m.at} className="message" style={{left: m.x, top: m.y, borderTopColor: m.color}}>
      <div className="message-label" style={{color: m.color}}><Icon kind={m.icon} size={29} />{m.role}</div>
      <p>{m.text}</p>
      <small>Public position · editorial paraphrase</small>
    </Enter>)}
    <Enter at={24.5} style={{position: 'absolute', left: 437, top: 811}}>
      <div className="question-bar"><Icon kind="question" size={28} />What must be clarified before a treatment decision?</div>
    </Enter>
  </>;
}

function Judgement() {
  const t = useSeconds();
  const guidanceFrames = Math.floor(Math.min(9.5, clips.find(item => item.name === 'guidance')?.duration ?? 9.5) * 25);
  return <><Heading eyebrow="UNCERTAINTY REQUIRES ATTENTION" title="Bring in human judgement." />
    <div className="human-loop">
      <div className={t < 7 ? 'loop-node focus' : 'loop-node'}><Icon kind="agent" size={48} /><strong>Radiology agent</strong><small>Unresolved question</small></div>
      <div className="loop-arrow">↑ <span>Review &amp; steer</span> ↓</div>
      <div className={t >= 7 ? 'loop-node focus human' : 'loop-node human'}><Icon kind="human" size={48} /><strong>Radiologist</strong><small>Clinical judgement</small></div>
    </div>
    <Sequence from={0} durationInFrames={6 * 25}>
      <Shot name="human-before" box={{x: 642, y: 270, w: 1200, h: 604}}
        crop={{x: 247, y: 195, w: 1360, h: 685}} />
      <Tag tone="amber" style={{position: 'absolute', left: 674, top: 793}}>Unresolved ≠ safe to assume</Tag>
    </Sequence>
    <Sequence from={6 * 25} durationInFrames={guidanceFrames}>
      <Shot name="guidance" motion box={{x: 642, y: 270, w: 1200, h: 604}}
        crop={{x: 918, y: 459, w: 722, h: 364}} zoom={0} />
    </Sequence>
    <Sequence from={6 * 25 + guidanceFrames}>
      <Shot name="human-return" box={{x: 642, y: 270, w: 1200, h: 604}}
        crop={{x: 937, y: 470, w: 690, h: 348}} />
    </Sequence>
    <Enter at={15.5} style={{position: 'absolute', left: 92, top: 799, width: 480}}>
      <Tag tone="green"><Icon kind="check" size={24} />Guidance recorded. Conditions retained.</Tag>
    </Enter>
  </>;
}

function Consensus() {
  const t = useSeconds();
  const people = Object.entries(record.concurrences);
  const shown = Math.min(6, Math.floor(Math.max(0, t - 2) / 1.35));
  return <><Heading eyebrow="VERSION-BOUND REVIEW" title="Review the plan. Preserve the conditions." />
    <Shot name={t < 5 ? 'proposal' : t < 10 ? 'review-radiology' : 'consensus'} box={{x: 76, y: 267, w: 1166, h: 617}}
      crop={t < 5 ? {x: 230, y: 205, w: 1390, h: 735} : t < 10 ?
        {x: 249, y: 195, w: 1360, h: 720} : {x: 240, y: 195, w: 1375, h: 728}} />
    <div className="signoffs">
      <div className="eyebrow">CAPTURED PLAN · VERSION {record.plan.version}</div>
      <h2>{t < 10 ? 'Specialty concurrence' : 'Decision recorded'}</h2>
      {people.map(([role, vote], i) => {
        const complete = i <= shown;
        return <div className="signoff" key={role} style={{opacity: complete ? 1 : .42}}>
          <span className={`vote-dot ${complete ? 'complete' : ''}`}>{complete ? <Icon kind="check" size={18} /> : null}</span>
          <div><strong>{role === 'patient' ? 'Patient perspective' : role}</strong><small>
            {complete ? vote.actor === 'human' ? 'Demo clinician input' : 'Automatic demo policy' : 'Awaiting review'}
          </small></div>
        </div>;
      })}
      <div className="retained">Agreement retains the clinical conditions.</div>
    </div>
    <Enter at={10} style={{position: 'absolute', left: 113, top: 815}}>
      <Tag tone="green"><Icon kind="check" size={24} />Required review completed for this version</Tag>
    </Enter>
  </>;
}

function DocumentIllustration({patient, language = 'en'}: {patient: boolean; language?: 'en' | 'de'}) {
  const german = language === 'de';
  return <div className={`document-illustration ${patient ? 'patient-doc' : ''}`}>
    <div className="doc-top"><Icon kind={patient ? 'heart' : 'document'} size={34} />
      <span>{patient ? 'PATIENT EXPLANATION' : 'COLLEAGUE LETTER'}</span></div>
    <Tag tone="amber">Illustrative excerpt · not an approved document</Tag>
    <h2>{patient ? german ? 'Was als Nächstes wichtig ist' : 'What needs to happen next' : 'MDT outcome and next steps'}</h2>
    <p>{patient ?
      german ? 'Die Behandlung hat die Veränderungen in Ihrer Leber verkleinert. Ihr Team muss noch prüfen, welche Behandlung als Nächstes für Sie geeignet ist.' :
        'Treatment has reduced the areas of cancer in your liver. Your team still needs to check which treatment is suitable for you next.' :
      'Complete diagnostic and specialist review before a treatment decision. Review all nine original liver sites, vascular margins and the indeterminate lung nodule.'}</p>
    <div className="doc-rule" />
    <p className="doc-note">{patient ?
      german ? 'Besprechen Sie die offenen Fragen und Ihre Wünsche mit Ihrem Behandlungsteam.' :
        'Discuss the remaining questions and your priorities with your care team.' :
      'Compare the management alternatives with the patient. Retain the conditions and evidence limitations recorded in the plan.'}</p>
    <div className="doc-approval"><Icon kind="human" size={22} />{german ? 'Vor der Weitergabe ärztlich prüfen' : 'Named clinician review before sharing'}</div>
  </div>;
}

function Action() {
  const t = useSeconds();
  return <><Heading eyebrow="FROM RECORDED OUTCOME TO COMMUNICATION" title="Carry the decision into care." />
    <Sequence from={0} durationInFrames={6 * 25}>
      <Shot name="outcome" box={{x: 77, y: 253, w: 1766, h: 648}}
        crop={{x: 242, y: 250, w: 1370, h: 503}} />
    </Sequence>
    <Sequence from={6 * 25} durationInFrames={6 * 25}>
      <Shot name="documents-status" box={{x: 77, y: 253, w: 1766, h: 648}}
        crop={{x: 230, y: 554, w: 1390, h: 510}} zoom={0.008} />
      <Tag tone="amber" style={{position: 'absolute', left: 112, top: 824}}>
        Local capture: drafting unavailable. The application reports the failure.
      </Tag>
    </Sequence>
    <Sequence from={12 * 25}>
      <Enter className="doc-layout"><DocumentIllustration patient={false} />
        <DocumentIllustration patient language={t < 21 ? 'en' : 'de'} /></Enter>
      <div className="languages">
        {['English', 'Deutsch', 'Italiano', 'Nederlands'].map((label, i) =>
          <div key={label} className={(t < 21 ? i === 0 : i === 1) ? 'active' : ''}>{label}</div>)}
        <span>Language illustration · this case records English</span>
      </div>
    </Sequence>
  </>;
}

function Closing() {
  const t = useSeconds();
  return <><Room closing />
    <div className="closing-title">
      <div className="eyebrow">MDT OBSERVATORY</div>
      <h1>More time for<br /><span>clinical judgement.</span></h1>
      <div className="closing-line">Agents prepare and coordinate. Clinicians make the decision.</div>
    </div>
    <div className="event-title" style={{opacity: reveal(t * 25, 250, 30)}}>
      Oncology Hackathon 2026 · Munich
    </div>
  </>;
}

const scenes: Record<string, React.FC> = {
  room: Opening, partners: Partners, inside: Inside, perspectives: Perspectives,
  conversation: Conversation, judgement: Judgement, consensus: Consensus,
  action: Action, close: Closing,
};

function SceneFrame({scene, index}: {scene: Scene; index: number}) {
  const Content = scenes[scene.id];
  return <AbsoluteFill>
    <Content />
    <div className="chapter"><span>{String(index + 1).padStart(2, '0')}</span> / 09</div>
  </AbsoluteFill>;
}

export const Movie: React.FC<MovieProps> = ({captions: showCaptions, music}) => {
  const frame = useCurrentFrame();
  const t = frame / story.fps;
  const caption = captions.find(cue => t >= cue.start && t < cue.end);
  return <AbsoluteFill className="film">
    <div className="background-glow" />
    <div className="brand"><span className="brand-symbol"><i /><i /><i /><i /></span>MDT OBSERVATORY</div>
    {story.scenes.map((scene, index) => <Sequence key={scene.id} from={scene.from * story.fps}
      durationInFrames={scene.duration * story.fps} name={scene.title}>
      <SceneFrame scene={scene} index={index} />
    </Sequence>)}
    {timing.map(cue => cue.file && <Sequence key={cue.id} from={Math.round(cue.start * story.fps)}
      durationInFrames={Math.ceil(cue.duration * story.fps)}>
      <Audio src={asset(cue.file)} volume={0.94} />
    </Sequence>)}
    {music && <Audio src={asset('ambient.wav')} volume={0.5} />}
    {showCaptions && caption && <div className="captions"><span>{caption.text}</span></div>}
    <footer><span>SYNTHETIC CASE · SCRIPTED REHEARSAL · NOT FOR CLINICAL USE</span>
      <span>Human judgement remains essential</span></footer>
    <div className="progress" style={{width: `${frame / (story.duration * story.fps - 1) * 100}%`}} />
  </AbsoluteFill>;
};
