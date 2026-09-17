"""Packaged fictional CRC case and independently reviewed, access-labelled sources."""

import json
from importlib.resources import files
from typing import Any, Literal

from mdt.models import Evidence, Memory, Role

_PACK = json.loads(files("mdt").joinpath("dossiers", "crc_case.json").read_text(encoding="utf-8"))
_D = _PACK["dossier"]

CASE: dict[str, Any] = {
    "id": _D["case"]["case_id"],
    "demo": True,
    "patient": "CRC case · 59-year-old woman",
    "pseudonym": "CRC-2026-001",
    "age": _D["patient"]["age"],
    "diagnosis": (
        "BRAF V600E / pMMR-MSS ascending-colon adenocarcinoma with bilobar liver metastases"
    ),
    "stage": "cT3 cN1b cM1a · Stage IVA; 5 mm lung nodule remains indeterminate",
    "history": [
        "Fictional case for MDT rehearsal; no real patient records or clinical imaging.",
        "Nine initially unresectable bilobar liver metastases; baseline major-resection FLR 23%.",
        "Controlled hypertension and type 2 diabetes; ECOG 1, G8 16/17.",
        "Nonobstructing ascending-colon primary; no urgent colectomy indication.",
    ],
    "biomarkers": {
        "BRAF": "V600E (tissue VAF 34.6%)",
        "MMR / MSI": "pMMR / MSS",
        "RAS": "KRAS / NRAS wild type",
        "HER2": "IHC 1+, no ERBB2 amplification",
        "CEA": "216 → 31.6 µg/L",
        "ctDNA BRAF VAF": "11.8% → 0.42%; persistent detection",
    },
    "performance_status": "ECOG 1",
    "treatment": "Four cycles encorafenib + cetuximab + mFOLFOX6; CT partial response",
    "previous_treatment": "Cycles on 6 July, 20 July, 3 August and 17 August 2026",
    "question": _D["case"]["primary_mdt_question"].strip(),
    "imaging": _PACK["lesion_mapping"],
    "disclaimer": "FICTIONAL MDT DEMONSTRATION — NOT FOR CLINICAL USE",
    **_PACK,
}

ROLE_LABELS: dict[Role, str] = {
    Role.RADIOLOGY: "Radiologist",
    Role.ONCOLOGY: "Medical oncologist",
    Role.SURGERY: "HPB / colorectal surgeon",
    Role.PATHOLOGY: "Pathologist",
    Role.RESEARCH: "Evidence researcher",
    Role.PROTOCOL: "Protocol / guideline specialist",
    Role.PATIENT: "Patient perspective",
}

RESIDUAL_CONDITIONS = [
    "Map and review clearance of all nine baseline liver sites, including S5/S2/S4b "
    "without a source-assigned treatment; disappearing lesions need intraoperative ultrasound.",
    "Vascular margins remain uncertain: S1 is 3 mm from the IVC and S4a 2 mm from the MHV; "
    "review ablation margin, heat-sink, access and venous drainage.",
    "Future liver remnant was 23% for baseline major resection; >65% is predicted only "
    "if the parenchymal-sparing strategy is feasible, not measured postoperative function.",
    "The stable 5 mm lung nodule remains indeterminate and below reliable PET resolution; "
    "repeat thin-section chest CT and human review, not assumed benignity.",
    "Persistent ctDNA BRAF VAF 0.42% indicates detectable disease; no validated binary "
    "ctDNA veto for conversion surgery follows from stage III prognostic evidence.",
    "Perioperative interruption/restart, oxaliplatin toxicity, colectomy sequencing and "
    "limited perioperative evidence after BRAF/EGFR induction require human review.",
]

