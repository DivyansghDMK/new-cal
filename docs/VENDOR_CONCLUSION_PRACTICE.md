<!-- Researched 30 August 2026 by a 29-agent workflow: 7 parallel researchers over
     Philips, GE, Glasgow, Mortara, Schiller, BPL, Dawei/EDAN/Contec/Biocare, the
     AHA/ACCF/HRS standard and printed-report layout, followed by 21 adversarial
     verifiers. 9 circulating claims failed verification and were corrected -
     see section 11. -->

# How the established vendors show ECG conclusions

**And what CardioX / RhythmUltra does differently**

---

## Read this first — our actual status

The research brief below marks most rows in its gap table ⚠️ *assumed absent*,
because the researchers only knew two things about our report. **We know more.**
Verified against the code this session:

| Brief's item | Its assumption | **What we actually do** |
|---|---|---|
| #8 Unconfirmed / overread banner — *"the single strongest convention in the industry"* | ⚠️ assumed absent | ✅ **We have it.** `Unconfirmed Diagnosis if not signed`, on the box title row, alongside `Please consult your doctor` |
| #7 Criterion printed per statement | ⚠️ likely absent | ✅ **We have it**, with a dotted leader — and an *implication* line beneath, which **no vendor in this study does** |
| #17 Global 12-lead onset-to-offset intervals — *AHA Part I requires it* | ⚠️ verify | ✅ **As of commit `1712454`, today.** It was off behind an env var; QRS read 18 ms short until this week |
| #13 Age- and sex-parameterised criteria | ⚠️ verify | ✅ **Partly** — ST elevation V2–V3 by age and sex (`ba3a340`). Nothing else is parameterised |
| #19 Filter / gain / speed in a fixed page region | ⚠️ verify | ✅ **We have it** — `filter_band` in the header |
| #20 Note that the print filter is not the analysis bandwidth | ⚠️ assumed absent | ⚠️ **Partly** — we append `NON-DIAGNOSTIC` when the low-pass is under 150 Hz, which is a stronger signal than the note Philips prints, but we do not state the analysis bandwidth separately |
| **#1 Severity line from a fixed vocabulary** | ⚠️ assumed absent | ❌ **Confirmed absent, and this is the real gap.** `build_interpretation()` computes `NORMAL / BORDERLINE / ABNORMAL / UNINTERPRETABLE ECG` and **nothing in the renderer reads it.** Every vendor here prints one |
| #3 Published statement library with stable codes | ⚠️ | ❌ We have 8 free-text labels in `REPORT_ALLOWED_CONCLUSIONS`, no codes |
| #11 Lead-reversal detection — *the standard requires it* | ⚠️ | ❌ Absent |
| #12 Explicit statement when age/sex missing | ⚠️ | ❌ We fall back silently to the conservative 1.0 mm threshold |
| #24 Published Physician's Guide | ⚠️ high-leverage | ❌ Absent — **but we already generate the criteria text**, so this is largely a documentation exercise |

So of the brief's "if only three things get done" — **#8 we already have**, #1 is a
renderer line away from existing, and #24 is documentation of work already done.

### The one number worth arguing with

The brief recommends adding a critical-value banner (#14) and then immediately
notes the seven-program study found **over 50% false-negative for ACS in every
program tested**. Given our own ST rule currently fires on 77% of records with no
ischemia label ([`pending/st-severity.md`](pending/st-severity.md)), a
`*** ACUTE MI ***` banner is the last thing we should add, not an early one.

### One finding to take seriously

**BPL is not a benchmark.** The research found it publishes no physician's guide,
no statement library, no criteria handbook and no sample printout — and that its
engine is a licensed Glasgow build whose version is not disclosed. Dawei publishes
less still and has no FDA clearance for any electrocardiograph. Publishing a
criteria handbook would put Deckmount **above** both on the one axis the AHA
standard actually asks for.

---

# Automated ECG Interpretation Reporting: How the Established Vendors Do It

**A technical comparison brief for the CardioX / RhythmUltra software team, Deckmount Electronics**

---

## 0. Scope, sources, and how to read this

This brief compares the printed interpretation block across **Philips (DXL)**, **GE HealthCare (Marquette 12SL)**, **University of Glasgow (Uni-G)** and its licensees, **Mortara / Welch Allyn / Baxter (VERITAS)**, **Schiller (ETM)**, and the Asian-market cart vendors **EDAN, Biocare, Contec, BPL and Dawei**. It is built from primary vendor documents — physician's guides, operator's manuals, FDA 510(k) summaries — plus the governing AHA/ACCF/HRS standard and the peer-reviewed accuracy literature.

Three honesty rules apply throughout:

- **Verified** = quoted verbatim from a primary document I can point at.
- **Likely** = strongly supported by primary evidence but inferred (e.g. a count I derived by parsing an appendix, not a figure the vendor publishes).
- **UNVERIFIED** = flagged explicitly and never asserted as fact.

Several widely-repeated claims failed verification during research and have been **corrected or excluded** here. Where a number in circulation is wrong, the corrected number is given with a note. See §11 for the register of corrections and known gaps.

**Two vendors in this comparison are effectively undocumented.** BPL Medical Technologies and Dawei Medical publish no physician's guide, no statement library, no criteria handbook, and no sample printout. This is stated plainly in §1.6 and §11 rather than padded out. If the intent was to benchmark against "the nearest Indian competitor," the honest finding is that **BPL is not a benchmark — it is a Glasgow licensee that publishes less than you do.**

---

## 1. How each vendor structures the conclusion block

### 1.1 Side-by-side summary

| | **Philips DXL** | **GE 12SL** | **Glasgow (Uni-G)** | **Mortara VERITAS** | **Schiller ETM** |
|---|---|---|---|---|---|
| Block position | Top-left text band, page 1 | Text band (above or below waveforms, per format) | Layout is the licensee's choice — Glasgow is layout-agnostic | Above waveforms, under measurements | User-orderable page block |
| Statement case | ALL CAPS | ALL CAPS (v17–20) → sentence case (v23) | Sentence case | Configurable (`Interp Text Uppercase`, default Yes) | Sentence case |
| Line prefix | Period-bullet (`.`) | None | None; `~` prefix marks modifier fragments | None | None |
| Criterion printed inline | **Yes** — dot-leader "reason" | **No** (base 12SL) | **Optional** — Short/Long report styles | **Yes** — in `[ ]` brackets | UNVERIFIED |
| Severity line | Yes, centred, `- ABNORMAL ECG -` | Yes, last line | Yes, one of six summary codes | Yes, "conclusion" at bottom of block | Yes, suppressible |
| Critical-value banner | `>>>> Acute MI <<<<` | `*** Critical Test Result: …` (v23) | `*** ACUTE STEMI ***` | `***ACUTE MI***` | None documented |
| Overread label | "Unconfirmed Diagnosis" | "Unconfirmed" / "Confirmed" / "Reviewed by" | Licensee's choice | "UNCONFIRMED REPORT" / "Reviewed by" | "Unconfirmed report" (on/off) |

### 1.2 Philips DXL — the most explicitly documented layout in the industry

Philips is the only vendor that publishes a **keyed sample-report figure**. Figure 4-1 of the PageWriter TC70/TC50 Instructions for Use labels fifteen page regions A–P, each with its own page reference: A Interpretive/Reason/Severity Statements, B Basic Measurements, C Patient ID Clinical Information, D Patient ID Information, E Institution Information, F Configurable Clinical Information, G ECG Order Information, H Physician Information, I Report Information, J Calibration Information, K Time Separator, L Pacing Detection Setting, M Algorithm Version, N Filter Settings, O Speed and Sensitivity Settings, P Device Identification Number. The DXL Physician's Guide repeats the same figure as Figure 5-1 ([TC70/TC50 IFU](https://archive.org/download/manual_Philips_PageWriter_TC70TC50_Cardiograph_User_manual/Philips_PageWriter_TC70TC50_Cardiograph_User_manual_djvu.txt); [DXL Physician's Guide Ed. 2](https://www.documents.philips.com/doclib/enc/fetch/2000/4504/577242/577243/577246/581601/711562/DXL_ECG_Algorithm_Physician_s_Guide_(ENG)_Ed.2.pdf)).

The interpretation block itself, reproduced verbatim from Figure 5-3 of the Physician's Guide (including the vendor's own typo "INFRACT"):

```
. SINUS RHYTHM.................................normal P axis, V-rate 50-99
. FIRST DEGREE AV BLOCK..............................PR >210, V-rate 50-90
. RIGHT BUNDLE BRANCH BLOCK.................QRSd>120, terminal axis(90,270)
. INFERIOR INFRACT, OLD........................Q >35mS, flat T, II III aVF
                            - ABNORMAL ECG -
```

**Selection rule (verbatim):** *"Each category is represented on the ECG report by a single statement if any criteria are met in the category. This statement is the last one encountered whose medical criteria were true… In each diagnostic category, more clinically significant findings override more benign ones… the presence of LBBB also suppresses a statement from a previous category, such as Left Axis Deviation, and bypasses tests for ventricular hypertrophy, most infarcts, ST deviations, and abnormal T waves."* This text is identical in Ed. 2 (2009) and Rev J (12/2025).

So the printed list is **at most one line per diagnostic category**, and a significant finding both suppresses lesser findings within its category *and* can bypass entire later categories.

> **CORRECTION — do not repeat the common claim about Philips print ordering.** A widely-circulated claim states that DXL prints statements in a fixed sequence "cardiac rhythm → adult morphology → pediatric morphology → technical quality." That sentence is genuine but is from **Appendix B of the 2003 predecessor guide** (Philips 12-Lead Algorithm, M5000-91000 Ed. 1, p. B-2), where it describes **how that manual organises its own appendix** — explicitly contrasted on the same page with Appendix C's alphabetical listing. It is not a report-output specification. DXL Ed. 2 and Rev J drop the sentence entirely and reorganise Appendix B so that Technical Quality sits **second**, not last, with pediatric and adult morphology interleaved by topic. **No Philips primary source documents a fixed statement print order on the ECG report.** Sample figures show rhythm first, but that is an observation, not a spec.

### 1.3 GE 12SL — compositional, not sentence-selected