ROLE_CONTEXTS: dict[Role, dict[str, Any]] = {
    Role.RADIOLOGY: {
        "workspace": "Nine-site liver mapping and chest review",
        "imaging": CASE["imaging"],
        "measurements": CASE["lesion_mapping"],
        "acquisition": _D["imaging"],
        "response": _D["response_assessment"],
        "current_report": _D["response_assessment"]["liver_MRI"]["radiology_conclusion"],
        "comparison_caveat": RESIDUAL_CONDITIONS[:4],
        "question": "Can all nine original sites be mapped and safely cleared, with vessels, "
        "remnant and the indeterminate lung nodule explicitly reviewed?",
    },
    Role.ONCOLOGY: {
        "workspace": "BRAF-directed response, sequencing and toxicity",
        "biomarkers": CASE["biomarkers"],
        "performance_status": CASE["performance_status"],
        "treatment": _D["prior_cancer_treatment"],
        "laboratory_results": _D["post_cycle_4_labs"],
        "baseline_laboratory_results": _D["baseline_laboratory_results"],
        "tumor_markers": _D["tumor_markers"],
        "baseline_ctDNA": _D["baseline_ctDNA"],
        "response_biomarkers": _D["response_assessment"]["biomarkers"],
        "pharmacogenomics": _D["pharmacogenomics"],
        "baseline_medications": _D["baseline_medications"],
        "question": "Interrupt after four cycles for conditional clearance review, or continue "
        "two to four cycles while balancing toxicity and the possible treatment window?",
    },
    Role.SURGERY: {
        "workspace": "Complete clearance and colorectal sequencing",
        "anatomy": CASE["lesion_mapping"],
        "reserve": _D["response_assessment"]["liver_MRI"]["volumetry"],
        "risk": RESIDUAL_CONDITIONS,
        "resectability_review": _D["current_resectability_review"],
        "consult_perspectives": [
            item for item in CASE["specialty_contributions"]
            if any(name in item["specialty"] for name in (
                "Hepatobiliary", "Colorectal", "Interventional", "Radiation"
            ))
        ],
        "consult_boundary": "HPB, colorectal, interventional radiology and radiation oncology "
        "are consultation perspectives within one surgery role, not separate human votes.",
        "question": "Can every original site be cleared safely with adequate remnant, and "
        "which liver-first, synchronous or staged sequence merits human discussion?",
    },
    Role.PATHOLOGY: {
        "workspace": "Colorectal tissue and molecular findings",
        "specimen": _D["pathology"],
        "biomarkers": _D["molecular_profile"],
        "pharmacogenomics": _D["pharmacogenomics"],
        "differentials": _D["differential_diagnoses"],
        "limits": "Superficial biopsy cannot assess lymphovascular/perineural invasion reliably "
        "or prove liver clearance. Preserve future resection tissue for response assessment.",
        "question": "What does pMMR/MSS BRAF V600E tissue establish, and which findings "
        "need hepatic pathology or molecular reassessment if progression is unexpected?",
    },
    Role.RESEARCH: {
        "workspace": "BREAKWATER / CAIRO5 / PROVENC3 applicability",
        "patient_profile": {
            "age": CASE["age"], "stage": CASE["stage"], "biomarkers": CASE["biomarkers"],
            "treatment": CASE["treatment"],
        },
        "source_order": ["NL guidance", "EU guidance / regulation", "International publications"],
        "management_alternatives": CASE["management_alternatives"],
        "trap": "Systemic efficacy, conversion assessment and stage III ctDNA prognosis are "
        "different evidence settings; no combined randomized perioperative answer is supplied.",
        "question": "Which conditional limits apply when comparing BREAKWATER systemic efficacy, "
        "CAIRO5 conversion assessment and PROVENC3 stage III ctDNA prognosis?",
    },
    Role.PROTOCOL: {
        "workspace": "Dutch/EU context and perioperative access gaps",
        "jurisdiction": "Netherlands / European Union",
        "trial": "BREAKWATER / CAIRO5 / PROVENC3 and Dutch BOM advice: separately curated "
        "sources; original CAIRO5 abstract only, other records full text",
        "institutional_protocol": "PROTOCOL_NOT_PUBLIC: local perioperative pathway, "
        "treatment interruptions/restarts and approval criteria are not supplied.",
        "question": "Which current Dutch/EU guidance, regulatory indications, full protocols and "
        "local perioperative sequencing rules need independent access and clinician review?",
    },
    Role.PATIENT: {
        "workspace": "Goals, independence and supportive care",
        "stated_priorities": _D["patient"]["goals"],
        "support": _D["patient"]["living_situation"],
        "symptoms": _D["presenting_history"],
        "treatment_toxicity": _D["prior_cancer_treatment"]["maximum_toxicities"],
        "supportive_care": CASE["specialty_contributions"][-1],
        "question": "How does the patient weigh potentially curative but uncertain local "
        "treatment against operative burden, independence and avoiding a permanent stoma?",
    },
}


def _record(role: Role, passage: str) -> Evidence:
    return Evidence(
        id=f"CASE-CRC-{role.value.upper()}",
        title=f"CRC case record: {ROLE_LABELS[role]}",
        url=f"case://{CASE['id']}/{role.value}",
        date="2026-09-16",
        authority="Fictional case dossier supplied for MDT demonstration",
        region="NL",
        kind="CASE_RECORD",
        access="PUBLIC_FULL_TEXT",
        patient_match="HIGH",
        passage=passage,
        limitations=["Fictional case data, not external medical evidence or clinical imaging."],
        scrutiny={"source_authority": "Supplied case.md", "study_type": "Not a study",
                  "patient_relevance": "Only this demonstration case"},
        synthetic=True,
    )


def _trial(
    identifier: str, title: str, passage: str, population: str,
    match: Literal["HIGH", "PARTIAL", "LOW"],
    *,
    url: str,
    authority: str,
    publication: str,
    doi: str = "",
    access: Literal["PUBLIC_FULL_TEXT", "PUBLIC_ABSTRACT_ONLY"] = "PUBLIC_FULL_TEXT",
    kind: str = "RCT",
    region: Literal["NL", "EU", "INTERNATIONAL", "US"] = "INTERNATIONAL",
    scrutiny: dict[str, str] | None = None,
) -> Evidence:
    return Evidence(
        id=identifier,
        title=title,
        url=url,
        date="2026-09-17",
        authority=authority,
        region=region,
        kind=kind,
        access=access,
        patient_match=match,
        passage=f"Curated paraphrase of independently reviewed source: {passage}",
        limitations=[
            "Original CAIRO5 is abstract-only; other source records were read in full. "
            "Article access does not establish review of every protocol, supplement or amendment.",
            "Date is independent source review/access date, not publication or simulation date.",
            "No individualized benefit, perioperative recommendation or ctDNA veto established.",
        ],
        scrutiny={
            "population": population,
            "source_authority": authority,
            "verification": "Independent research review on 2026-09-17; not a runtime lookup",
            "access_scope": "Abstract only" if access == "PUBLIC_ABSTRACT_ONLY" else "Full text",
            "publication_date": publication,
            "doi": doi or "Not applicable to this guidance page",
            "study_type": kind,
            "sample_size": "Not extracted in this compact curation",
            "endpoints": "Setting-specific outcomes, not a combined conversion pathway",
            "absolute_effect": "Not independently extracted",
            "relative_effect": "Not independently extracted",
            "confidence_intervals": "Not independently extracted",
            "follow_up": "Not extracted in this compact curation",
            "prespecified": "Do not infer protocol/amendment review from article access",
            "funding": "Not extracted in this compact curation",
            "geographic_relevance": "Does not replace Dutch/EU guidance or local approval",
            "patient_relevance": population,
            **(scrutiny or {}),
        },
    )