GE's structural difference is the important one: **12SL assembles each printed line from numbered library fragments** rather than selecting whole sentences. Appendix F documents the recipes: `Cannot rule out anteroseptal infarct` = **CRO + ASMI**; `Deep Q wave in lead V6, possible left ventricular hypertrophy` = **QV6 + PO + LVH**. This is why connector fragments exist as numbered library entries with class `NA`: `1400 AND "and"`, `1401 HOWEVER "however"`, `1680 PO "Possible"`, `830 AC ", POSSIBLY ACUTE"`, `831 AU ", AGE UNDETERMINED"` ([12SL Physician's Guide Rev B, Appendix F](https://www.numed.co.uk/files/uploads/Product/3_12SL%20Physicians%20Guide%20Rev%20B.pdf)).

Ordering **is** documented for GE, unlike Philips: *"The rhythm criteria is presented first since it is analyzed before the morphology of the waveforms. This sequence is required because information regarding the rhythm is needed for proper morphology interpretation."* The morphology sequence is WPW → atrial hypertrophy → QRS abnormalities (low voltage, pulmonary pattern, axis, conduction, ventricular hypertrophy) → infarction → ST elevation → ST depression → T wave → QT → acute MI.

GE's report anatomy is a numbered 15-item table (MAC VU360 "Standard Report Layout", Table 43): demographics, vital signs, 12SL statements, ECG header, physician info, report status, waveforms, pace spikes, page number, report format, 12SL version, product model, filter, gain, speed ([MAC VU360 Operator's Manual](https://landing1.gehealthcare.com/rs/005-SHS-767/images/45351-MAC360-17Nov2022-3-3-Manual-LP-Diagnostic-Cardiology.pdf)).

### 1.4 Glasgow — fixed section order, capped rhythm output, layout delegated

Glasgow's statement list is organised into **21 named groups** printed in a fixed order: Preliminary comments → Lead reversal/dextrocardia → Restricted analysis → Miscellaneous preliminary → Pediatric → Intervals → Atrial abnormalities → Critical values → QRS axis deviation → Conduction defects → WPW pattern → Brugada pattern → Hypertrophy → Myocardial infarction → ST abnormalities → ST-T changes (ischemia) → Misc low QRS voltages → Misc tall T waves → Dominant rhythm → Supplementary rhythm → Summary statements ([Glasgow Physician's Guide, corpuls3 edition, §20](https://8331374.fs1.hubspotusercontent-na1.net/hubfs/8331374/Knowledge%20Base/corpuls3/20210525_glasgow_GAN_v1.0_ENG_Druck.pdf)).

A hard structural cap applies to rhythm (verbatim, §17): *"The rhythm section of the program will always select one statement (only) from the list of dominant rhythms and if appropriate will select up to three additional statements from the list of supplementary statements."*

Glasgow deliberately **does not specify page layout** — that is the cart maker's responsibility. Mindray's BeneHeart R3 annotated sample report gives one licensee's answer: item 11 Global measurements, item 12 Critical value, item 13 Diagnosis statement — i.e. measurements, then the critical-value headline, then the statements ([BeneHeart R3 Operator's Manual](http://mindray.sy/wp-content/uploads/2019/12/BeneHeart-R3-Operator-Manual.pdf)).

### 1.5 Mortara VERITAS and Schiller ETM

**VERITAS** ordering rule (verbatim): *"Interpretation of all ECGs proceeds in the sequence of the criteria listing. Ordinarily the last valid statement or conclusion reached within a given section supplants all prior statements."* The severity conclusion is appended at the bottom: *"The statement with the most severe condition provides the conclusion added at the bottom of the interpretative statements when printed"* ([VERITAS Physician's Guide 9515-001-53-ENG](https://www.hillrom.com/content/dam/hillrom-aem/us/en/sap-documents/LIT/9515-/9515-001-53-ENGLITPDF.pdf)).

**Schiller** is unique in making the whole report a **user-orderable stack of blocks**. The AT-102 G2 Reports menu lets the operator select, activate/deactivate and sort: "Rhythm 10s 25 mm/s 2p", "Measurements", "Averages Grid 25/25", "Averages Grid 50/25", "Averages Wide 50/25", "Panorama 25 mm/s", "Rhythms 10s / 5s / 5s 50mm/s / Grid". Even the header field order is configurable, and the severity header is an independent on/off ([CARDIOVIT AT-102 G2 User Manual](https://woodleytrialsolutions.com/img/products/user-guides/CARDIOVIT%20AT-102%20G2%20-%20User%20Manual.pdf)).

### 1.6 BPL and Dawei — the honest finding

**BPL Medical Technologies (Bangalore).** BPL publishes **no user manual, no service manual, no physician's interpretive guide, no criteria handbook, no statement library, and no sample printout** for any Cardiart model. Every retrievable BPL document is a 2–4 page marketing brochure. bplmedicaltechnologies.com has no downloads/support library; MedWrench holds a spec sheet only. The entirety of what BPL publishes about its conclusions is one sentence in the 9108D brochure: *"ECG Analysis and Interpretation — Gender, age & race specific advanced ECG analysis & interpretation - The Glasgow ECG Interpretation Algorithm."*

What *is* verifiable from BPL's own catalogue is which models carry which engine ([BPL all-product catalogue](https://www.bplmedicaltechnologies.com/product-catalogue/all-product-catalogue.pdf)):

| BPL model | Engine as stated by BPL |
|---|---|
| Cardiart 9108D, GenX3, GenX1 | Badged "Powered by Glasgow ECG Interpretation Algorithm" |
| Cardiart 9108, 8108 View, 6208 View Plus | "Automatic Measurements and Interpretation" — **engine never named** |
| Cardiart 7108, 6108T | "Parameter measurement program" (measurement only) |
| Cardiart 108T-DIGI | Neither |
| Cardiart GenX 12i / 12i+ | UNVERIFIED — current copy dropped the Glasgow name for "smart analysis adjusts for age, gender, and background" |

BPL has **no FDA 510(k) and no FDA establishment registration** (firm negative from direct openFDA queries against both the 510(k) and registration/listing endpoints), and no CDSCO record is publicly retrievable. The usual regulatory route to a vendor's statement library and validation summary is closed.

The one useful BPL statement about output format: the GenX3 page says *"The interpretation report comes as a short and detailed version. It also shows the comprehensive analysis along with the medians"* ([BPL GenX3](https://www.bplmedicaltechnologies.com/product-details/cardiology/ecgs/resting-ecg/cardiart-genx3/)) — which maps onto Glasgow's documented Short/Long report styles.

> **CORRECTION on BPL hardware lineage.** A circulating claim identifies the Cardiart 9108/9108D as the EDAN **SE-1200 Express**. That is wrong on the specifics. The 9108 (5.7" foldable LCD, 420×330×105 mm, 5 kg) matches the EDAN **SE-12/SE-1200**; the 9108D (7" LCD with touch option, 4.2 kg) matches the **SE-1201**. The shared 24-bit A/D, 0.01–300 Hz and 16000 Hz figures are **series-wide across the whole SE-12 family** and distinguish nothing. The SE-1200 Express is 8.0" and 420×330×120 mm — neither BPL model. No OEM or licensing relationship between BPL and EDAN is confirmed by any primary source; the identification remains circumstantial spec-matching. The EDAN **SE-12 Series** user manual is still a reasonable behavioural proxy because it covers all five models.

**Dawei Medical.** The only traceable primary document is the "Digital ECG machine instructions" for models DE03/DE06/DE12/ME03/ME06/ME12 from **Dawei Medical (Jiangsu), Xuzhou** — not any Shenzhen entity, and no "DW series" ECG document could be located at all ([Dawei manual, via Vietnam MoH](https://imda.moh.gov.vn/documents/10182/81706028/upload_00004420_1775629866702.pdf?version=1.0&fileId=81725225)). Its **entire** documented interpretation behaviour is one setting:

> *"Automatic diagnostic analysis — Optional: All, closed, only normal ECG. When selecting only the normal electrocardiogram, print only the diagnostic result of the normal electrocardiogram, otherwise it does not print. When selecting off, do not print any diagnostic results, and print only the 'diagnostic information' title."*

No statement library, no measurement matrix, no algorithm name, no age/sex criteria, no accuracy data, no overread disclaimer, and no FDA 510(k) for any Dawei electrocardiograph. **Every Dawei-specific interpretation claim should be treated as unsupported.** (Note the wording is functionally identical to EDAN's `Auto Analysis: On/Off/Normal ECG only` setting, including the same odd behaviour of printing an empty section title — suggestive of shared software lineage, but circumstantial, not proof.)

---

## 2. The severity / classification line

**Every serious vendor prints exactly one overall classification line, and it is the most-severe-single-statement, not a composite score.** This is the single most consistent convention in the industry.

| Vendor | Levels | Exact printed values (ascending severity) |
|---|---|---|
| **Philips DXL** | 6 | `No Severity` (NS) · `Normal ECG` (NO) · `Otherwise Normal ECG` (ON) · `Borderline ECG` (BO) · `Abnormal ECG` (AB) · `Defective ECG` (DE) — printed delimited, e.g. `- ABNORMAL ECG -` |
| **GE 12SL** | 4 | `Normal ECG` (N) · `Otherwise normal ECG` (O) · `Borderline ECG` (B) · `Abnormal ECG` (A) |
| **Glasgow** | 6 | `Normal ECG` · `Normal ECG except for rate` · `Normal ECG based on available leads` · `Borderline ECG` · `Abnormal ECG` · `Technical error` |
| **VERITAS** | 8 | `Normal ECG` · `Atypical ECG` · `Borderline ECG` · `Abnormal Rhythm ECG` · `***CRITICAL TEST RESULT***` · `Abnormal ECG` · `***ACUTE MI***` · `No Further Interpretation Possible` |
| **Schiller ETM** | 5 | `Normal ECG` · `Otherwise normal ECG` · `Borderline ECG` · `Possibly abnormal ECG` · `Abnormal ECG` |
| **Biocare CardioPro** | 5 | `1010 Normal ECG` · `1011 Borderline ECG` · `1012 Atipical ECG` *(sic — vendor's typo, printed as-is)* · `1013 Abnormal rhythm ECG` · `1014 Abnormal ECG` |
| **AHA/ACCF/HRS standard** | 4 | `Normal ECG` · `Otherwise normal ECG` · `Abnormal ECG` · `Uninterpretable ECG` |
| **Contec** | **none** | No severity tier. Nearest equivalent is library item 1, `No abnormality` — a statement, not a conclusion |
| **EDAN, Dawei, BPL** | UNVERIFIED | No vendor document found that specifies a severity line |

Notes worth carrying into design:

- **"Otherwise normal" ranks *below* "Borderline"** in GE's ladder, which is counterintuitive but explicit in the guide.
- **Philips:** *"Severities that are more abnormal override lesser severities. The severities of all interpretive statements in a report are combined to determine the overall severity of the ECG."* Individual statements carry a severity code in the criteria tables — e.g. LVHV = BO, LVHCNV = AB, borderline short QTc = ON.
- **GE's worked example:** Sinus bradycardia (O) + with frequent (—) + premature ventricular complexes (O) + in a pattern of bigeminy (O) + Left ventricular hypertrophy (A) ⇒ **Abnormal ECG**. Connector fragments carry no classification.
- **Class distribution matters.** In GE's v17–20 appendix of 225 entries, the classes distribute A=109, NA=48, `*`=32, O=20, B=13, **N=3** — only three statements can by themselves yield "Normal ECG."
- **The AHA standard treats "Borderline" as a *modifier* (code 301), not a verdict class.** Category A contains only four statements. Most vendors deviate from this ([AHA Part II](https://fd.org.ua/wp-content/uploads/2019/03/AHA-ACCF-HRS-Recommendations-for-the-Standardization-and-Interpretation-of-the-Electrocardiogram-Part-II.pdf)).
- **The severity line has mechanical consequences, not just semantic ones.** GE's MAC 5500 setup splits "Normal ECG Reports" and "Abnormal ECG Reports" into separate auto-print configurations with independent format, interpretation flag, and copy count (0–10) — so the classification selects which template prints and how many copies ([MAC 5500 Operator's Manual](https://www.davismedical.com/content/pdf/GE_Mac%205500_Users_Guides.pdf)).
- **The severity line is suppressible on several platforms.** GE: `Suppress NORMAL statement` and `Suppress ABNORMAL and BORDERLINE statements`. Schiller: `Display abnormal/borderline header Yes/No`. Biocare: `Diagnostic Conclusion — Disable/Enable`, independent of the statement list.

---

## 3. Statement library size and wording conventions

### 3.1 Sizes — with corrections

| Vendor / program | Count | Basis |
|---|---|---|
| **Philips DXL** (Ed. 2, PH100B) | **605 distinct statement codes in 43 categories** | Column-position parse of Appendix B, Tables B-1…B-43, pp. B-1–B-46. **Corrected** — see note below |
| **GE 12SL v17–20** | **exactly 225** | Appendix B, Rev B guide; unique, strictly increasing, 1→1699 |
| **GE 12SL v23** | **exactly 496** | Appendix B, Rev C guide, pp. 283–302. **Corrected** — see note below |
| **Glasgow (corpuls3 ed.)** | **355 lines / 346 unique, 21 groups** | §20 list. **Corrected** — see note below |
| **Biocare CardioPro** | ~216 numbered codes, 9 groups | My count of Appendix D code lines; vendor states none |
| **Contec ECG-1200G** | exactly 60, closed list | Appendix I §2.2, items 1–60 |
| **VERITAS, Schiller ETM** | UNVERIFIED | No published count located |
| **EDAN SEMIP** | UNVERIFIED | Manuals publish only three subsets (19 serious diseases, 24 extended-print arrhythmias, 19 abnormal statements); no total anywhere |
| **BPL, Dawei** | **No library published at all** | See §1.6 |

> **CORRECTION — Philips.** The figure "~654 codes / ~40 categories" is in circulation and is wrong. A column-disciplined parse of the Statement Code column (codes at x≈53, interpretive text at x≈150, Notes at x≈460) yields **605 unique codes, zero duplicates, across 43 named categories**. The inflated figure comes from a regex sweep over flattened text that swallows the adjacent **Notes** column, which carries ~66 *legacy alias codes* for renamed statements (e.g. PRAE→note PRAA, LAECB→note LAACB, BAE→note BAA) rather than new statements. Left column ∪ notes column = 671; a fully naive uppercase-token sweep gives 722. Also note: the phrase "over 600 interpretive statements" does **not** appear in the Physician's Guide — it is external marketing copy.

> **CORRECTION — GE v23.** The figure "roughly 404–489" is wrong, and its stated cause (PDF text wrapping defeating row detection) is also wrong. The v23 appendix table is **number-first on every row**, so counting is unambiguous: **496 rows, 496 unique numbers, zero duplicates, zero monotonic violations, range 1–1699**, reproduced identically by two independent PDF engines and corroborated by Appendix A's 440 numbers being a strict subset. All 225 v17–20 numbers are a subset of the v23 set; the 56 numbers in B but not A are non-clinical/reserved codes (`$RDBC1-3`, `$SERREM`, `SNF`).

> **CORRECTION — Glasgow.** The figures "370 lines / 357 unique" are wrong; the actual §20 list is **355 lines (354 net of one OEM editorial note), 346 unique (9 exact duplicates)**, across exactly 21 groups. Group counts, verified: Preliminary comments 25; Lead reversal/dextrocardia 4; Restricted analysis 4; Misc preliminary 6; Pediatric 1; Intervals 4; Atrial abnormalities 5; Critical values 7; QRS axis deviation 12; Conduction defects 8; WPW pattern 8; Brugada pattern 1; Hypertrophy 12; Myocardial infarction 51; ST abnormalities 30; ST-T changes (ischemia) 81; Misc low QRS voltages 4; Misc tall T waves 2; Dominant rhythm 46; Supplementary rhythm 38; Summary statements 6. **Also: this count cannot be attributed to BPL.** The document counted is the **corpuls3 edition** (GS Elektromedizinische Geräte G. Stemple GmbH, P/N 04145.02, EN v1.0, 2021-05-25) — the strings "BPL", "Cardiart" and "BPL Medical Technologies" appear **zero times** in it, and it repeatedly scopes itself to corpuls3 hardware ("corpuls3 does not support race as an input"). Which Glasgow build BPL ships is unknown.

**The true printable count always exceeds the library count**, because most vendors use combinatorial templates. Glasgow: 101 of 355 entries are leading-`~` modifier fragments appended to a parent statement. GE: connector fragments (`PO`, `CRO`, `AND`, `AC`, `AU`) recombine with region statements. Philips: `***`/`**`/`*` are numeric placeholders — *"The symbol \*\*\* in an interpretive statement is replaced with a numeric value on the ECG report."*

### 3.2 Wording conventions, with real examples

**Graded hedging is lexicalised, not ad-hoc.** Every mature vendor has a small closed set of certainty prefixes reused across all territories.

Schiller is the only vendor that publishes **what its hedges numerically mean** ([Schiller Physician's Guide §4.3](https://www.numed.co.uk/documents/download/263)):

| Schiller hedge | Stated confidence |
|---|---|
| `Cannot Rule Out...` | ≈ 15% |
| `Possible ...` | ≈ 35% |
| `Consider...` | ≈ 50% |
| `Consistent with ...` | ≈ 80% |

GE's hedge fragments are numbered library entries: `1680 PO "Possible"`, `CRO "Cannot rule out"`, `844 CRI-FOR "Criteria for"`, `845 MINI-CRIT "Minimal criteria for"`, `846 BORD-CRIT "Borderline criteria for"`, plus suffixes `830 AC ", possibly acute"` and `831 AU ", age undetermined"`.

Biocare builds MI statements on an explicit **3 × 4 certainty × age grid** across eight territories:

```
1113  Cannot rule out anterior myocardial infarction, probably old
1221  Possible anteroseptal myocardial infarction, possible acute
1633  Inferior myocardial infarction, probably old
16312 Inferior myocardial infarction with posterior extension, possible acute
```

**Severity grading within a finding** — Biocare's ST-depression ladder:
```
2102  Minimal ST depression
2103  Moderate ST depression
2104  Marked ST depression, possible subendocardial injury
2106  Marked ST depression, consistent with subendocardial injury
```

**Reassurance statements** — Glasgow is notably willing to say a finding is probably benign, which reduces overreading:
```
Small inferior Q waves noted: probably normal ECG
rSr'(V1) - probable normal variant
Borderline high QRS voltage - probable normal variant
```
Philips has the equivalent in its Borderline Statement Suppression tables: `RSR1 "RSR' in V1 or V2, probably normal variant.........small R' only"`, `SEINP "ST elevation, probably normal variation, inf........ST>0.15mV, II III aVF"`.

**Culprit-artery localisation** — Philips DXL prints the suspected vessel in parentheses inside the STEMI statement: *"In addition to the traditional suggested localization of the infarct, the probable culprit artery is identified in parentheses."*
```
ANTERIOR INFARCT, ACUTE (LAD)
INFERIOR INFARCT, ACUTE (RCA)
POSTERIOR INFARCT, ACUTE (LCX)
RIGHT VENTRICULAR INFARCT, ACUTE (RCA)
```
Glasgow does the equivalent as parenthetical prose:
```
Marked anteroseptal ST depression, CONSIDER ACUTE INFARCT (proximal LAD occlusion)
Widespread ST depression, CONSIDER ACUTE INFARCT (left main occlusion /multivessel disease)
```

**Delimiter conventions differ by vendor and are worth copying deliberately rather than by accident:**

| Marker | Meaning | Vendor |
|---|---|---|
| leading `.` | statement bullet | Philips |
| `....` dot leader | separates statement from reason | Philips |
| `***`/`**`/`*` | numeric placeholder | Philips |
| `>>>> … <<<<` | critical value, printed | Philips |
| `- … -` | overall severity line | Philips |
| `#` prefix | overreader-only edit code (`#LVHST`, `#HVOLT`) | Philips |
| `~` prefix | modifier appended to parent statement | **Glasgow** |
| `--- … ---` | technical/preliminary comment | Glasgow |
| `*** … ***` | critical value | Glasgow, VERITAS |
| `[ … ]` | reason/criteria | VERITAS |
| `** ** ** ** * … * ** ** ** **` | acute MI banner | GE v17–20 |

> **The `~` prefix is a Glasgow convention, not a Philips one.** Neither the DXL Ed. 2, nor Rev J, nor the 2003 Philips 12-Lead guide contains a tilde anywhere in the text (all three extracted PDFs were searched directly). If you have seen `~` attributed to Philips, it is a misattribution.

> **Two strings that do NOT exist and should never be quoted:** `***ACUTE MI SUSPECTED***` is **not** in GE's library (GE's actual strings are `** ** ** ** * ACUTE MI * ** ** ** **` in v17–20 and `** ** ACUTE MI ** **` in v23). And `UNCONFIRMED REPORT` as a single printed GE phrase was not found — GE prints the status word `Unconfirmed`, and the library's `1306 SUNCNF "(Unconfirmed)"` is a *serial-comparison qualifier referring to the prior ECG*, not the current one.

---

## 4. Is the CRITERION printed alongside each statement? *(directly relevant to CardioX)*

**Short answer: printing criteria alongside statements is a real, established, minority practice. Two of the six major algorithms do it by default, a third does it as a user-selectable report style, and one major vendor deliberately does not.** It is *not* mandated by any standard.

| Vendor | Prints criterion inline? | Form | Configurable? |
|---|---|---|---|
| **Philips DXL** | **Yes** | Dot-leader, right-aligned after statement: `FIRST DEGREE AV BLOCK..............PR >210, V-rate 50-90` | Yes — and **only on unconfirmed reports** |
| **Mortara VERITAS** | **Yes** | Square brackets inside the statement: `Anteroseptal Infarct [40+ ms Q WAVE IN V1-V4]` | Yes — `Reasons` on/off; requires interpretation enabled |
| **Glasgow** | **Optional** | Short vs Long report style; long format prints explanatory reasons above/beside the statement | Yes — `Interpretation: Short/Long/Off` on Cardioline; "short and detailed version" on BPL GenX3 |
| **GE 12SL** | **No** (base program) | Only the optional **ACS Tool** prints reasons, appended after *"ECG interpretation of ACS is based on presence of symptoms and…"*. Base 12SL instead embeds criteria-strength as a fragment (`Minimal voltage criteria for LVH, may be normal variant`) | n/a |
| **Schiller ETM** | UNVERIFIED | Not documented either way in retrievable manuals | — |
| **Contec** | **No** — but publishes criteria in the manual (Appendix I §3.5, per-item rules) | — | — |
| **EDAN, Biocare, Dawei, BPL** | **No** | EDAN publishes normal ranges in an appendix; Biocare prints a Minnesota Code the reader decodes separately | — |

Three findings that should shape CardioX's design decision:

**(a) Philips treats criteria as a pre-overread aid, not part of the permanent record.** Verbatim from the LVH section of the DXL guide: *"Reasons may appear on unconfirmed reports if the acquisition device is configured to display them. After confirmation on a TraceMaster ECG Management System, they are no longer shown. They generally indicate which evaluation criteria were met."* This is a deliberate design: criteria help the overreading physician decide, then disappear from the confirmed clinical document. **If CardioX prints criteria, mirroring this — criteria visible pre-confirmation, suppressible/absent post-confirmation — puts you in step with the single best-documented implementation of the feature.**

**(b) The standard asks for criteria in *reference material*, not on the tracing.** AHA Part I, verbatim: *"Programs using complex diagnostic algorithms should document in reference material those measurements that are critical to the diagnostic statement."* And AHA Part II explicitly declines to standardise criteria at all: *"This listing does not specify diagnostic criteria for any of the statements… we encourage ECG vendors and electrocardiography researchers and experts to collaborate on the development of a universally acceptable criteria set"* ([Part I](https://fd.org.ua/wp-content/uploads/2019/03/AHA-ACCF-HRS-Recommendations-for-the-Standardization-and-Interpretation-of-the-Electrocardiogram-Part-I.pdf), [Part II](https://fd.org.ua/wp-content/uploads/2019/03/AHA-ACCF-HRS-Recommendations-for-the-Standardization-and-Interpretation-of-the-Electrocardiogram-Part-II.pdf)). So printing criteria is a **legitimate differentiator**, but publishing a criteria handbook is the thing the standard actually asks for — and neither BPL nor Dawei nor EDAN does it, while Contec and Philips and GE all do.

**(c) Criteria strings are terse and abbreviation-dense in practice.** Real examples of the register in use:
```
Philips:  normal P axis, V-rate 50-99
          QRSd>120, terminal axis(90,270)
          Q >35mS, flat T, II III aVF
          ST >0.35mV in V1-V5
          V-rate >(220-age)
          (R aVL+S V3) > LVHCNV:THRESH mV
VERITAS:  [40+ ms Q WAVE IN V1-V4]
          [QRS axis < -30]
          [QRS axis > 100]
```

---

## 5. Critical-value / acute-MI alerting

### 5.1 What each vendor prints

| Vendor | Printed form (verbatim) | Count | Placement |
|---|---|---|---|
| **Philips DXL** | `>>>> Acute MI <<<<` · `>>>> Acute Ischemia <<<<` · `>>>> Complete Heart Block <<<<` · `>>>> Very High Heart Rate <<<<` | 4 | Large font, just under the severity line, left of "Unconfirmed Diagnosis"; **plus a second notation at bottom right**, plus a `C` beside the algorithm version |
| **GE 12SL v17–20** | `** ** ** ** * ACUTE MI * ** ** ** **` | 1 | In statement block |
| **GE 12SL v23** | `** ** ACUTE MI ** **` and `*** Critical Test Result: <list>` | 1 + 7 result types | *"appears as the first line of the 12SL interpretation"* |
| **Glasgow** | `*** ACUTE STEMI ***` · `*** POSSIBLE ACUTE STEMI ***` · `*** ACUTE MI/ISCHEMIA ***` · `*** EXTREME TACHYCARDIA ***` · `*** EXTREME BRADYCARDIA ***` · `*** SIGNIFICANT ARRHYTHMIA ***` · `*** PROLONGED QTc INTERVAL ***` | 7 | Layout is licensee's choice |
| **VERITAS** | `***ACUTE MI***` · `***CRITICAL TEST RESULT***` | 2 | Is the conclusion line itself, above waveforms, under the interpretation text — **prints even if interpretation is disabled** |
| **EDAN** | **No text banner.** 19-item "List of Serious Diseases" rendered **in red on screen**, with a `Serious Illness Hint` toggle | 19 conditions | Screen only |
| **Contec** | **None, and explicitly disclaimed:** the function *"does not generate alarms during its use, so it must be used by professional and qualified personnel"* | 0 | — |
| **Biocare, BPL, Dawei, Schiller** | None documented | — | — |

Philips' library entries use a narrower delimiter than the printed form: `ACUTMI ">>> ACUTE MI <<<"`, `ACUISC ">>> ACUTE ISCHEMIA <<<"`, `CMPLHB ">>> COMPLETE HEART BLOCK <<<"`, `XTACH ">>> EXTREME TACHYCARDIA <<<"`.

### 5.2 Firing logic — three genuinely useful design patterns

**Critical values are roll-ups of ordinary statements, not independent detectors.** This is the key architectural insight and it is shared across Philips, GE and Glasgow.

- **Philips:** Rev J prose says *"Thirty interpretive statements are summarized in the following four Critical Values."* However, the enumerated tables (Rev J Tables 5-1…5-4) list **~43 codes** — ~36 acute-MI (AMIA, AMIAP, IMIA, PMIA, LMIA, ASMIA, EAMIA, ALIA, RMIA and territory/artery variants), 3 tachycardia (ETACH, TACHW, VTACH), 3 complete heart block (3AVB, 3AVBIR, 3AVBFF), 1 acute ischemia (LMMVD). **This internal conflict is unresolved**; the "thirty" figure appears to be stale prose.
- **Glasgow:** `*** ACUTE STEMI ***` fires when ST amplitudes exceed the *higher* threshold set **and** a regional infarct statement is already present; `*** POSSIBLE ACUTE STEMI ***` fires when only the normal upper limits are exceeded.

**Age-adjusted rate thresholds, not fixed cut-offs.** Philips: *"the measured heart rate in beats per minute, minus the patient age in years. If this value is 150 bpm or higher, the measurement will generate the extreme tachycardia statement."* The underlying ETACH statement prints its reason as `V-rate >(220-age)`. Glasgow bands it: extreme tachycardia ≥18 yr = 150 bpm; 181 days–17 yr = 230→150; birth–28 days = 213→230. Extreme bradycardia: >12.5 yr = 40 bpm; 1–6 yr = 90→45.

**Confounder gating.** Glasgow's `*** PROLONGED QTc INTERVAL ***` requires QTc > 520 ms **AND** QRS < 120 ms **AND** HR ≤ 125 bpm. GE's v23 Long QTc critical value requires no LBBB, no RBBB, no ventricular pacing, QRS < 140 ms, rate < 140 bpm. GE also suppresses a Low HR flag when the rhythm is "Normal sinus rhythm" — *"we will avoid saying 'Low HR' when the rhythm is 'Normal sinus rhythm'."*

### 5.3 The regulatory hook and the honest caveat

Philips ties Critical Values explicitly to accreditation: *"This feature is provided in part to help satisfy Section 2C of Goal 2 of the 2009 National Patient Safety Goals of the United States of America, as defined by the Joint Commission on Accreditation of Healthcare Organizations."* GE v23 notes critical-value statements *"become part of the ECG record."* Mortara requires acknowledgement with a technician identifier of ≥2 characters, populating an "acknowledged by" field.

**But no standard specifies the wording.** Neither AHA Part I nor Part II mentions asterisk banners, angle brackets, or STAT syntax; Part II's lexicon has no escalation above "Abnormal ECG." And the evidence is unkind to critical-value flags: the seven-program head-to-head found **ACS flagging varied by a factor of 2.5 between programs**, with false-negative rates **>50% for all of them**, concluding: *"Healthcare institutions should not rely on ECG software 'critical result' flags alone to decide the ACS workflow"* ([J Electrocardiol 2019](https://www.sciencedirect.com/science/article/pii/S0022073619306120)).

---

## 6. The "unconfirmed / requires physician overread" convention

### 6.1 What each vendor prints

| Vendor | Printed text | Configurable? |
|---|---|---|
| **Philips** | `Unconfirmed Diagnosis` — *"Indicates that the ECG report has not been overread by a qualified physician. This statement may be customized by an institution."* | Yes, institution-customisable. Sits in the Report Information block with `COPY`, `STAT`, `Non-standard lead gains` |
| **GE** | `Unconfirmed` / `Confirmed` / `Reviewed by <name>` — a device-level "Confirmation text" setup field, **not a 12SL statement** | Yes, three-way |
| **Mortara** | `UNCONFIRMED REPORT` or `Reviewed by` — the `Append` setting, *"printed under the interpretive text"* | Yes, two-way |
| **Schiller** | `Unconfirmed Report` | Yes — **Print / Not Print** (can be switched off entirely) |
| **EDAN** | `Unconfirmed Report` — SE-1200 Series `Prompt` setting: *"Select Unconfirmed, Unconfirmed Report is printed in the ECG reports"* | Yes: `Confirmed By` (default) / `Unconfirmed` |
| **Cardioline** (BPL-distributed) | `REPORT NOT CONFIRMED` / `CONFIRMED by xxxx on xx/xx/xxxx` — the `Record Status` setting | Yes/No |
| **Physio-Control LIFEPAK 15** (Glasgow) | `**UNCONFIRMED**` — *"All 12-lead ECG interpretation statements provided by the LIFEPAK 15 monitor/defibrillator include the printed message \*\*UNCONFIRMED\*\*"* | Not documented as optional |
| **Glasgow program itself** | Nothing — mandates no text. Only a WARNING block in the guide | licensee's choice |
| **BPL Cardiart, Dawei, Contec, Biocare** | **None documented** | — |

### 6.2 The actual legal / regulatory basis

There are **three** bases, and they are commonly conflated. Getting this right matters if you are writing regulatory documentation.

**(a) The scientific-statement requirement — the real one.** AHA/ACCF/HRS Part I, verbatim: *"Computer-based interpretation of the ECG is an adjunct to the electrocardiographer, and **all computer-based reports require physician overreading**."* And: *"Sensitivity and specificity of computer-based diagnostic statements are improving, but at the same time, it remains evident that physician overreading and confirmation of computer-based ECGs is required."*

Critically: **neither Part I nor Part II uses the word "unconfirmed" anywhere** (both full texts searched; zero occurrences). The requirement is functional, not lexical. The printed word is a **vendor labelling convention** that implements the functional requirement.

**(b) Device labelling — where the wording actually comes from.** Every vendor carries an Indications-for-Use or boxed-warning sentence, and the phrasing is near-identical across the industry:

- GE: *"WARNING — INTERPRETATION HAZARD: 12SL analyses… should be used only as an adjunct to clinical history, symptoms, and the results of other non-invasive and or invasive tests. All reports must be reviewed by a qualified physician."* MAC 2000 adds: *"A qualified physician must overread all computer-generated tracings."*
- EDAN (K160876), Biocare (K141946, K171517), Spacelabs (K130207): *"the interpreted ECG with measurements and interpretive statements is offered to clinicians on an advisory basis only."*
- Mortara: *"The ECG interpretations offered by the device are intended to be most relevant when used in conjunction with a physician over-read and with consideration of all other relevant patient data."*
- Glasgow guide: *"No automated analysis system is completely reliable, however, and interpretations should be reviewed by a qualified physician before treatment, or non-treatment, of any patient."*

**(c) US reimbursement — a reinforcement, not the origin.**

> **CORRECTION.** A common claim states that CMS *requires a separate, distinct, authenticated physician interpretation*, cites Medicare Claims Processing Manual **Chapter 12**, and asserts this is what the UNCONFIRMED banner encodes. All three parts need fixing. The relevant text is in **Chapter 13 §100.1** (per 42 CFR 415.120(a)), not Chapter 12 — Chapter 12's only EKG passage is an expired 1992–93 bundling rule. CMS does **not** require a physically separate document; the "separate, signed, written, and retrievable report" phrasing is **CPT's**, not CMS's ([AAPC](https://www.aapc.com/blog/27895-charge-up-your-ecg-documentation/)). And reimbursement is **not** the driver of the banner: no vendor manual, 510(k) or standard cites it, GE's MUSE defines confirmed/unconfirmed purely as overread workflow state, and MUSE ships in markets with no CMS at all. **Correct framing:** under Medicare, a computer-generated report alone does not support billing CPT 93010 — the physician must produce a complete written interpretation, and a passing "EKG normal" notation is treated as a bundled review. This *reinforces* overread in US practice; the unconfirmed→confirmed state is a device-labelling and overread-safety convention implemented identically worldwide.

**For an Indian-market device**, (a) and (b) are the operative ones. (c) is irrelevant to Deckmount.

### 6.3 Why this convention exists — the automation-bias evidence

This is not ceremonial. Tsai et al. (JAMIA 2003) ran a randomised crossover with resident physicians: without computer interpretation, 48.9% of findings correct; with correct interpretation, 55.4% (p<0.0001). But **with an *incorrect* interpretation present, accuracy fell from 56.7% to 48.3%**, and *"Subjects erroneously agreed with the incorrect CI more often when it was presented with the EKG 67.7%… than when it was not 34.6% (p<0.0001)"* ([doi:10.1197/jamia.m1279](https://doi.org/10.1197/jamia.m1279)).

Bogun et al. (Am J Med 2004) is the clinical harm case: of 2,298 ECGs computer-labelled atrial fibrillation, **442 (19%) were wrong**; in 92 patients (24% of those) the ordering physician failed to correct it, *"resulting in change in management and initiation of inappropriate treatment, including antiarrhythmic medications and anticoagulation in 39 patients (10%)"* ([PMID 15501200](https://pubmed.ncbi.nlm.nih.gov/15501200/)). A Swedish primary-care replication using **Glasgow v28.5.1** found 9.0% of computer AF/flutter diagnoses wrong (34% wrong for flutter specifically), with physicians accepting 47% of the wrong ones uncorrected and twelve patients anticoagulated inappropriately ([Scand J Prim Health Care 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6883419/)).

---

## 7. What the measurement matrix contains

Note the terminology trap: **"measurement matrix" means two different things**. Philips, GE and Schiller use it (or an equivalent term) for the *per-lead* table; the header row of global values is separately called "Basic Measurements" (Philips) or "Vital Signs" (GE).

### 7.1 The global block (the header row)

| Vendor | Fields printed |
|---|---|
| **Philips** ("Basic Measurements") | `RATE` (bpm), `RR` (ms), `PR` (ms), `QRSD` (ms), `QT` (ms), `QTcB` Bazett; Rev J adds `QTcF` Fridericia, `QTcH` Hodges, `QTcFm` Framingham. Then a `--AXIS--` sub-block: `P`, `QRS`, `T` frontal axes in degrees |
| **GE** ("Vital Signs") | Heart rate, PR interval, QRS duration, QT/QTc, P-R-T axes, blood pressure |
| **Mindray/Glasgow** (licensee) | Vent. Rate (bpm), PR Interval (ms), QRS Duration (ms), QT/QTc (ms), P/QRS/T Axes (deg), optional RV5/SV1 and RV5+SV1 (mV) |
| **Mortara** | Global PR, QRS, QT, average RR; QTcB and QTcF alongside a default linear QTc |
| **Schiller** | Heart rate, intervals, axes, **Sokolow Index**, plus a Detailed Measurement Table |
| **EDAN** | HR, P duration, PR, QRS, QT/QTc, frontal P/QRS/T axes, RV5/SV1; optional RV5+SV1, RV6/SV2, RR/PP. **Five QTc formulae selectable** |
| **Biocare** | HR, PR, QRS, QT/QTc, P/QRS/T axis, RV5/SV1, RV5+SV1. QTc default **Hodges** |
| **Contec** | HR, PR, **P duration**, QRS, **T duration**, QT/QTc, P/QRS/T axis, R(V5)/S(V1), R(V5)+S(V1) |
| **BPL Cardiart** | **UNVERIFIED — undocumented anywhere** |
| **Dawei** | **UNVERIFIED — undocumented anywhere** |

Observations: **Contec is the only vendor printing T duration.** **RV5/SV1 (Sokolow) is an Asian/European convention** — present in Schiller, EDAN, Biocare, Contec and Mindray, and absent from the documented Philips, GE and Mortara standard matrices. If CardioX targets Indian cardiologists, keeping RV5/SV1 is regionally correct.

### 7.2 The per-lead matrix

**Glasgow's is the most elaborate** (§19): 15 columns (I, II, III, aVR, aVL, aVF, V1, V2, V3 *or V4R in paediatric placement*, V4, V5, V6, + 3 optional), with rows sparsely numbered 1–53: P onset, P duration, QRS onset, QRS duration, Q/R/S/R'/S' durations, T onset, QRS intrinsicoid deflection, P+/P− amplitudes, peak-to-peak QRS, Q/R/S/R'/S' amplitudes, ST amplitude, 2/8 and 3/8 ST-T amplitudes, T+/T− amplitudes, QRS area, T morphology, R-wave notch count, delta-wave confidence (%), ST slope (degrees, J point to 3/8 ST-T), QT interval, QRS notch/slur amplitude, PR amplitude, ST adjusted amplitude. Durations in ms, amplitudes in µV.

**GE's is a separate report format**, not trace annotation: the Expanded Median format's *"upper part of the report is text (including the measurements but not the interpretation) and the measurement matrix, which is the measurements for each lead in the record (12 or 15 lines)."* GE notes its criteria *"use only the values from the measurement matrix."*

**Schiller's is amplitude-per-lead** rather than a 40-row matrix: *"In 12 columns i.e. one for each lead, the amplitude values of P, Q, R, S, T and R\", S\", T\" waves, the J point and the ST integral are listed in millivolts."*

### 7.3 Measurement conventions — get these right

**Global onset-to-offset across all leads is universal.** GE, verbatim: *"Onsets are defined as the earliest deflection in any lead, and offsets are defined as the latest deflection in any lead. Thus, the QRS duration is measured from the earliest onset in any lead to the latest deflection in any lead."* Mortara notes the consequence: *"global QT"* is statistically longer than a single-lead QT. Schiller and Glasgow do the same.

**This is a standards requirement**, not a vendor choice. AHA Part I, verbatim: *"Global measurements of intervals should be obtained from time-coherent data in multiple leads… For routine purposes, global measurements of P-wave duration, PR interval, QRS duration, and QT duration should be stated on the ECG report."*

**The standard also asks for something almost nobody prints:** *"the addition of a frontal plane ST-segment axis to the currently measured P-wave, QRS, and T-wave axes in the ECG header data is recommended."* I found no vendor in this comparison that prints an ST axis. **This is an available, standards-backed differentiator.**

**QTc formula must be stated.** Philips Rev J publishes all four: Bazett QTc = QT/√RR; Fridericia QTc = QT/∛RR; Hodges QTc = QT + 1.75(HR−60); Framingham QTc = QT + 0.154(1−RR). GE uses Bazett and notes the v23 Critical Values module *"always defaults to the Bazett correction."* Defaults differ across vendors (Biocare defaults to Hodges), so labelling the formula on the report is not optional.

**Small print that avoids support calls:** Philips — *"Some reports do not include the heart rate (RATE) in Basic Measurements, but do include a heart rate above the interpretive statements. This rate may be edited."* GE — *"A PR interval is reported only if synchronous P waves are detected."* Cardioline — *"the heart rate shown in print is that calculated as the average of the 10 s rhythm printed."*

---

## 8. Where filter / bandwidth settings are printed

**Every serious vendor prints filter, gain and speed on the page.** Placement is consistent: a thin technical annotation strip along the bottom edge.

| Vendor | What prints | Where |
|---|---|---|
| **Philips** | Dedicated **"filter information box"** printing AC line frequency + frequency-response band, e.g. `60~ 0.05-150 Hz`; adds `F` for artifact filter; `0.5` high-pass shown when baseline-wander filter on. Selectable low-pass 40/100/150 Hz; high-pass 0.05/0.15/0.5 Hz | **Lower right corner** |
| **Philips** | Separate block: `Speed 25 mm/sec`, `Limb 10 mm/mV`, `Chest 10 mm/mV` (limb 5/10/20; chest 2.5/5/10/20; speed 25/50 mm/s) | Bottom strip, with Philips logo and `Dev: 132` |
| **GE** | Filter Setting (Hz, with **ZPD** noted for the high-pass), Gain Setting (mm/mV), Speed Setting (mm/s), plus 12SL version, product model, report format, page x of y | Bottom strip. Exercise reports add a coded strip on the **lower left edge**: `A+/A-`, `H+/H-`, `S+/S-`, `50`, `60`, `HR` |
| **Mortara** | Filter setting and Gain setting; Site Name separately | Filter/gain **bottom right corner**; site name **bottom left edge** |
| **Schiller** | AT-101 manual mode: chart speed, user ID, mains filter (50/60 Hz), myogram cutoff (25/35 Hz) on the **lower edge**; heart rate, sensitivity, time/date at the **top**. AT-102 G2 renders as e.g. `LP 40Hz, AC 50Hz` | Lower edge |

### 8.1 Three conventions worth adopting verbatim

**(1) State that the printed bandwidth is not the analysis bandwidth.** This is a genuine safety point and both Philips and Mortara print/document it.

Philips, verbatim: *"NOTE While all filters affect displayed and printed ECGs, the interpretive algorithms always receive, store, and analyze data at 0.05 to 150 Hz."* And: *"The interpretive algorithms always use 0.05 to 150 Hz bandwidth for maximum fidelity. The maximum fidelity waveform is always stored in the permanent record."*

Mortara: *"The plot-frequency filter does not filter the digitized signal acquired for interpretation of the ECG."* Schiller: *"The ECG is stored unfiltered. It is therefore possible to print the stored ECG either with or without applying the myogram filter."*

**(2) Warn when a 40 Hz filter invalidates the trace.** AHA Part I, verbatim: *"An obvious consequence of these high-frequency recommendations is that reduction of noise by setting the high-frequency cutoff of a standard or monitoring ECG to 40 Hz will invalidate any amplitude measurements used for diagnostic classification."* The standard then recommends: *"Electrocardiographs should automatically alert the user when a suboptimal high-frequency cutoff, such as 40 Hz, is used, and a proper high-frequency cutoff should automatically be restored between routine standard ECG recordings."* Required bandwidth: **≥150 Hz upper cutoff for adults/adolescents, 250 Hz for children/infants**; low-frequency 0.05 Hz analog, relaxable to ≤0.67 Hz for zero-phase-distortion digital filters.

Mortara implements this: *"When the 40 Hz filter is used, the frequency response requirement for diagnostic ECG equipment cannot be met."* Schiller: *"When using the 25 or 40 Hz filter, the displayed or printed ECG does not always meet the requirements of a diagnostic ECG."*

**(3) Encode gain in the calibration pulse shape, not only in text.** Philips: *"If the calibration pulse is square, the precordial leads and limb leads were recorded at the same scale. If the calibration pulse is stepped, the precordial leads were recorded at half the scale of the limb leads."* Table 4-6 maps each pulse glyph to a limb/precordial mm/mV pair, and off-standard gain *additionally* prints the text `Non-standard lead gains` in the Report Information block — belt and braces.

GE defines the pulse precisely: *"Each calibration pulse represents 1 mV of amplitude and 200 ms duration of the waveform"*, and re-emits it whenever speed, gain or filter change mid-recording.

**(4) Print the algorithm version.** Philips: `PH100B` or `PH110C`, with `C` appended when Critical Values is enabled and `L?` when lead-reversal detection fired and was overridden by the operator; pacing state prints as `P?` / `P` / `PM`. GE prints an encoded 12SL version number that combines the algorithm version and a product code, decodable via an appendix table: *"This number appears on the ECG report printed by the analyzing electrocardiograph."* **This is reproducibility infrastructure** — without it, a report from three years ago cannot be re-derived.

---

## 9. Published accuracy data — honestly reported

### 9.1 The overriding caveat

**Almost every accuracy figure a vendor publishes is a self-test.** Philips' tables are in its own Physician's Guide appendix; GE's are in its own Statement of Validation; Contec's and Biocare's are in their own manuals. **No head-to-head peer-reviewed study comparing DXL vs 12SL vs Glasgow vs VERITAS diagnostic-statement accuracy was located.** Philips' own guide says it best in the mirror-image case, and Physio-Control states it explicitly: *"Sensitivity and specificity for STEMI should not be compared between different ECG interpretive programs unless testing was done with the same 12-lead ECG data set."*

Also note: **IEC 60601-2-51 binds measurement accuracy, not interpretive accuracy.** GE's validation document explains the clause structure — 100 biological CSE ECGs, acceptance limits of mean difference ±10 ms / SD 15 ms for P duration, ±10/10 for PR, ±10/10 for QRS, ±25/30 for QT. There is **no equivalent binding numeric acceptance standard for diagnostic statement accuracy anywhere.** (The clause numbers and limits here come from GE's published summary; the standard itself is paywalled and was not read directly — flagged as such.)

### 9.2 Philips DXL (vendor self-published)

PH110C, Rev J Appendix D — Overall Adult accuracy **95%** (Common Rhythms 97, Conduction Defects 98, Hypertrophy 95, Ischemia/Infarction 91); Overall Pediatric 91.

Adult rhythms, n=1785, as sens/PPV/spec/accuracy: SR 97/98/93/96 · 1° AVB 78/73/98/96 · sinus tachy 91/88/98/97 · VPCs 84/80/98/97 · APCs 74/73/98/96 · AFib 85/83/99/98. Conduction: RBBB 81/96/100/99 · LBBB 90/70/98/98. Hypertrophy: LVH 86/75/94/93 · **RVH 53/55/99/98**. Infarcts, n=2921: Acute MI 75/92/99/96 · **"Acute MI Critical Value" 68/96/100/95** · Anterior MI 83/98/98/91 · Inferior MI 86/93/94/90.

Culprit vessel given STEMI: LAD 98/95/97/98 · **LCx 50/92/99/93** · RCA 97/88/88/93 · LM/MVD 85/90/99/97 · **proximal LAD 32/86/98/83**.

Extra leads change things materially: **RV infarct sensitivity rises from 0% (12-lead) to 69% (+V4R) to 76% (+V5R/V4R/V8/V9)**; posterior MI from 54% to 75% (+V8).

**The generational jump is large and should temper any confidence in older figures:** PH100B (Ed. 2, Appendix E) reports Acute Inferior MI sensitivity **0.37** and Acute Anterior MI **0.61**.

Validation databases are named: Long Beach Memorial ED 2003–2004 (268 acute-MI patients + 266 matched controls) for culprit vessel; a Spanish prehospital set of 111 patients (2008–2010) with angiographic single-vessel ≥70% stenosis confirmation; 424 expert-annotated pediatric records from a series of 4,000, *"not used in the development of the algorithm"*, plus 1,112 consecutive pediatric ECGs overread by two pediatric cardiologists; Dalhousie body-surface-map superset (705 subjects, 670 after exclusions) for Selvester MI-size scoring, 94% correlation vs two experts (95% CI 93–95%).

### 9.3 GE 12SL

GE's is the only **formal regulatory-reviewed** validation document in this comparison: *"The Statement of Validation and Accuracy is considered official product labeling and is reviewed by the Food and Drug Administration (FDA) and the International Electrotechnical Commission (IEC)"* ([Statement of Validation, 416791-003 Rev B](https://www.numed.co.uk/documents/download/216)). Statements are typed per the Tenth Bethesda Conference: **Type A** (anatomic/pathophysiologic — validated against CATH/ECHO/enzymes), **Type B** (electrophysiologic — validated against physician-read ECG databases), **Type C** (purely descriptive, unverifiable independently).

Rhythm, 4 hospitals, 69,957 ECGs: Sinus 98.2/85.5/98.3 (sens/spec/PPV) · AFib 89.0/99.4/91.9 · **Ectopic atrial rhythm 35.2/99.7**. NY Presbyterian 2005, 4,297 ECGs, 2 cardiologists: Sinus 98.7/90.1/99.0 · AF 90.8/98.9/84.7 · Atrial flutter 61.0/99.9/83.3 · **Atrial tachycardia 2.8/99.9/25.0** · PACs 64.2/99.5/87.2 · PVCs 82.7/99.1/80.2.

Healed MI vs CATH, 1,140 ECGs (734 MI): all MI-indicating statements 70/92/94; **excluding "cannot rule out"/"possible" modifiers 54/98/98** — a clean demonstration of what hedging buys and costs. GE notes the physician comparator had similar sensitivity (69%) but higher specificity (97%).

STEMI, MITI trial, 1,189 prehospital ECGs: vs enzymes alone 52/98.5/94; vs enzymes + ST elevation 71/98.5/94. **ED vs enzymes (n=103): sensitivity 32%.** Same cohort vs cardiologist STEMI call: 71/98/98.

Signal quality has a measurable, monotonic effect: 95.4% of ECGs green lead quality, 4.3% yellow, 0.3% red, with **edited interpretations rising 3.9% → 7.4% → 12.1%** across those tiers.

### 9.4 Glasgow

Measurement accuracy vs CSE, mean diff / SD in ms with IEC limits bracketed: P duration 1.348 [10] / 8.501 [15]; QRS 1.609 [10] / 6.354 [10]; PR 1.043 [10] / 6.747 [10]; QT 0.602 [25] / 9.669 [30] ([CinC 2005](https://cinc.org/archives/2005/pdf/0451.pdf)).

Prehospital STEMI, four studies compiled by Physio-Control (LIFEPAK 15, Glasgow v27.0): Tucson 2004 (n=1220) spec 98.5% · Tucson 2007 (n=300) sens 89% · Denmark/Clark 2010 (n=912) sens 78%/spec 94% · Los Angeles/Bosson 2017 (n=44,611) sens 92.8%/spec 98.7% ([Stryker clinical overview](https://www.stryker.com/content/dam/stryker/ems/resources/clinical-information/glasgow_program_clinical_overview.pdf)). **A dissenting AHA abstract (Circulation 2016;134:suppl 1:17782) reports the Glasgow algorithm was "not specific" for prehospital suspected STEMI.**

**Glasgow has no per-statement accuracy table in this comparison.** The Physio-Control "Statement of Validation and Accuracy" (doc 3302436.A, 32 pp.) exists but is paywalled and was not retrieved. **UNVERIFIED.**

### 9.5 VERITAS

VERITAS publishes a full validation chapter with named database sizes: 558 adult 12-lead ECGs; 553 pediatric 15-lead; a further 568 consecutive ECGs to strengthen sinus/AF/flutter; ~1,300 pediatric 15-lead for hypertrophy (1,174 after exclusions), read blind by a cardiologist into No/Possible/Definite RVH then LVH; 69 paced ECGs plus ~7,000 to measure false-positive pacing calls, normalised to 1% prevalence.

Rhythm (sens/spec/PPV/NPV %): Sinus 97.2/95.8/99.5/78.6 · AFib 91.7/99.0/87.0/99.4 · Atrial Flutter 82.4/99.4/58.3/99.8 · High-degree AV block 71.4/100/100/99.8 · **Ventricular preexcitation 42.9/100/100/99.2** · VPCs 96.7/98.8/81.9/99.8 · Ventricular Electronic Pacemaker 98.0/100/96.1/100.

### 9.6 Schiller, Contec, Biocare

**Schiller** publishes agreement-based data: >50,000 ECGs in development, ~3,000 expert-validated for performance; a 618-recording test set (242 Basel patients, 126 Swiss conscripts aged 18–22, 250 CSE) with *"Total number in agreement: 617."* AMI detection is more sobering: PREMISE cohort n=448 (CK-screened) sens 0.67/spec 0.99/PPV 0.97/NPV 0.92; **APACE cohort n=235 (troponin-screened) sens 0.47**, which Schiller itself attributes to AMIs *"not showing any significant ST elevation and depression within the single ECG."* Against combined CSE referees on 1,220 cases, *"Total agreement: 75.33%."*

**Contec is the most granular disclosure of any vendor here — and the least flattering.** Per-item sens/spec/PPV for all 60 items against CSE + 549 in-house Asian cases. Highlights: `No abnormality` n=585, 92.01/79.16/97.38 · Sinus bradycardia n=191, 96.68/99.73/98.64 · **Left atrial hypertrophy sens 51.09%** · **Right atrial hypertrophy sens 42.64%, PPV 50.00%** · **LVH n=236, sens 41.37%** · **RVH sens 39.75%** · **item 22 "Possible acute anteroseptal MI" n=27, sens 16.67%** · **item 43 "Possible acute inferolateral MI" n=29, sens 11.11%**. Many ischaemia items have PPV 33–55%. Contec also states its intended population (*"Adolescents and adults, age range: 12–87"* — no pediatric claim) and explicitly excludes posterior ischemia/MI from its accuracy verification.

**Biocare** publishes CSE (n=1220, Race: White, age 52±13): Normal 92.7/73.9/61.8 · LVH 60.1/97.0/77.7 · **RVH 32.7/99.9/92.3** · Anterior MI 80.6/97.7/85.1 · Inferior MI 67.0/97.8/89.7. Rhythm database (n=4500, Race: Yellow, age 48±12): Sinus 98.0/91.1/97.9 · PVCs 87.2/98.9/81.2 · AFib 89.6/98.7/91.0 · **Atrial flutter 65.3/99.9/88.9**. Biocare is admirably candid: *"Test with CSE database, but this database doesn't have sufficient number of acute myocardial infarction and myocardial ischemia ECG"*, and lists grade II/III conduction block as absent from the test set.

**EDAN submitted no clinical data at all.** K160876's Performance Data section lists biocompatibility, electrical safety/EMC, IEC 60601-2-25 bench testing, software V&V and battery testing, then: *"Clinical data: Not applicable."* No sensitivity/specificity for SEMIP or for the Glasgow option appears anywhere ([K160876](https://www.accessdata.fda.gov/cdrh_docs/pdf16/K160876.pdf)).

**BPL and Dawei publish no accuracy data whatsoever**, and no peer-reviewed or vendor validation study of any BPL Cardiart automated interpretation — in India or elsewhere — was found.

### 9.7 The independent literature — what it actually says

This is the part to read before making any marketing claim.

- **CSE / NEJM 1991** (9 programs vs 8 cardiologists, 1,220 validated cases, 7 disorders): *"The median total accuracy level was 6.6 percent lower for the computer programs (69.7 percent) than for the cardiologists (76.3 percent; P<0.001)"*, though *"the performance of the best programs nearly matched that of the most accurate cardiologists"* ([NEJM](https://www.nejm.org/doi/full/10.1056/NEJM199112193252503)). **Caution:** AHA Part I cites a *different* CSE metric (91.3% vs 96.0% correct classification). These are not interchangeable.
- **Seven-program head-to-head, >2,000 ECGs replayed through seven real carts** ([J Electrocardiol 2019](https://www.sciencedirect.com/science/article/pii/S0022073619306120)): false-positive rates 2.1–5.5% (non-sinus), 0.7–4.4% (AF/flutter), 1.5–3.0% (other abnormal rhythms); **false-negative rates 12.0–7.5%, 9.9–2.7%, and 55.9–30.5%** respectively. ACS flagging varied by a factor of 2.5. **Agreement between programs and majority reviewer decisions: 46–62%.**
- **Interval measurement head-to-heads** (Kligfield et al., [AHJ 2018](https://www.amps-llc.com/uploads/2019-1-16/Kligfield%20et%20al%20AHJ%202018.pdf), 7 algorithms, 800 ECGs; and AHJ 2014, 4 algorithms, 600 ECGs): pairwise differences are small in normals (PR 0.2–3.6 ms, QRS 0.1–8.1 ms, QT 0.1–9.3 ms) but **widen substantially in abnormal repolarization** — in LQTS patients up to 13.3 ms for QRS and 12.8 ms for QT. Encouragingly, the maximum mean QT difference between algorithm pairs in the long-QT population **fell from 18 ms (2014) to 10–12 ms (2018)**.
- **Errors concentrate in rhythm, not measurement.** Guglin & Thatai (2,072 ECGs): significant computer-vs-cardiologist disagreement in **9.9% of all ECGs, 15.9% of abnormal ones**, of which *"errors in diagnosis of arrhythmia, conduction disorders and electronic pacemakers accounted for 178 cases, or 86.4% of all errors"*; and *"Computer ECG diagnosis of life threatening conditions e.g. acute myocardial infarction or high degree AV blocks are frequently not accurate (40.7% and 75.0% errors, respectively)"* ([PMID 16321696](https://pubmed.ncbi.nlm.nih.gov/16321696/)).
- **Shah & Rubin** (2,112 ECGs): rhythm correct in 88.0% overall, **95.0% for sinus but only 53.5% for non-sinus** ([PMID 17531257](https://pubmed.ncbi.nlm.nih.gov/17531257/)). This is the canonical citation for why rhythm statements must be overread.
- **Real-world overread modification rate** (159,630 ECGs, 104 physicians, GE 12SL v16–23, 2011–2023): **31.3% of automated reports were modified**, falling from 42.2% (2011–12) to 18.4% (2023). Terms most often *deleted*: anterior infarct (44.6% deletion rate), inferior infarct (32.0%), pacemaker terms up to 92.1% ([PMC12821064](https://pmc.ncbi.nlm.nih.gov/articles/PMC12821064/)).
- **Contemporary single-device audit** (Frontiers Physiol 2025, 526 ECGs, Spacelabs CardioExpress SL12): **39.5% incorrectly interpreted**; among 193 abnormally interpreted cases, 58.0% involved false-negative components. The authors' own caveat: *"an analysis of automatic ECG interpretations made by a single device from a particular manufacturer with a single algorithm"* ([PMC12137353](https://pmc.ncbi.nlm.nih.gov/articles/PMC12137353/)).
- **The "Normal ECG" line as a rule-out — a genuine conflict in the literature.** WestJEM 2024 (2,275 triage ECGs, GE 12SL) found *"a triage ECG with a computerized interpretation of 'normal' or 'otherwise normal' ECG had a negative predictive value of 100% for STEMI (one-sided, lower 97.5% CI 99.6%)"* ([PMC10777178](https://pmc.ncbi.nlm.nih.gov/articles/PMC10777178/)). But McLaren et al. (Acad Emerg Med 2024, 7-year retrospective, two urban academic EDs) found **~4% of true-positive Code STEMI activations had an initial ECG labelled "normal" by the computer**, many diagnostic of occlusion MI ([doi:10.1111/acem.14795](https://onlinelibrary.wiley.com/doi/10.1111/acem.14795)). **Safe reading: high but not absolute NPV; never use the "Normal" line to defer physician review in chest pain.**
- **Do not cite the Ioannidis 2001 figures as computer accuracy.** Sensitivity 76%/specificity 88% for acute cardiac ischemia and 68%/97% for AMI are frequently reproduced as "computer ECG accuracy." The primary meta-analysis (11 studies, 7,508 patients) evaluated *out-of-hospital ECG diagnosis generally* — a mix of physician and computer reading — not an algorithm benchmark ([doi:10.1067/mem.2001.114904](https://doi.org/10.1067/mem.2001.114904)).

---

## 10. Common practice CardioX does not yet do

**Basis and limitation:** I know two things about the CardioX/RhythmUltra report — it prints a box headed **"PROBABLE CONCLUSION"**, and it **does** print criteria. Everything else below is a checklist of near-universal vendor practice; rows marked ⚠️ are *assumed absent* and should be struck if you already have them. This is a gap list, not an audit.

| # | Common practice | Who does it | Why it matters | CardioX status |
|---|---|---|---|---|
| 1 | **A single overall severity line from a fixed, published, ordered vocabulary** (`Normal / Otherwise Normal / Borderline / Abnormal / …`), selected as the most-severe single statement | Philips (6), GE (4), Glasgow (6), VERITAS (8), Schiller (5), Biocare (5), AHA standard (4) | "PROBABLE CONCLUSION" is a *header*, not a classification. Every buyer, every EMR integration and every audit expects a machine-readable severity token | ⚠️ Assumed absent |
| 2 | **Per-statement severity codes in the library**, so the overall line is derived, not hand-assigned | Philips (NS/NO/ON/BO/AB/DE), GE (N/O/B/A/NA/`*`), Glasgow (summary codes 1–6) | Without it, the severity line is unmaintainable as the library grows | ⚠️ |
| 3 | **A published statement library with stable codes** and a documented category grouping | Philips (605 codes / 43 categories), GE (496 / banded 1–1699), Glasgow (346 / 21 groups), Biocare (~216 / 9), Contec (60) | Codes are what make serial comparison, MIS integration and regression testing possible. Free-text strings are not | ⚠️ |
| 4 | **A documented statement-selection rule** — one statement per category, later findings suppress earlier ones, and named findings bypass whole later categories | Philips (verbatim, unchanged 2009→2025), GE ("last valid statement supplants"), VERITAS (same) | Prevents contradictory lines on the same report (e.g. LBBB *and* LVH *and* left axis) | ⚠️ |
| 5 | **A cap on rhythm output** — one dominant rhythm + ≤3 supplementary | Glasgow (explicit) | Stops a noisy 10 s strip generating a wall of rhythm text | ⚠️ |
| 6 | **A closed hedging lexicon with defined confidence** (`Cannot rule out` / `Possible` / `Consider` / `Consistent with`) reused across all territories | Schiller (with published ≈15/35/50/80% values), GE (`PO`/`CRO` fragments), Biocare (3×4 certainty×age grid), Glasgow | Ad-hoc hedging wording is the fastest way to lose clinician trust. Schiller's numeric lexicon is a genuine differentiator you could copy | ⚠️ |
| 7 | **Criteria suppressed on the confirmed record** — visible pre-overread, gone once a physician signs | Philips (explicit) | You already print criteria. This is the mature version of the feature | ⚠️ Likely absent |
| 8 | **An "Unconfirmed / requires physician overread" label printed on the report**, ideally institution-customisable | Philips, GE, Mortara, Schiller, EDAN, Cardioline, LIFEPAK 15 | This is the single strongest convention in the industry and rests on AHA Part I: *"all computer-based reports require physician overreading."* Nothing else on this list is as important | ⚠️ **Highest priority if absent** |
| 9 | **A confirmed/unconfirmed record state**, with the confirming physician's name printed once signed | GE (`Confirmed`/`Reviewed by`), Mortara, Cardioline (`CONFIRMED by xxxx on xx/xx/xxxx`) | Turns the banner from decoration into workflow | ⚠️ |
| 10 | **Technical-quality statements in the same block as diagnostic statements**, able to force a severity | Philips (`Defective ECG`), Glasgow (`Technical error`, `--- Technically unsatisfactory tracing ---`), GE (`*** POOR DATA QUALITY…`), AHA Part II Category B | A bad trace must announce itself in the conclusion, not silently degrade it | ⚠️ |
| 11 | **Lead-reversal detection with a printed statement** — the standard *requires* this | AHA Part I (verbatim recommendation), Philips (`RALARV`, `PEERV`, `L?` flag), Glasgow, GE, Biocare (`LIMB LEADS REVERSED`) | AHA notes precordial misplacement alters diagnostic statements in **up to 6%** of recordings | ⚠️ |
| 12 | **Explicit statements when age/sex are missing**, rather than silent defaulting | Glasgow (`--- Interpretation made without knowing patient's age ---`), Philips (`Gender not entered, assumed to be male…`), Mortara (`INTERPRETATION BASED ON A DEFAULT AGE OF 40 YEARS`) | Makes an unsafe assumption visible on the page | ⚠️ |
| 13 | **Genuine age- and sex-parameterised criteria** with a documented adult/pediatric split | Philips (≥16 adult, 12 pediatric bands), GE (≥16, Davignon 12 groups), Glasgow (continuous equations, neonates by *days*), VERITAS (≥16/≤15), Biocare | Sex- and age-specific STEMI criteria are in the 2007/2012/2019 Universal Definitions. Non-parameterised thresholds are now below standard of care | ⚠️ Verify |
| 14 | **Critical-value banner in a visually distinct delimiter**, derived by rolling up existing statements | Philips (`>>>> Acute MI <<<<`), GE (`*** Critical Test Result:` as first line), Glasgow (7 × `*** … ***`), VERITAS (`***ACUTE MI***`) | If added, use it honestly — the seven-program study found **>50% false-negative for ACS in every program** | ⚠️ |
| 15 | **Age-adjusted rate thresholds** for extreme tachy/brady, not fixed cut-offs | Philips (HR − age ≥ 150), Glasgow (age-banded) | A fixed 150 bpm cut-off is wrong for a 6-year-old and wrong for an 80-year-old | ⚠️ |
| 16 | **Confounder gating on QTc / STEMI flags** (no LBBB/RBBB/pacing, QRS < 120–140 ms, HR limits) | Glasgow, GE v23, Philips (`Prolonged QTc Probably Secondary to Wide QRS Complex`) | The cheapest available false-positive reduction | ⚠️ |
| 17 | **Global onset-to-offset interval measurement across all 12 leads** | Philips, GE, Glasgow, VERITAS, Schiller — and **AHA Part I requires it** | Single-lead intervals are not standards-conformant | ⚠️ Verify |
| 18 | **QTc formula named on the report**, ideally selectable | Philips (up to 4, formulae published), EDAN (5), Biocare (4, default Hodges), Mortara (3) | Defaults differ across vendors; an unlabelled QTc is uninterpretable across devices | ⚠️ |
| 19 | **Filter/bandwidth, gain and speed printed in a fixed page region** | Philips (lower-right filter box, e.g. `60~ 0.05-150 Hz`), GE, Mortara (bottom right), Schiller (lower edge) | Universal. Cheap. Absence is immediately noticed by any cardiologist | ⚠️ Verify |
| 20 | **A printed note that the display/print filter is not the analysis bandwidth** | Philips (*"the interpretive algorithms always receive, store, and analyze data at 0.05 to 150 Hz"*), Mortara, Schiller | Directly prevents a real misreading | ⚠️ |
| 21 | **An automatic alert when a 40 Hz cutoff is selected** | AHA Part I recommends it explicitly; Mortara and Schiller print the warning in the manual | Standards-mandated and almost nobody implements the *alert* — a differentiator | ⚠️ |
| 22 | **Calibration pulse encoding non-standard gain by shape**, plus a text flag | Philips (square vs stepped pulse + `Non-standard lead gains`) | Belt-and-braces against a whole class of amplitude misreadings | ⚠️ |
| 23 | **Algorithm version printed on every page**, with flags for enabled options | Philips (`PH110C`, `C`, `L?`, `P?`/`P`/`PM`), GE (encoded 12SL version + decode table) | Without it, a report cannot be reproduced or a field issue scoped | ⚠️ |
| 24 | **A published Physician's Guide / criteria handbook** | Philips (222 pp.), GE (268 + 334 pp.), Glasgow (85 pp.), VERITAS, Schiller, Contec (Appendix I), Biocare (Appendix D/E) | **AHA Part I requires it:** *"Programs using complex diagnostic algorithms should document in reference material those measurements that are critical to the diagnostic statement."* BPL, Dawei and EDAN do not do this — publishing one puts CardioX **above** its nearest regional competitors | ⚠️ **High-leverage** |
| 25 | **Published per-condition sensitivity/specificity/PPV against a named database** | Philips, GE (FDA/IEC-reviewed), VERITAS, Schiller, Contec (per-item), Biocare (per-category) | IEC 60601-2-51 asks manufacturers to report these per diagnostic category. Contec and Biocare do it and neither is a premium vendor — the bar is not high | ⚠️ |
| 26 | **A configurable low-acuity / borderline statement suppression mode** | Philips (Exclude Low Certainty / Exclude ALL), GE (Screening/Hi-Spec), Schiller (Sensitivity High/Low), Philips Rev J (Low Sensitivity Acute MI for EMS) | Lets one device serve both a cardiology clinic and a screening camp | ⚠️ |
| 27 | **Serial comparison against a prior ECG**, with change statements | GE (own library groups; overread edits fall *"by as much as 76%"*), Glasgow, AHA Part II (6 codes with numeric criteria) | AHA Part I: *"Serial comparisons of sequential ECGs should be done by trained observers regardless of whether the ECG program provides a serial comparison"* | ⚠️ Likely absent |
| 28 | **A frontal-plane ST-segment axis in the header** | **No vendor found doing this** | AHA Part I explicitly recommends it. Genuinely unclaimed ground | ⚠️ Opportunity |

**If only three things get done:** #8 (overread banner), #1 (severity line from a fixed vocabulary), #24 (publish a criteria handbook — you already generate the criteria, so this is largely a documentation exercise, and it would immediately put Deckmount ahead of BPL, Dawei and EDAN on the one axis the standard actually asks for).

---

## 11. Register of corrections, unverified items, and known gaps

### 11.1 Claims corrected during verification (do not repeat the originals)

| Original claim | Status | Corrected |
|---|---|---|
| Philips DXL prints statements in fixed order rhythm → adult morph → ped morph → technical quality | **Refuted** | That sentence describes the *2003 predecessor manual's appendix organisation*, not report output. DXL Ed. 2 / Rev J drop it and put Technical Quality second, interleaving pediatric with adult by topic. **No Philips source documents report print order.** |
| Philips DXL library ≈654 codes / ~40 categories | **Refuted** | **605 codes / 43 categories.** The inflated count swallows ~66 legacy alias codes from the adjacent Notes column. "Over 600 interpretive statements" is marketing copy, not guide text |
| GE 12SL v23 library ≈404–489 statements | **Refuted** | **Exactly 496** (v17–20: exactly 225). The v23 table is number-first; the count is unambiguous, not wrap-defeated |
| 12SL v23 cleared July 2014; K141963 is the MAC VU360's predicate | **Refuted** | K141963 **submitted** July 2014, **cleared 5 Feb 2015**. K173830 (MAC VU360, cleared 18 Sep 2018) has a **single predicate: Mortara ELI 380, K142105**. The MAC 5500 HD (K073625) and 12SL v23 (K141963) are **reference** devices. The predicate/reference distinction is legally meaningful |
| Glasgow library ≈370 lines / 357 unique | **Refuted** | **355 lines (354 net), 346 unique, 21 groups** |
| That Glasgow count is BPL's library | **Refuted** | The counted document is the **corpuls3** OEM edition; "BPL"/"Cardiart" appear **zero times** in it. BPL's shipped Glasgow build is unknown |
| BPL Cardiart 9108/9108D = EDAN SE-1200 Express | **Refuted** | 9108 ≈ SE-12/SE-1200; 9108D ≈ SE-1201. Shared 24-bit / 0.01–300 Hz / 16000 Hz figures are series-wide and distinguish nothing. No OEM relationship confirmed by any primary source |
| BPL's nearest overread mechanism is only a confirm/not-confirmed status line | **Refuted** | The EDAN **SE-1200 Series** manual documents a literal printed `Unconfirmed Report` banner via the `Prompt` setting |
| CMS Ch. 12 requires a separate physician report; this is why UNCONFIRMED is printed | **Refuted** | It is **Ch. 13 §100.1** (per 42 CFR 415.120(a)); CMS does not require a separate document; and reimbursement is **not** the origin of the banner |

### 11.2 Explicitly UNVERIFIED

- **Philips:** whether race is used *internally* as a criterion (it is captured and printed as a demographic field, but no criterion is documented as using it). The "thirty statements roll up into four Critical Values" prose vs the ~43 enumerated codes — unresolved. Exact on-page typography, indentation and line-wrap rules. The K132068 510(k) summary (HTTP 404 on fetch).
- **GE:** the literal *printed* critical-value string on a MAC VU360 (only on-screen dialogs are documented). Whether base 12SL can print reasons at all (no such setting found in MAC 5500 or VU360 manuals — suggestive but not proof). Statement library beyond v23.
- **Glasgow:** per-statement accuracy tables (Physio-Control doc 3302436.A, paywalled). Current version number and version history. On-page geometry (deliberately delegated to the licensee).
- **Schiller:** whether it prints reasons per statement; its statement library size; whether the AT-102 G2 still prints Sokolow.
- **EDAN:** the full SEMIP statement library (only three subsets published; no total anywhere). What the licensed Glasgow option *changes* on an EDAN printout — the published appendices describe SEMIP, so a Glasgow-enabled cart may print wording the manual never documents. Whether SEMIP uses race.
- **Contec:** exact **English** strings for the 60 items (verified in the Italian edition; the official English GIMA M33224EN was blocked from automated retrieval).
- **BPL:** essentially everything about the printout — layout, conclusion block position, statement wording, statement count, severity line existence, overread text, measurement block, Glasgow build/version, whether a race field is exposed, and the engine on the 9108 / 8108 View / 6208 View Plus / GenX 12i.
- **Dawei:** essentially everything, as above. No FDA 510(k) exists for any Dawei electrocardiograph.
- **AHA Parts III–VI:** full text not retrievable (HTTP 403 on ahajournals.org and sciencedirect.com). This means Part IV's sex-specific QT thresholds (commonly quoted as ≥450 ms men / ≥460 ms women), Part V's LVH voltage criteria and Part VI's ST-elevation thresholds are **second-hand only**. Only Part I's parent requirement — *"stratification for specific age groups, sex, and race"* — is verified verbatim.
- **IEC 60601-2-51 itself** is paywalled. All clause numbers and numeric tolerances here come from GE's published summary of it, not the standard's own text. Whether the standard imposes any requirement on *interpretive-statement* accuracy (as opposed to measurement accuracy) is **inference from a single vendor summary**.
- **Schläpfer & Wellens, JACC 2017** — the standard narrative review — abstract only; its internal STEMI misinterpretation figures are second-hand via a 2025 Frontiers review.

### 11.3 What no source could establish, for anyone

- **No head-to-head peer-reviewed comparison of diagnostic-statement libraries or accuracy across Philips DXL, GE 12SL, Glasgow and VERITAS.** The three genuine head-to-heads compare rhythm/ACS classification and interval measurement, not statement lexicons.
- **No published comparison of report *layout*** (as opposed to accuracy). All layout evidence in §1 and §8 comes from vendor manuals.
- **No standards document specifying critical-value flag wording.** AHA Parts I and II were searched in full: zero hits for asterisk banners, STAT syntax, or urgent-flag conventions.
- **No sample printout was obtained** for BPL, Dawei, EDAN, Contec or Biocare. Every layout claim for those five is from settings tables and appendices, not from a scanned report.