EVIDENCE: list[Evidence] = [
    _record(Role.RADIOLOGY, "Nine bilobar sites remain visible after response: "
            + "; ".join(f"{row['site']} {row['baseline_mm']} → {row['response_mm']} mm"
                        for row in CASE["lesion_mapping"])
            + ". S1-IVC 3 mm; S4a-MHV 2 mm. Stable 5 mm lung nodule is below PET resolution."),
    _record(Role.ONCOLOGY, "Four cycles encorafenib/cetuximab/mFOLFOX6; CT partial response. "
            "CEA 216 → 31.6; BRAF ctDNA VAF 11.8% → 0.42%, still detectable. "
            "Grade 2 rash/hypomagnesemia, grade 1 neuropathy; magnesium 0.61 mmol/L. "
            "Marker dates differ between tumor_markers and response biomarkers; retain both."),
    _record(Role.SURGERY, "Baseline major-resection FLR 23%; predicted parenchymal-sparing "
            "remnant >65%. Potential complete clearance is conditional on all nine original "
            "sites, vascular margins and expert review. Source leaves S5/S2/S4b treatment "
            "unallocated. Nonobstructing primary permits liver-first/synchronous/staged debate."),
    _record(Role.PATHOLOGY, "Ascending-colon biopsy: moderately/poorly differentiated colorectal "
            "adenocarcinoma, CK20/CDX2/SATB2 positive; pMMR/MSS, BRAF V600E tissue VAF 34.6%, "
            "APC 41.2%, TP53 28.7%, SMAD4 18.4%; RAS wild type, HER2 IHC 1+."),
    _record(Role.RESEARCH, "59-year-old woman with BRAF V600E/MSS ascending-colon cancer, "
            "nine initially unresectable liver metastases after four cycles of BRAF/EGFR-directed "
            "induction. CT response is not proof of cure; ctDNA 0.42%, lung nodule unresolved."),
    _record(Role.PROTOCOL, "PROTOCOL_NOT_PUBLIC: no local perioperative pathway or verified "
            "full trial protocol is supplied. Independently reviewed Dutch BOM advice concerns "
            "palliative systemic therapy, not a conversion-surgery pathway; "
            "do not infer approval, reimbursement or perioperative interruption/restart rules."),
    _record(Role.PATIENT, "Goals: long-term disease control or cure; accepts short-term "
            "toxicity if curative intent is credible; preserve independence and avoid permanent "
            "stoma. Lives with partner; two adult children. No consent is inferred."),
    _trial("CRC-BREAKWATER", "BREAKWATER — first-line BRAF V600E systemic therapy",
           "Encorafenib/cetuximab plus mFOLFOX6 improved first-line systemic outcomes in "
           "previously untreated BRAF V600E metastatic CRC, not a liver-only population. "
           "A conversion-hepatectomy pathway and optimal "
           "perioperative duration were not specifically established.",
           "First-line BRAF V600E metastatic CRC; systemic efficacy, not conversion surgery",
           "PARTIAL",
           url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12197837/",
           authority="BREAKWATER investigators; New England Journal of Medicine",
           publication="Online 2025-05-30",
           doi="10.1056/NEJMoa2501912",
           scrutiny={"endpoints": "Phase III systemic progression-free and overall survival",
                     "subgroup_relevance": "Not dedicated conversion-metastasectomy randomization",
                     "funding": "Pfizer"},
           ),
    _trial("CRC-CAIRO5", "CAIRO5 — original 2023 induction report (abstract)",
           "Expert-panel reassessment informed local treatment in initially unresectable "
           "liver-only colorectal metastases. The original right-sided/RAS/BRAF-mutant induction "
           "analysis favored FOLFOXIRI/bevacizumab. This is not the patient's BRAF/EGFR-directed "
           "regimen, does not establish a BRAF-only effect and does not settle optimal "
           "post-response surgical timing.",
           "Initially unresectable CRLM with repeated expert-panel review; different induction",
           "PARTIAL",
           url="https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
           "query=EXT_ID:37329889%20AND%20SRC:MED&format=json&resultType=core",
           authority="CAIRO5 investigators; Lancet Oncology, original trial abstract",
           publication="2023",
           doi="10.1016/S1470-2045(23)00219-X",
           access="PUBLIC_ABSTRACT_ONLY",
           scrutiny={"access_scope": "Original abstract verified through Europe PMC core record",
                     "pubmed_locator": "https://pubmed.ncbi.nlm.nih.gov/37329889/",
                     "subgroup_relevance": (
                         "Right-sided/RAS/BRAF stratification, not BRAF-only effect"
                     )},
           ),
    _trial("CRC-CAIRO5-LONGTERM", "CAIRO5 — long-term outcomes, separate 2025 report",
           "In initially unresectable liver-only metastases, increased response/local treatment "
           "did not demonstrate an overall-survival advantage for triplet versus doublet "
           "induction; the survival comparison was underpowered. "
           "This does not establish a randomized surgery-versus-no-surgery effect or show "
           "that an individual potentially clearable patient should never receive local therapy.",
           "Long-term analysis of randomized induction in initially unresectable liver-only CRLM",
           "PARTIAL",
           url="https://pmc.ncbi.nlm.nih.gov/articles/PMC11583021/",
           authority="CAIRO5 investigators; JAMA Oncology",
           publication="Online 2024-11-21; issue January 2025",
           doi="10.1001/jamaoncol.2024.5174",
           scrutiny={"endpoints": "Long-term overall survival and local-treatment outcomes",
                     "subgroup_relevance": "Not a surgery/no-surgery randomization"},
           ),
    _trial("CRC-PROVENC3", "PROVENC3 — postoperative ctDNA prognosis in stage III",
           "Postoperative ctDNA was prognostic in resected stage III colon cancer. This is "
           "not conversion-stage IV peri-hepatectomy evidence and supplies no absolute "
           "ctDNA threshold prohibiting surgery.",
           "Resected stage III colon cancer, not conversion-stage IV disease", "LOW",
           url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12785881/",
           authority="PROVENC3 investigators; British Journal of Surgery",
           publication="PMC 2026-01-09; PubMed 2025-12-24; source date discrepancy retained",
           doi="10.1093/bjs/znaf281",
           kind="OBSERVATIONAL",
           scrutiny={"sample_size": "209 resected stage III colon patients on adjuvant therapy",
                     "endpoints": "Postoperative/post-adjuvant ctDNA prognosis and recurrence",
                     "subgroup_relevance": "No conversion-stage IV or binary no-surgery threshold"},
           ),
    _trial("CRC-NVMO-BOM", "Dutch NVMO/BOM — encorafenib, cetuximab and chemotherapy",
           "Positive PASKWIL 2023 palliative advice for encorafenib/cetuximab with chemotherapy "
           "as first-line treatment in metastatic BRAF V600E colorectal cancer. "
           "Control-arm post-progression BRAF-directed therapy was nonuniform. "
           "This supports Dutch systemic-treatment "
           "context, not a conversion-hepatectomy pathway, perioperative interruption schedule "
           "or individual hospital approval.",
           "Dutch palliative systemic treatment advice for BRAF V600E metastatic CRC", "PARTIAL",
           url="https://medischeoncologie.nl/artikelen/2026/juli/2026-6/"
           "encorafenib-cetuximab-en-chemotherapie-bij-gemetastaseerd-braf-v600e-"
           "gemuteerd-colorectaalcarcinoom",
           authority="NVMO commissie BOM; Medische Oncologie",
           publication="July 2026 advice; e-publication 2026-07-11; print 2026-08-12",
           kind="GUIDANCE", region="NL",
           scrutiny={"study_type": "Dutch BOM evidence appraisal, not a separate clinical trial",
                     "geographic_relevance": "Dutch advice; not local perioperative authorization",
                     "official_listing": "https://www.nvmo.org/bom/encorafenib-cetuximab-en-"
                     "chemotherapie-bij-gemetastaseerd-braf-v600e-gemuteerd-colorectaalcarcinoom/",
                     "conflicting_evidence": (
                         "Nonuniform post-progression control-arm BRAF therapy"
                     )},
           ),
]

MEMORIES: list[Memory] = [
    Memory(id="MEM-CRC-MAPPING", role=Role.RADIOLOGY, category="CLINICIAN_PREFERENCE",
           text="Review all nine original liver sites, vascular distances and chest uncertainty.",
           source="Demonstration preference card; not medical evidence", date="2026-09-16"),
    Memory(id="MEM-CRC-TOXICITY", role=Role.ONCOLOGY, category="FACTUAL_PATIENT",
           text="Grade 2 hypomagnesemia and rash; grade 1 sensory neuropathy after four cycles.",
           source="Case prior_cancer_treatment; CASE-CRC-ONCOLOGY", date="2026-09-09"),
    Memory(id="MEM-CRC-REMNANT", role=Role.SURGERY, category="INSTITUTIONAL_PRACTICE",
           text="Request complete clearance and remnant review before considering treatment.",
           source="Demonstration team practice card; not an approved protocol", date="2026-09-16"),
    Memory(id="MEM-CRC-SETTING", role=Role.RESEARCH, category="EXPERIENTIAL_NUDGE",
           text="Separate systemic response, conversion utility and stage III ctDNA prognosis.",
           source="Demonstration MDT reflection; not evidence", date="2026-09-16"),
]
