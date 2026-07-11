# Frontend button-by-button audit — 2026-07-12

Method: full interactive walk of every page/button against `openmc2donjon serve --mock` (browser), plus a 68-agent code audit (9 scoped auditors → dedupe → 1 adversarial verifier per finding). 72 raw → 58 deduped → 54 confirmed, 3 refuted, 1 verifier lost to an API drop (its finding is included below marked UNVERIFIED).

Live-reproduced in the browser during the walk: the /convert "Output ready" contradiction (Refresh does not clear it), the /builder file dialog hiding all selectable files ("3 non-input file files hidden"), the file-browser dead parent/breadcrumb after a 404 listing (network trace shows no request fired), the demo preview ENERGY=MISSING vs "ADF 9/4f + SPH 9" contradiction, and the /inspect path-echo mismatch.

## Bugs (user-blocking or self-contradicting) — 12

### BUG-01 `src/openmc2donjon/web/convert.py:501`

Mock /api/convert claims it wrote an ASCII output (output_exists=true, 184,320 bytes, summary_written=true) at paths absent from the mock file tree, so the /convert 'Output ready' panel simultaneously asserts the artifact exists and that it is missing, in at least three co-rendered places, and 'Refresh file status' can never resolve the contradiction.

**User impact:** In the demo's happiest path (mock convert with defaults), the same screen tells the user the DONJON artifact exists, that it is not present yet, that the preview cannot be opened, and shows the opened preview — with 'output: missing' chips directly beneath the 'artifact ready' badge. Clicking the offered Refresh button changes nothing, making the product look broken at the exact moment it claims success.

**Evidence:** convert.py:501-527 defaults output to /mock/home/openmc-runs/c5g7/handoff.mcompo.txt and hard-codes response["output_exists"] = not dry_run, output_size=184_320, summary_written=True; but _MOCK_TREE lists c5g7 as only [handoff.h5, handoff_aug.h5, bundle, README.md] (files.py:29-40), so _mock_file_status returns exists=False/kind "missing" (files.py:247-253). UI contradictions: (1) convertOutputMode.ts:6 picks 'converted' from the response alone, so OutputActions.tsx:332-338 renders "The DONJON-facing ASCII handoff exists." + 'artifact ready' badge while the sibling status line OutputActions.tsx:341 renders convertArtifactStatus.ts:92 "ASCII output is not present yet; preview and bundling wait for conversion."; (2) the ASCII action card gates on the probe (OutputActions.tsx:748-750 outputKnownMissing) and renders "The output file was not confirmed, so the preview cannot be opened yet." (768-778) with a 'waiting' span, while ConvertReport.tsx:102-106 renders a fully populated AsciiPreview below it (mock text-preview synthesizes content for any path, text_preview.py:37-38, 87-100); (3) inside 'Advanced delivery evidence', convertAsciiReadiness.ts:84-94 renders "Conversion returned, but the ASCII file is not confirmed" and DeliveryCommandPanel (OutputActions.tsx:550-552, 574-585) renders "Delivery waits for a confirmed ASCII file" under the parent header claiming the handoff exists. 'Refresh file status' (OutputActions.tsx:342-348) re-fetches the same static tree, so the contradiction persists. The mock default also ignores the input directory (live mode derives output from input_path.with_suffix, convert.py:295-297). Fix: add the claimed outputs to _MOCK_TREE's c5g7 entry and derive the mock default output from the input path.

**Verifier nuance:** Minor nuance only: contradictions (2) and (3) — the "preview cannot be opened yet"/"waiting" card, "not confirmed" readiness panel, and "Delivery waits for a confirmed ASCII file" — sit inside the collapsed "Advanced delivery evidence" <details> (OutputActions.tsx:418-429), so they require one click to expose; contradiction (1) in the header block is unconditional as claimed.

### BUG-02 `src/openmc2donjon/web/text_preview.py:137`

The mock ASCII artifact contains no ENERGY, ADF/HADF, NSPH, CALCULATIONS, TREE, ISOTOPESLIST, or STRD records yet is served as the complete file, so the preview UI brands ENERGY 'MISSING' and scores equivalence blocks 0/4 while the sibling validation summary on the same page claims 'ADF 9/4f + SPH 9'.

**User impact:** Demo users watch the converter claim full ADF+SPH equivalence carriage and then open a 'complete' preview that visibly lacks every equivalence block, with ENERGY flagged MISSING in red — the mock demo actively communicates that the converter drops the equivalence data, contradicting the product's central physics claim.

**Evidence:** _mock_ascii_preview_text (text_preview.py:137-173) emits only SIGNATURE/GLOBAL/STATE-VECTOR/MIXTURES/NTOT0/NUSIGF/NJJS00/IJJS00/SCAT00, and _mock_text_preview (text_preview.py:87-100) sets file_size=len(text) so truncated=false. The UI then asserts incompatible things at once: AsciiPreview.tsx:112 shows 'complete within preview limit'; asciiPreview.ts:135-138 marks 'Energy grid' status 'missing' with the provably false excuse 'ENERGY was not visible in this preview slice.'; mock preflight (convert.py:552-554: adf_mixtures 9, sph_calculations 9) drives ConvertReportShared.ts:203-206 to render 'ADF 9/4f + SPH 9' while expectedArtifactBlockCoverage scores Equivalence 0/4. Real writers always emit these blocks (multicompo.py:421, :501, :517, :556-558, :602; macrolib.py:151, :230, :391-393). The SPH fixture even claims macrolib_ascii_nsp_block_count=33 for a file whose mock preview shows zero NSPH blocks; the mock STATE-VECTOR is hardcoded to 9 mixtures / 7 groups even when the reader guide says 2 mixtures / 33 groups; preview file_size (~1.4 KB) contradicts the convert response's output_size 184,320 rendered by HandoffPipeline.tsx:160.

**Verifier nuance:** Accurate as described, with one scoping note: the defect exists only in --mock demo mode (which the UI does label as mock); real conversions read the actual output file, which the writers (multicompo.py, macrolib.py) populate with ENERGY/ADF/NSPH, so live-mode previews are consistent.

### BUG-03 `src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json:20`

The mock SPH physics-summary fixture lists every handoff artifact under a .../openmc-sph-minicase/handoff/ subdirectory (and mg_case_iterNN dirs) that does not exist in the mock file tree and disagrees with the demo preset's flat paths, so the two same-labeled 'Send corrected MGXS to Convert' buttons on one page target different files and every fixture path 404s in the mock browser.

**User impact:** Following the flagship demo path (SPH summary card -> Convert this handoff) produces a 'successful' conversion decorated with input-missing status chips; the planner form and the summary card directly below it name different canonical paths for the same corrected artifact, and browsing to either fixture path returns 'path not found' — the demo contradicts itself about its own showcase files.

**Evidence:** Fixture lines 20-27: ascii_path "/mock/home/openmc-runs/openmc-sph-minicase/handoff/out_with_openmc_sph.macrolib.txt", augmented_hdf5_path ".../handoff/mgxs_with_openmc_sph.h5", plus mg_case_iter02/iter03 paths (lines 39-41, 260-292); served verbatim in mock mode (openmc_sph_summary.py:35-38). The mock tree is flat — mgxs_with_openmc_sph.h5, out.mcompo.txt, out.macrolib.txt sit directly in openmc-sph-minicase with no handoff/ or mg_case_* entries (files.py:41-54) — so _mock_file_status returns exists=false for every fixture path. The frontend demo preset uses the flat paths that DO exist (openmcSphDemo.ts:40-42), so 'Fill SPH planner' (app/openmc/page.tsx:258-274) fills one path while the loaded summary card's convert link (openmcSphSummary.ts:80-111 via OpenmcSphPhysicsSummaryCard.tsx:134) uses the fixture's handoff/ path; convertArtifactStatus.ts:17 then probes the input and OutputActions renders an 'input: missing' chip under the success panel. Fix: point the fixture's handoff paths at the flat minicase paths in _MOCK_TREE, or add the handoff/ subtree.

**Verifier nuance:** Minor placement nuance only: in the converted (success) state the "input: missing" chip is inside the collapsed "Advanced delivery evidence" details element rather than immediately under the header; the directly visible contradiction on the success panel is the "ASCII output is not present yet; preview and bundling wait for conversion." status line. The defect as described is otherwise accurate.

### BUG-04 `web/lib/openmcSphDemo.ts:74`

The SPH demo prefill puts the already-augmented HDF5 into the 'Intermediate HDF5' field, so 'Plan workflow' plans a second SPH injection into an already-corrected file, derives the doubled-suffix artifact mgxs_with_openmc_sph_sph.h5 that nothing else on the page agrees with, and even plans overwriting the corrected file with a raw export.

**User impact:** A user who clicks 'Fill SPH planner' then 'Plan workflow' gets CLI commands that would double-apply SPH factors and overwrite the demo's corrected HDF5 with an uncorrected export; the plan's Inspect/Convert links point at a file that does not exist and directly contradict the demo card's own step-02 convert link visible on the same screen.

**Evidence:** openmcSphPlannerPrefill returns keepHdf5Path: preset.augmentedH5 = ".../mgxs_with_openmc_sph.h5" (openmcSphDemo.ts:40,57,68-74). Backend _augmented_hdf5 (openmc_workflow.py:611-619) appends _sph to the keep_hdf5 stem -> mgxs_with_openmc_sph_sph.h5; _commands (openmc_workflow.py:436-457) emits augment-sph on the already-corrected file, and the export command writes the raw export over the corrected file (-o = keep path, openmc_workflow.py:482-489). The plan's 'Open converter'/'Inspect HDF5' links use the doubled path (openmcWorkflowWalkthrough.ts:106-116) while the co-rendered demo card step 02 sends the single-suffix file (openmcSphDemo.ts:104-117). The mock filesystem has no mgxs_with_openmc_sph_sph.h5 (files.py:41-53).

**Verifier nuance:** Core defect is real, with two nuances: (1) executing the planned three-command sequence applies SPH only once because the export first overwrites the corrected file with a raw export (double-application occurs only if the user runs the augment step alone against the pre-existing corrected file); (2) the 'Open converter'/'Inspect HDF5' buttons are gated on plan.ok, which is false for the mock preset (empty recipe), so the doubled-path links render only in the live preset — though the doubled path is still shown to both via the plan's command and artifact lists.

### BUG-05 `web/lib/openmcEntryPoints.ts:41`

The 'Open SPH summary' secondary link on the SPH entry-point card is a dead control when clicked on /openmc itself: it links back to /openmc with query params, but page state is read only in useState initializers and never re-synced, so nothing visible changes.

**User impact:** A user on the direct route clicks 'Open SPH summary' and nothing happens except the URL bar changing — the summary card never appears; even on a fresh load the link drops the user at the top of the planner, not at the summary.

**Evidence:** secondaryHref: "/openmc?workflow=two-step&equivalence=sph&format=macrolib" with secondaryLabel: "Open SPH summary" (openmcEntryPoints.ts:41-42), rendered as a plain <Link> (OpenmcEntryPoints.tsx:52-54; component rendered only on /openmc). page.tsx derives workflow/equivalence/format exclusively from useState initializers over searchParams (app/openmc/page.tsx:88-113) with no effect watching searchParams — unlike /builder which re-syncs via useEffect([searchParams, spec]) (app/builder/page.tsx:84-86). Same-route App Router navigation does not remount the page; the SPH summary section renders only when equivalence === "sph" (page.tsx:326). The href also lacks the #openmc-sph-summary anchor its label promises.

### BUG-06 `web/lib/openmcSphDemo.ts:77`

In mock mode the demo's 'Fill SPH planner' flow can never produce a READY plan: the prefill leaves the required Recipe Python field empty and the mock filesystem contains no .py file to browse for.

**User impact:** Every mock-mode user who follows the recommended demo card's primary button and then submits the form gets 'NEEDS INPUT' with 'recipe: Required path is missing.' and no way to satisfy it from the mock file browser — the bundled demo dead-ends at its own happy path.

**Evidence:** recipePath is only set for the live preset: `recipePath: preset.id === "live-openmc-sph" ? "examples/...export_recipe.py" : ""` (openmcSphDemo.ts:77-80). The backend recipe check is required=True unconditionally (openmc_workflow.py:118-125) and plan ok is all(check["status"] != "fail") (openmc_workflow.py:90). The mock tree (files.py:18-62) contains no .py entry anywhere, and the recipe browser filters extensions: ["py"] (app/openmc/page.tsx:795-802), so the browser shows nothing selectable.

**Verifier nuance:** The dead-end applies to the guided flow (prefill + file browser) only: because mock mode sets must_exist=False and a wrong suffix merely warns, manually typing any non-empty path into the Recipe Python field does produce a READY plan — so "can never produce a READY plan" should read "the prefill-plus-browse path cannot produce a READY plan without the user hand-typing a recipe path the demo never supplies".

### BUG-07 `src/openmc2donjon/web/inspect.py:53`

Mock /api/inspect ignores the requested path and returns the canned fixture path, so the inspect result's 'Path' header names a different file than the input field directly above it — a file that is not even part of the mock browser's /mock/home universe.

**User impact:** In mock mode, arriving via any /inspect?path=... link (e.g. OpenmcArtifactList.tsx:58) auto-inspects and shows 'Path /mock/c5g7-shape-handoff.h5' in the result card while the form input above still shows the path the user asked for — two simultaneously rendered elements disagree about which file was read, and the reported file can never be found in the browser.

**Evidence:** inspect.py:52-54: `if mock_mode: return load_fixture("inspect_handoff.json")` — the path argument is unused; fixtures/inspect_handoff.json:3: "path": "/mock/c5g7-shape-handoff.h5", outside the /mock/home tree the mock browser serves (files.py:17-62). Summary.tsx:17 renders {data.path} under the 'Path' header while app/inspect/page.tsx:139 setPath(trimmed) keeps the requested path in the input (page.tsx:225-234). Sibling mock endpoints already echo the request: inspect.py:434 `payload["mixture"] = mixture`, openmc_sph_summary.py:38 `payload["requested_path"] = path`. Fix in the mock backend: copy the fixture and set payload["path"] = path (live mode deliberately returns the resolved real path, inspect.py:327).

### BUG-08 `src/openmc2donjon/web/inspect.py:432`

Mock per-mixture detail never overrides volume/temperature from the canned fixture, so for 5 of the 9 mock mixtures the mixture-meta card shows a volume that contradicts the table row selected right above it.

**User impact:** In the default mock demo, clicking M7_REFL shows 'Volume 96.00' in the roster table and 'Volume 9.600' in the detail card below it at the same time (similarly wrong for M5, M6, M8, M9). A first-time user evaluating the tool sees the UI contradict itself about basic data.

**Evidence:** _mock_mixture (inspect.py:432-449) only overrides mixture, the fission XS family, and the scatter moment; fixtures/inspect_mixture.json has "volume": 9.6, but fixtures/inspect_handoff.json mixture rows have volume 11.4 (M5_MOD), 0.8 (M6_GUIDE), 96.0 (M7_REFL), 1.2 (M8_CLAD), 0.8 (M9_CONTROL). The table renders m.volume.toFixed(2) (MixtureTable.tsx:74-76) and the meta card renders detail.volume.toFixed(3) (page.tsx:507-510) on the same screen. Fix in _mock_mixture: look the mixture up in the handoff fixture and override volume, as is already done for mixture and fissionability.

**Verifier nuance:** Minor framing fix: mock mode is opt-in via `openmc2donjon serve --mock`, not the app's default; within mock mode the contradiction is exactly as described (also affects Temperature in principle, but the table doesn't display temperature so only Volume is visibly contradictory).

### BUG-09 `web/lib/commandBuilder.ts:68`

Every file-Browse dialog on /builder filters out all target files because builder specs define extensions with leading dots while FileBrowserModal expects them without.

**User impact:** Clicking Browse on any path field in any of the 14 command builders shows only directories plus 'N non-input file files hidden' — no file can ever be selected, so the Browse buttons are effectively dead on /builder and users must type every path by hand. The /equivalence page passes undotted extensions and works, making the inconsistency more baffling.

**Evidence:** commandBuilder.ts:68-69 `const H5 = [".h5", ".hdf5"]; const JSON = [".json"];` (also [".csv"] line 264, [".txt", ".mcompo.txt"] line 305, [".py"] line 336) passed verbatim by builder/page.tsx:238. FileBrowserModal.tsx:25 documents "File extensions (without the leading dot...)" and :55-61 builds `new RegExp(`\\.(${escaped.join("|")})$`, "i")` after escaping dots. Verified: buildExtensionRegex([".h5",".hdf5"]).test("reference.h5") === false, while the equivalence page's undotted form matches. Filter at FileBrowserModal.tsx:453 hides non-matching files.

### BUG-10 `web/lib/commandBuilder.ts:149`

The export-surface-flux builder emits `--mu-edges -1,-0.5,0.5,1` as separate tokens, which argparse rejects, and since mu bin edges necessarily span [-1,1] every physically valid value breaks the generated command.

**User impact:** Anyone copying the export-surface-flux CLI preview — with the default value or with any real mu edges they typed (which always start at -1) — gets an immediate argparse failure in the terminal. The one command this builder exists to assemble can essentially never run as copied.

**Evidence:** commandBuilder.ts:149 text("mu_edges", ..., "--mu-edges", "-1,-0.5,0.5,1", ...) and buildCommandCli:482 `tokens.push(field.flag, emitted)`. Reproduced against the real parser (src/openmc2donjon/commands/adf.py:277-281 --mu-edges required): parsing `--mu-edges -1,-0.5,0.5,1` exits with 'error: argument --mu-edges: expected one argument' because argparse's negative-number matcher does not accept the comma list, so the value is classified as an option string. Only the `--mu-edges=-1,...` form parses.

**Verifier nuance:** Claim is accurate for the supported range; minor nuance: on Python >=3.14 the space-separated form also parses, so 'only the = form parses' is version-scoped to 3.10-3.13.

### BUG-11 `web/app/pygan/page.tsx:710`

browserInitialPath gives the file browser invalid start paths in both of its branches: empty fields fall back to the hardcoded mock tree root (a 404 in live mode), and filled fields pass the field's file path verbatim (which the backend rejects as not-a-directory), so Browse opens on an error card in both mock and live modes.

**User impact:** In the advertised mock demo flow (Fill mock compare, then Browse to adjust a path) every Browse button opens on 'HTTP 404 — path not found: /mock/home/openmc-runs/c5g7/handoff.h5'; in live mode a filled field yields 'HTTP 400 — path is not a directory' and an empty field with no saved prefix yields 'HTTP 404 — path not found: /mock/home/openmc-runs'. Users must manually type paths to recover.

**Evidence:** Lines 710-713: `if (target === "input") return input || savedPrefix || "/mock/home/openmc-runs";` (same for summary/keep/default) — the raw field value is returned with no file-segment stripping, and the fallback is the mock root even against a live backend. Passed at line 299 `initialPath={browserInitialPath(...)}`; FileBrowserModal.tsx:142 lists it verbatim. Backend live: files.py:96-97 404s nonexistent paths and files.py:98-101 400s 'path is not a directory' for files; mock: files.py:209-210 404s file paths because they are not _MOCK_TREE keys (e.g. MOCK_INPUT "/mock/home/openmc-runs/c5g7/handoff.h5" filled by 'Fill mock compare' at line 122). Every other page strips the file segment and/or falls back to backend-resolved "~" (inspect/page.tsx:481-489, equivalence/page.tsx:780, 807-810, builder/page.tsx:548, openmc/page.tsx:815).

**Verifier nuance:** Only one nuance: in mock mode an empty field's fallback "/mock/home/openmc-runs" is a valid _MOCK_TREE directory and lists correctly; the error card appears for filled fields in mock mode and for both the empty-fallback (404) and filled-file (400) cases in live mode — which the claim's branch descriptions state correctly, though its one-line summary slightly overgeneralizes.

### BUG-12 `src/openmc2donjon/web/commands.py:509`

Catalog entry pygan-inspect-compo is labeled 'Command builder ready' and links to /builder?command=pygan-inspect-compo, but no such builder spec exists, so the target page renders the fallback saying no structured builder exists yet.

**User impact:** On both the catalog card and the /commands/pygan-inspect-compo detail page the user sees a 'Command builder ready' badge, a 'Web form' card marked pass with an 'Open form' button, and 'Preselected in web: Builder: pygan-inspect-compo'; clicking any of these lands on a page that flatly contradicts the promise and offers only a bare CLI copy.

**Evidence:** web/commands.py:509-510: status_label="Command builder ready", web_path="/builder?command=pygan-inspect-compo" — but COMMAND_BUILDER_SPECS in web/lib/commandBuilder.ts:76-364 has no pygan-inspect-compo id, so commandBuilderSpec() returns null and web/app/builder/page.tsx:533 renders "This command is visible in the catalog, but no structured builder exists yet." Meanwhile commandWorkflowMapping.ts:105-117 treats any /builder path as available:true with preset "Builder: pygan-inspect-compo".

## Confusing (misleading state, copy, or flow) — 23

### CONFUSING-01 `web/app/openmc/page.tsx:106`

The ?summary= deep links into the SPH physics summary (home 'Open SPH minicase' shortcut and demo step 01 'Review SPH evidence') never auto-load anything: the param only prefills the path field and the card stays idle until the user finds and clicks 'Load summary'; the home shortcut additionally omits the #openmc-sph-summary anchor, landing the user at the top of the page.

**User impact:** Clicking links whose copy promises reviewing flux uncertainty, SPH range, and NSPH status lands the user on an empty placeholder telling them to load the summary themselves (for the home shortcut, off-screen at the top of the planner) — the promised evidence never appears without a second, unadvertised scroll-and-click, so the shortcut appears broken.

**Evidence:** page.tsx:106-108 only stores the param: `useState(searchParams.get("summary") ?? "")`. OpenmcSphPhysicsSummaryCard starts at `useState<SummaryState>({ kind: "idle" })` (line 32) and load() fires solely from the 'Load summary' button onClick (lines 84-91); the file contains zero useEffect, and the idle body (102-108) says 'After running the CE/MG SPH workflow, load the summary...'. Entry points: openmcSphEvidenceHref appends #openmc-sph-summary but still cannot auto-load (openmcSphDemo.ts:93-102, used by OpenmcSphMainlineCard.tsx:54); demoShortcuts.ts:40-44 promises 'including the physics summary and corrected MACROLIB NSPH handoff' and omits even the anchor. Contrast app/inspect/page.tsx:159-162 where the sibling inspect shortcut's path param genuinely auto-runs.

### CONFUSING-02 `web/components/convert/ConvertForm.tsx:314`

The 'Mixture filter' <label> wraps the entire MixturePicker plus textarea, so its implicit labeled control is the picker's 'Inspect HDF5' button — clicking the label text fires an HDF5 inspection request instead of focusing the textarea.

**User impact:** Clicking the 'Mixture filter' heading unexpectedly launches an HDF5 inspection (network call plus state change) instead of focusing the mixture list field, and assistive tech gets a wrong label association for the textarea.

**Evidence:** ConvertForm.tsx:314-335: `<label className="block lg:col-span-2"> <div>Mixture filter</div> <div ...> <MixturePicker .../> <textarea .../> </div> ... </label>`. Per HTML labeling rules the labeled control is the first labelable descendant, which is MixturePicker's first button `onClick={() => void loadMixtures()}` — 'Inspect HDF5' (MixturePicker.tsx:65-72).

### CONFUSING-03 `web/app/convert/page.tsx:160`

The same dry-run -> convert -> preview/bundle step sequence is rendered five times simultaneously on the idle convert page as five separately styled sections (six in mock mode).

**User impact:** A first-time user scrolls through five near-identical tellings of the same three-step workflow before reaching any result, burying the form and the actual output and directly violating the 'nothing superfluous' bar.

**Evidence:** (1) ConverterFirstSteps 'User path' steps 1-4 (app/convert/page.tsx:160-221); (2) 'What each action means' cards (ConvertModeReferenceStrip.tsx:17-33, rendered at ConvertForm.tsx:259); (3) 'Direct convert action' steps 01-03 (DirectConvertActionPanel.tsx:67-86, rendered at ConvertForm.tsx:261); (4) 'Converter main path' steps 01-03 (ConvertActionProgress.tsx:35-41 + convertActionGuide.ts:62-101, always rendered via ConvertReport.tsx:30); (5) 'Direct converter production path' stage pills plus 01-04 cards (ConvertPrimer.tsx:98-186, rendered at page.tsx:139). In mock mode MockDemoCard's 'Show demo click path' (MockDemoCard.tsx:106-127) adds a sixth.

**Verifier nuance:** The claim is accurate for the five always-visible sections; the mock-mode "sixth" (MockDemoCard's "Show demo click path") is inside a collapsed <details> element by default, so only its summary line is visible until the user expands it.

### CONFUSING-04 `web/lib/convertSphHandoff.ts:36`

On the MULTICOMPO variant of the SPH handoff card, the 'Next action' tile urges "Run Convert to write the NSPH-bearing ASCII handoff" — format-blind copy that nudges the user to deliver SPH via MULTICOMPO, whose NSPH records DONJON NCR does not consume.

**User impact:** A user converting an SPH-corrected handoff in MULTICOMPO mode reads 'Run Convert to write the NSPH-bearing ASCII handoff' as confirmation their SPH factors will reach DONJON, when DONJON NCR treats MULTICOMPO NSPH records as inert — a physics-communication defect the sibling tile only partially counteracts.

**Evidence:** convertSphHandoff.ts:33-37 computes nextAction without checking `macrolib`: `data.dry_run && data.ok ? "Run Convert to write the NSPH-bearing ASCII handoff."`. The same card's sibling 'DONJON output' tile explicitly says the opposite for multicompo: "L_MULTICOMPO can carry equivalence metadata, but the validated DONJON NSPH consume smoke uses L_MACROLIB." (line 29) with badge "Review output format" (line 24).

**Verifier nuance:** Minor nuance: the multicompo ASCII can literally contain NSPH blocks as inert metadata (api.ts exposes multicompo_ascii_nsp_block_count), so "NSPH-bearing" is not factually false — the defect is the misleading, format-blind call-to-action copy, matching the claimed "confusing" severity rather than a functional bug.

### CONFUSING-05 `web/components/openmc/OpenmcProductionPathPanel.tsx:91`

With equivalence=SPH and Output object=MULTICOMPO (a combination the form allows), the SPH panel contradicts itself: header and step title claim MACROLIB while the same step's body says to write L_MULTICOMPO.

**User impact:** A user who flips the output toggle to MULTICOMPO on the SPH route sees one card simultaneously telling them the converter writes MACROLIB and instructing them to write L_MULTICOMPO, with no gate stopping the invalid combination.

**Evidence:** `const object = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO"` (line 61); the sph branch step 03 has hardcoded title "Convert to DONJON MACROLIB" (line 91) but body `Use the corrected HDF5 as converter input and write ${object}. For this SPH route, MACROLIB is the DONJON consumption path...` (line 93); header is hardcoded "Three steps before the converter writes MACROLIB" (line 147). The form's Output object Segmented is never restricted when equivalence=sph (app/openmc/page.tsx:355-363).

### CONFUSING-06 `web/components/openmc/OpenmcSphPhysicsSummaryCard.tsx:322`

The footer note interpolates the live applied_to_xs value into a sentence whose conclusion is hardcoded for false, producing a self-contradiction whenever a summary reports applied_to_xs = true.

**User impact:** A user reviewing an apply-sph-style summary reads 'applied_to_xs = true, so the macro cross sections were not silently multiplied' — the sentence asserts the opposite of the value it just printed.

**Evidence:** `The report says \`applied_to_xs = {String(summary.sph.applied_to_xs)}\`, so the macro cross sections were not silently multiplied in the HDF5.` (lines 321-325) — the conclusion clause renders unconditionally; the apply-sph route explicitly produces XS-divided copies (web/lib/openmcSphWorkflow.ts:79-84), so true is a reachable value.

### CONFUSING-07 `web/components/openmc/OpenmcProductionPathPanel.tsx:72`

After a successful 'Plan workflow', the SPH route's step 01 'Run OpenMC CE/MG SPH' displays status 'passed' even though nothing was executed — the plan-request status is mapped onto a run-physics card.

**User impact:** A user who merely generated a command plan sees the OpenMC CE/MG SPH run badged 'passed', suggesting the physics already ran and its evidence exists when neither is true.

**Evidence:** Step id 'run-openmc' uses `status: statuses.plan` (lines 63-75); openmcWalkthroughStatuses sets `plan: ... planned ? "passed" : ...` where planned = plan API returned ok (openmcWorkflowWalkthrough.ts:40-52). The idle PlanReport on the same page states 'This planner does not execute OpenMC.' (app/openmc/page.tsx:513-516).

### CONFUSING-08 `web/lib/openmcSphDemo.ts:81`

The mock demo prefill fills the Statepoint HDF5 field but sets loadStatepoint=false, leaving a populated-yet-disabled input whose value every downstream command ignores.

**User impact:** After 'Fill SPH planner' the user sees a greyed-out statepoint path that looks meaningful but is silently excluded from every generated command, inviting the false belief the statepoint will be used.

**Evidence:** `statepointPath: preset.id === "mock-openmc-sph" ? preset.mgStatepoint : "", loadStatepoint: false` (openmcSphDemo.ts:81-82); the field renders disabled={!loadStatepoint} (app/openmc/page.tsx:384); the planned export command takes the --no-load-statepoint branch and drops the statepoint (openmc_workflow.py:483-489).

### CONFUSING-09 `web/lib/openmcSphDemo.ts:50`

The live-mode demo card bakes in machine-specific, dated, volatile /private/tmp paths (plus one relative repo path), and renders unconditionally for every live backend as the 'recommended demo path' whether or not those files exist.

**User impact:** On any machine other than the one that produced the 2026-07-09 run (or after /private/tmp is cleared), the flagship 'live production minicase' card's Load summary returns 'path not found' and every prefilled path is dead, making the recommended path look broken.

**Evidence:** LIVE_OPENMC_SPH_DEMO uses runRoot "/private/tmp/openmc2donjon_two_region_production_20260709" and five sibling absolute paths (openmcSphDemo.ts:45-62), plus relative recipePath "examples/openmc_ce_mg_33g_sph_minicase/export_recipe.py" (lines 77-80). page.tsx selects it purely on backendMode === "live" (app/openmc/page.tsx:147-152) with no existence check; the live summary endpoint 404s for missing paths (openmc_sph_summary.py:64-66).

### CONFUSING-10 `src/openmc2donjon/web/fixtures/inspect_handoff.json:36`

Mock fixture declares file-level "state_points": null even though all nine mixtures declare "state_points": 1, making the Summary display 'State points: 9' (the calculation count) for a one-state-point file.

**User impact:** The mock demo — the first thing a new user sees — reports 'State points 9' with an OK badge for a file whose mixtures each hold 1 state point, silently substituting a different quantity under the 'State points' label.

**Evidence:** inspect_handoff.json:36 `"state_points": null` vs lines 62-174 `"state_points": 1` per mixture; Summary.tsx:34-37 `<Stat label="State points" value={data.state_points ?? data.calculation_count} />` falls back to calculation_count (9). The real inspector can only emit null here alongside a FAIL issue (mgxs_inspect.py:175-177), so ok:true + issues:[] + state_points:null is a state the live backend can never produce.

**Verifier nuance:** Accurate except one nuance: mock mode is opt-in (create_app defaults mock_mode=False), so the misleading "State points 9" appears in the demo/mock-mode UI rather than unconditionally being "the first thing a new user sees".

### CONFUSING-11 `web/app/inspect/page.tsx:203`

After a failed scatter-moment fetch, the moment selector still asserts the failed moment as active while the heatmap header shows the previous moment, and clicking the same moment button again is a silent no-op with no retry path.

**User impact:** After a transient error on a moment switch, the user sees P1 selected but P0 data drawn, clicks P1 to retry, and nothing happens — no request, no feedback. They must discover on their own that toggling to P0 and back re-triggers the fetch.

**Evidence:** On error the state keeps scatterMoment at the requested value (page.tsx:186-198) with the previous payload rendered, so ScatterHeatmap.tsx:78 shows 'Scatter matrix (P0)' while the P1 button renders aria-pressed/highlighted (ScatterHeatmap.tsx:137-152). Retry is impossible via that button: onMomentChange={setScatterMoment} (page.tsx:305) sets the same value, React bails out, and the fetch effect keyed on [state, selectedMixture, scatterMoment] (page.tsx:203) never re-fires. The banner (page.tsx:462-464) says only '— keeping previous payload (P0).'

### CONFUSING-12 `web/app/equivalence/page.tsx:60`

Switching equivalence tabs keeps the previously edited output filename (plus mode fields, clip values, summary JSON, and the Force overwrite toggle), so the CLI preview for a different command targets the previous tool's artifact.

**User impact:** A user who set the ADF sidecar output and then switches to Inject SPH copies a command that writes the augmented MGXS over their ADF sidecar path — silently destructive with the Force overwrite toggle, which also persists across tabs.

**Evidence:** options state is created once (page.tsx:60-63 useState(defaultEquivalenceOptions(kind)), outputTouched at :63) and no effect resets it when kind changes from the URL (contrast builder/page.tsx:83-86 which resets values on searchParams change). activeOptions (page.tsx:69-76) uses `outputTouched ? options.outputPath : info.outputPlaceholder`, so after editing the output on the ADF tab (setOutputTouched(true), :92/:161), clicking 'Inject SPH' renders `openmc2donjon augment-sph ... -o <adf output name>`.

**Verifier nuance:** The defect is real, but not fully "silent": the stale output filename is displayed in the Output HDF5 field on the new tab (page.tsx:159 renders activeOptions.outputPath), so the destructive overwrite requires the user to overlook a visible-but-unexpected value; the cross-tab persistence of the edited output path, Force overwrite, summary JSON, and mode/clip fields is nonetheless a genuine state-reset bug.

### CONFUSING-13 `web/app/builder/page.tsx:533`

The builder fallback asserts "This command is visible in the catalog" even when the catalog failed to load or the id is not in it, co-rendering with a banner that claims a local builder exists when none does, and it fabricates a copyable `openmc2donjon <id>` command for unknown ids.

**User impact:** With the backend stopped, a user landing on /builder?command=pygan-inspect-compo sees two contradictory claims (catalog failed vs. command visible in catalog / builder can assemble a preview) plus a Copy CLI button for a command that errors on missing required arguments; for a mistyped command id the copyable command does not exist at all.

**Evidence:** FallbackCommand renders whenever spec is null (page.tsx:231-233) with fixed copy at :533-534 "This command is visible in the catalog, but no structured builder exists yet." and :528 `const cli = command?.cli ?? \`openmc2donjon ${commandId}\``. Simultaneously, on catalog failure the banner at :145-149 renders "Command catalog failed: {message}. The local builder can still assemble its CLI preview." — but for spec-less ids (e.g. /builder?command=pygan-doctor, linked from app/pygan/page.tsx:440) there is no local builder, and command is null so nothing is actually known to be in the catalog.

### CONFUSING-14 `web/app/builder/page.tsx:265`

The identical stage.summary sentence renders twice in adjacent panels whenever the catalog entry is unavailable (initial load and backend-down mode).

**User impact:** In the explicitly supported no-backend mode, users see the same explanatory sentence twice stacked on every builder page — reads as a rendering mistake and violates the 'nothing superfluous' bar.

**Evidence:** Both panels render unconditionally for spec pages (page.tsx:177-178). WorkflowHint prints {stage.summary} at :265; CommandContextPanel, when command is null, falls back to ["Use when", stage.summary] at :290-291. E.g. /builder?command=diff without the backend shows "Diagnostic command: use it before accepting a handoff or when a local environment looks suspicious." verbatim in the cyan 'workflow step' box and again directly below as the 'Use when' card.

### CONFUSING-15 `web/lib/donjonGuide.ts:200`

The SEQ_ASCII 72-character truncation warning in the handoff checklist is rendered only for hex geometry, although the limit applies to the SEQ_ASCII FILE statement in every generated deck (CAR2D/CAR3D smoke and ingest decks included).

**User impact:** A user generating a CAR2D/CAR3D deck with a long absolute ASCII path gets no warning; DONJON silently truncates the path at 72 characters and the deck fails (or reads the wrong file) even though the page knew about the limit.

**Evidence:** Checklist item is inside `...(deck.geometry === "hex" ? ([{ id: "hex-ascii-72", title: "Keep the ASCII path under 72 characters", ... }]) : [])` (donjonGuide.ts:200-215), while donjonIngestSnippet/donjonIngestOnlySnippet emit `SEQ_ASCII … :: FILE '${path}' ;` for all geometries and both formats (donjonGuide.ts:270, 284, 308, 317). Project docs state the limit generally: examples/irena30_zrefl_hex/README.md:70-72 and write_donjon_decks.py:119-121 enforce len(str(path)) > 72 for every deck path.

### CONFUSING-16 `web/app/pygan/page.tsx:268`

The CLI preview claims to be the 'Same command' as the web run, but for non-numeric rtol/atol the web request silently substitutes defaults while the CLI preview embeds the raw broken string, so the two runs diverge.

**User impact:** A user who typos '1e-6x' into Relative tolerance gets a web comparison quietly run at the default 1e-6, while the copied 'same' CLI command errors in the shell — or they trust that the shown command reproduces what the web ran when it does not.

**Evidence:** Copy at line 268: "Same command, runnable in a shell." Web run (lines 143-144): `rtol: parseNumberOrDefault(rtol, 1.0e-6), atol: parseNumberOrDefault(atol, 1.0e-8)` — falls back on any non-finite parse. CLI preview (lines 691-692): `if (rtol.trim() && rtol.trim() !== "1e-6") tokens.push("--rtol", rtol.trim());` — pushes the raw string verbatim.

### CONFUSING-17 `web/app/donjon/page.tsx:318`

'Copy page link' copies a relative path ('/donjon?ascii=…'), not a URL — there is no origin prefix anywhere in the app.

**User impact:** Pasting the 'link' into chat, notes, or a browser address bar yields a non-navigable relative path; the user must hand-assemble the localhost origin to actually share or reopen the configured page.

**Evidence:** Line 318: `<CopyCliButton value={selfHref} label="Copy page link" />` where selfHref = donjonGuideHref(...) returning `query ? \`/donjon?${query}\` : "/donjon"` (donjonGuide.ts:100). Grep for window.location/location.origin across web/app, web/components, web/lib returns nothing.

### CONFUSING-18 `web/app/settings/page.tsx:63`

Settings copy says the value is 'Pre-filled as a placeholder on the Inspect page', but the preference is read by six pages (Inspect, Convert, PyGan, Equivalence, Builder, OpenMC), several of which commit it into inputs via 'Use saved prefix' buttons and use it as the file-browser start directory.

**User impact:** A user editing 'Default Inspect path' has no way to know it also changes prefill buttons and Browse start directories on five other pages; conversely users of those pages don't know where the prefix comes from or how to change it.

**Evidence:** settings/page.tsx:63-66: "Pre-filled as a <em>placeholder</em> on the Inspect page so you can see your usual prefix without it being committed into the input." Consumers: inspect/page.tsx:122, useConvertPageState.ts:82-83, pygan/page.tsx:62 + 207-215 (`onClick={() => setInputH5(savedPrefix)}` commits it), equivalence/page.tsx:66, builder/page.tsx:62 + 121 (`patch(firstPath.name, savedPrefix)`), openmc/page.tsx:122.

**Verifier nuance:** Minor path fix only: the convert consumer is web/lib/useConvertPageState.ts:82-83 (not under web/app/), with the commit button in web/components/convert/ConvertForm.tsx:171; the defect itself stands as described.

### CONFUSING-19 `src/openmc2donjon/web/commands.py:523`

A `tab=compare` query parameter is emitted at multiple sources (the compare-writers catalog entry and the convert page's 'Validate PyGan' links) but /pygan never reads any 'tab' param, and the command detail page even displays 'tab: compare' under 'Preselected in web', asserting a preselection the target page never performs.

**User impact:** The compare-writers detail page tells the user 'tab: compare' is preselected in the web UI; /pygan has no tab mechanism, so the user lands at the top of the PyGan page and must find the 'Compare writer backends' section manually. Shared/bookmarked convert-page URLs also carry the dead parameter, suggesting tab behavior that does not exist.

**Evidence:** web/commands.py:523: web_path="/pygan?tab=compare"; web/lib/convertNextSteps.ts:62-71 builds `new URLSearchParams({ tab: "compare", input_h5: ..., ... })` used by ConvertOutcomeSummary.tsx:114 and OutputActions.tsx:392,609. app/pygan/page.tsx reads only input_h5, format, root_name, comment, mixture, rtol, atol, summary_json, keep_dir (lines 65-77); grep for get("tab") across web/ returns nothing. Because commandWorkflowMapping.ts has no /pygan branch, the generic branch (lines 119-127) sets presets = queryPresetLabels(searchParams) yielding "tab: compare", rendered by web/app/commands/[id]/page.tsx:178 under 'Preselected in web'.

**Verifier nuance:** Minor overstatement of impact only: /pygan is essentially the compare-writers workspace (doctor status + compare form), so the user is not far from the compare section on landing; the dead parameter and the false "Preselected in web: tab: compare" label are nonetheless real.

### CONFUSING-20 `src/openmc2donjon/web/commands.py:531`

The serve command is status='ready' while its own status_label says 'Command builder ready', contradicting the status legend on the same catalog page which defines Ready as a first-class web workflow and classifies builders as Partial.

**User impact:** On the catalog page the ready/partial counters and the coverage legend define categories that serve visibly violates: users see a green 'ready' command whose own label says it is only a command builder, which the legend two sections above says should be 'partial'.

**Evidence:** web/commands.py:531-533: status="ready", status_label="Command builder ready", web_path="/builder?command=serve". CommandCoverageDashboard.tsx:104-112 legend on the same /commands page: Ready = "First-class web workflow: inspect, convert, or review directly in the browser." vs Partial = "Planner/viewer/builder: the web UI prepares the command or report...". serve is counted in the 'ready' tile (commandCoverage.ts:35) and shows the emerald ready badge (CommandPrimitives.tsx:148-150).

### CONFUSING-21 `web/components/Nav.tsx:19`

The More dropdown has no dismissal path except toggling the button, pressing Escape while the button itself is focused, or a pathname change — it stays open after outside clicks, after Escape from a menu item, and after clicking a menu item that navigates within the same pathname.

**User impact:** The dropdown lingers over page content: clicking anywhere else does not close it, Escape does nothing once focus is on a menu link, and after clicking e.g. Bundle while already on /builder the menu stays open covering the top of the page the user just navigated to.

**Evidence:** Only close mechanisms in the file: `useEffect(() => { setMoreOpen(false); }, [pathname]);` (lines 19-21) and the button-scoped Escape onKeyDown (lines 46-50). No document/outside-click listener, no onBlur, and the menu-item <Link>s (lines 75-96) have no onClick close. Same-path navigations exist in the menu itself: from /builder?command=diff, clicking 'Bundle' (/builder?command=bundle, navigation.ts:40) keeps pathname "/builder" so the effect never fires.

### CONFUSING-22 `src/openmc2donjon/web/fixtures/inspect_handoff.json:46`

The mock inspect fixture and the mock convert preflight give contradictory uncertainty stories for the same demo file: inspect reports 0 of 58 std_dev datasets present, while convert's preflight claims uncertainty fully checked at 72/72 datasets with max_rel 1.9e-2.

**User impact:** In the mock demo, inspecting the file says its uncertainty data is entirely absent (production readiness flagged), then converting the very same file reports complete uncertainty coverage — users evaluating the tool cannot tell which claim to trust, and the combination is physically impossible for one file.

**Evidence:** inspect_handoff.json:46-47: `"std_dev_datasets": 0, "std_dev_expected_datasets": 58` versus convert.py:566-573 mock preflight input: `"uncertainty": {"checked": True, "expected_datasets": 72, "datasets": 72, "missing_datasets": 0, "max_rel": 1.9e-2}`. Both describe the same mock C5G7 handoff (9 mixtures, 7 groups, 4 fissionable, ADF 9/4 faces, SPH 9 in both payloads). Summary.tsx:51 renders the std_dev stat and Summary.tsx:144-145 flags 0/58 as failing coverage, while ConvertReportShared.ts:211-213 renders 'std_dev max 1.9e-2' on the convert validation summary. The expected totals (58 vs 72) also disagree.

**Verifier nuance:** Minor: the inspect Production hint renders tone "warn" (amber), not a hard failure; otherwise the claim is accurate as stated.

### CONFUSING-23 `web/components/commands/CopyCliButton.tsx:20`

Every copy button across the app (Copy CLI, Copy DONJON path, Copy page link, Copy summary, deck/run commands on /convert, /equivalence, /builder, /donjon, /pygan, /commands) flips to 'Copied' even when both the async clipboard API and the execCommand fallback fail.

**User impact:** On an origin where navigator.clipboard is unavailable (e.g. plain http on a LAN host) and execCommand returns false, the user clicks Copy, sees the confirming 'Copied' label, then pastes stale or empty clipboard content into their terminal with no signal anything went wrong — the whole product funnels into these buttons.

**Evidence:** copy() at lines 20-24: `await copyText(value); setCopied(true);` — no failure branch. copyText swallows the navigator.clipboard.writeText rejection in an empty catch (lines 44-48) and ignores document.execCommand("copy")'s boolean return in the fallback (lines 50-58), so copyText always resolves and setCopied(true) runs unconditionally. Used by every copy control on every page (e.g. OutputActions.tsx:157-166, 405-414, 510-519; ConvertForm.tsx:350; RunSummaryCard.tsx:29-35; LiveMinicaseCard.tsx:139-144, 169-174, 221-227; donjon/page.tsx:318).

## Polish (dead code, a11y, duplication) — 19

### POLISH-01 `web/app/page.tsx:371`

When the backend health check fails, the Backend card and the Demo panel co-render two different startup commands side by side in the same sidebar (`openmc2donjon serve` vs `openmc2donjon serve --mock`) with no cue that they are mutually exclusive alternatives.

**User impact:** A first-time user with no backend running sees two adjacent panels prescribing different commands and cannot tell at a glance which one to run.

**Evidence:** Both branches derive from the same status.kind === "error": StatusView (page.tsx:365-375) renders "Start it with `openmc2donjon serve`." and demoBackendState maps error→"unavailable" (page.tsx:306-308), so DemoDisabledMessage (page.tsx:316-324) simultaneously renders "Start the backend with `openmc2donjon serve --mock` to enable bundled demos." — both inside the single <aside> (page.tsx:73-79).

### POLISH-02 `web/components/convert/OutputActions.tsx:113`

The entire fallback 'Artifacts & next actions' panel (including a third 'Refresh file status' button, a 'Convert now' button, and the outputNotice banner) is unreachable dead code because convertOutputMode's three return values are all handled by early returns above it.

**User impact:** No direct user impact (never rendered), but ~90 lines of unreachable panel UI is a maintenance trap: copy fixes to the visible notice/refresh flows can silently land in the dead twin, which duplicates strings from the visible contradiction-prone panels.

**Evidence:** convertOutputMode.ts:3-9 returns only "dry-run-ready" | "converted" | "blocked"; OutputActions.tsx:74-111 early-returns for all three, so lines 113-180 (Refresh button at 131-137, Convert now at 152-156, notice banner at 169-176) can never render; outputNotice/outputNoticeClass (950-994) and the locals notice/pathLabel/canConvertNow (65-69) exist only to feed the dead branch.

### POLISH-03 `web/components/inspect/MixtureTable.tsx:58`

Mixture roster rows use <tr role="button" aria-selected>, which destroys table row semantics for assistive tech and applies aria-selected to a role that does not support it.

**User impact:** Screen-reader users lose the column context (Fiss / Volume / Required / ADF faces / SPH / Scatter) for every row and never hear which mixture is currently selected.

**Evidence:** MixtureTable.tsx:58-60: `tabIndex={interactive ? 0 : undefined} aria-selected={interactive ? active : undefined} role={interactive ? "button" : undefined}` on the <tr>. role="button" strips the row/cell relationship (seven <td> cells flatten into one button label, losing column-header association), and aria-selected is not a supported property of role=button.

### POLISH-04 `web/components/inspect/FileBrowserModal.tsx:314`

File-browser buttons have aria-labels that do not contain their visible text ('Cancel' vs 'Close browser', 'Go' vs 'Navigate to typed path'), failing WCAG 2.5.3 label-in-name.

**User impact:** Voice-control users who say 'click Cancel' or 'click Go' cannot activate these buttons because the accessible name replaces rather than extends the visible label.

**Evidence:** FileBrowserModal.tsx:314-318: aria-label="Close browser" on the button whose visible text is 'Cancel'; lines 377-384: aria-label="Navigate to typed path" on the 'Go' button; lines 340-347: aria-label="Use the current directory" on the 'Use this directory' button.

### POLISH-05 `web/app/builder/page.tsx:239`

Browse on output-path fields opens a picker titled 'Browse for input file' that only lets the user select an existing file, contradicting the field's write-target purpose (same on the equivalence page's SPH CSV table output).

**User impact:** Users trying to choose where an output will be written get a dialog asking for an 'input file' and cannot enter a new filename — a fresh output name is impossible to pick, and picking an existing file means naming a file to overwrite. The equivalence page's main output field shows the right pattern (directory mode) right above the broken one.

**Evidence:** builder/page.tsx:239 `fileTypeLabel={browserField?.browse === "directory" ? "directory" : "input file"}` and :242 selectMode file — applied to output optionPaths like "Surface flux HDF5" (-o, commandBuilder.ts:143), "Driver HDF5" (:211), "SPH table CSV" (:264), "Corrected MGXS HDF5" (:288). equivalence/page.tsx:236 does the same for tableOutput (--table-output, :468-472). FileBrowserModal only selects existing file rows in file mode (FileBrowserModal.tsx:40-44).

**Verifier nuance:** Minor detail: the modal title renders as "Browse for input file file" (fileTypeLabel + selectMode suffix both say "file"), not exactly "Browse for input file"; the substance of the claim is otherwise accurate.

### POLISH-06 `web/lib/commandBuilder.ts:337`

The doctor builder labels Statepoint as freestanding-optional, but the CLI rejects --statepoint without --recipe, so filling only that field produces a command that always errors.

**User impact:** A user who supplies a statepoint (or checks Load statepoint) without a recipe copies a doctor command that exits with a usage error; the form's help text gives no hint of the dependency the CLI enforces.

**Evidence:** commandBuilder.ts:337 `optionPath("statepoint", "Statepoint", "Optional OpenMC statepoint path.", "--statepoint", ...)` (and :338 'Load statepoint' toggle) versus src/openmc2donjon/commands/diagnostics.py:795-800 `if args.statepoint is not None and args.recipe is None: parser.error("--statepoint can only be used with --recipe")`.

### POLISH-07 `web/app/equivalence/page.tsx:108`

The equivalence page states its does-not-write-files disclaimer twice on the same screen.

**User impact:** The same reassurance appears in the page intro and again in the always-visible CLI preview card, adding repeated copy on a page whose stated bar is nothing superfluous.

**Evidence:** Header at :108-110: "This web page does not mutate files; run the copied command in a terminal." CLI-preview aside at :215-217: "Copy and run this command locally. No web endpoint writes files here."

### POLISH-08 `web/app/pygan/page.tsx:383`

PyGan availability status is told three times simultaneously on one page — the overview card pill+sentence, the Doctor panel heading, and the compare-button hint — with the sentence 'PyGan is importable from the running backend' rendered nearly verbatim twice.

**User impact:** The page reads as padded: the same availability fact occupies three stacked sections, diluting the at-a-glance clarity the page is supposed to provide.

**Evidence:** WriterBackendOverview (rendered line 185) shows pill {pyganLabel} (line 370) plus line 383: "PyGan is importable from the running backend."; DoctorPanel (rendered line 186, directly below) shows line 425: "PyGan available"/"PyGan unavailable"; the compare aside (lines 288-290) renders pyganCompareAvailability's hint, pyganBackend.ts:27: "PyGan is importable from the running backend; live writer comparison is enabled."

**Verifier nuance:** Minor precision fixes: the overview sentence is on line 382 (not 383), and the verbatim duplication with the compare hint occurs only in the live available state — in mock mode the hint is a different mock-specific string, though the page still states availability three times.

### POLISH-09 `web/app/donjon/page.tsx:931`

In hex mode the fixed-boundary explanation ('Z- REFL Z+ REFL with HBC COMPLETE VOID', only VOID validated) is rendered three times at once: as the deck-builder note, inside the 'Confirm boundaries' checklist card, and again as the dedicated 'hex-boundary-void' checklist card.

**User impact:** Hex users read the same boundary rule three times in adjacent sections of one page, which buries the genuinely distinct warnings (72-char path, smoke-first) among repetition.

**Evidence:** donjon/page.tsx:931-934: "Hexagonal boundaries are fixed: Z- REFL Z+ REFL with HBC COMPLETE VOID — the only outer boundary validated for full-hex SNT decks."; donjonGuide.ts:194 (boundary-solver hex body): "Hex boundaries are fixed: Z- REFL Z+ REFL with HBC COMPLETE VOID. …"; donjonGuide.ts:209-211 (hex-boundary-void): "Only VOID is validated on the hex outer boundary … only VOID is validated for full-hex outer boundaries." All three co-render whenever geometry === "hex".

**Verifier nuance:** The repetition is real, but the third card (hex-boundary-void) is not a pure duplicate: it uniquely explains that HBC COMPLETE REFL/ALBE 1.0 silently leak and that white-boundary colorset decks cannot be validated in SNT, while the boundary-solver card adds a solver-alignment reminder; only the core "fixed Z REFL + HBC COMPLETE VOID / only VOID validated" statement is repeated across all three.

### POLISH-10 `web/app/donjon/page.tsx:820`

Clearing the 'Mixtures to extract' (or hex side/height) number input stores 0 in state, so the visible control shows 0 while the sibling checklist and generated deck silently normalize to 1 (or the default length) — two co-rendered elements asserting different values.

**User impact:** A user who clears the field sees '0' in the form but 'NMIX 1' in the deck they are about to download, with no indication which one is real; the field also can never be visually emptied.

**Evidence:** donjon/page.tsx:818-821: `value={mixtureCount} onChange={(event) => onMixtureCountChange(Number(event.target.value))}` — Number("") === 0, and min={1} does not constrain typed/cleared values. donjonGuide.ts:474-477 normalizeMixtureCount: `Math.min(999, Math.max(1, Math.floor(Number(value))))` turns 0 into 1, so the checklist renders 'NCR extracts 1 mixture' and the deck shows NMIX 1 while the input displays 0. Same pattern for hexSide/hexHeight via normalizeHexLength (donjonGuide.ts:491-494).

### POLISH-11 `web/app/donjon/page.tsx:498`

The summary/artifact mismatch panel asserts 'The bundle contains one DONJON ASCII artifact', but bundles can carry both a MULTICOMPO and a MACROLIB artifact, and the picker silently keeps only the best-scoring one — so the mismatch can fire against a summary path that actually is a bundled artifact.

**User impact:** For a dual-format bundle whose summary points at the second artifact, the amber warning wrongly tells the user the summary output is outside the bundle when it is in fact bundled and self-contained.

**Evidence:** donjon/page.tsx:498-500: "The bundle contains one DONJON ASCII artifact, but the conversion summary points to a different output path." findDonjonBundleArtifact reduces all matches to a single best candidate (donjonGuide.ts:613-615) and donjonBundleAsciiMismatch compares the summary only against that one (donjonGuide.ts:677-687). The bundle CLI/builder accepts both formats at once (commandBuilder.ts bundle spec fields --mcompo and --macrolib).

**Verifier nuance:** Minor precision: the summary path literally equals a bundled artifact path only for in-place bundles (source == destination, copy skipped); for fresh-directory bundles the summary points at the original run-dir path while the same content is bundled under the bundle dir — but in both cases the "one DONJON ASCII artifact" premise is false and the guidance hides the second bundled format.

### POLISH-12 `src/openmc2donjon/web/commands.py:234`

The OpenMC entrypoint catalog links (and the direct lane's first workflow step) emit an intent= query param that the /openmc page never reads.

**User impact:** Users following 'Open web workflow' from openmc2donjon-export / openmc2donjon-from-openmc get a URL carrying a dead intent parameter; the page behaves identically without it, falsely suggesting intent-specific behavior and masking future regressions.

**Evidence:** web/commands.py:234: web_path="/openmc?intent=export&workflow=two-step"; web/commands.py:247: web_path="/openmc?intent=from-openmc&workflow=one-step"; web/lib/commandWorkflowLanes.ts:37: href: "/openmc?intent=export&workflow=two-step". web/app/openmc/page.tsx:88-112 reads only equivalence, workflow, format, summary, production; the only intent reader in the codebase is useConvertPageState.ts:38 which serves /convert.

### POLISH-13 `web/lib/commandWorkflowMapping.ts:123`

Commands linked to /pygan fall through to the generic mapping branch whose surface is the raw pathname, so the catalog's 'Web surface' filter buttons and the coverage 'Web surfaces' list mix the literal string '/pygan' in with friendly names like 'Convert page' and 'Command builder'.

**User impact:** The Web-surface filter row and the coverage surface list show a raw route path ('/pygan') alongside curated labels, which looks unfinished and gives no hint that the surface is the PyGan diagnostics page.

**Evidence:** commandWorkflowMapping.ts:119-124 generic branch: surface: parsed.pathname, title: "Linked web surface" — hit by pygan-doctor (web_path "/pygan", web/commands.py:497) and compare-writers (web/commands.py:523). Rendered as filter options via CommandWorkspace.tsx:150-160 and as chips in CommandCoverageDashboard.tsx:80-88.

**Verifier nuance:** Trivial citation nits only: the surface assignment is at commandWorkflowMapping.ts line 122 (line 123 is the title field), and the Python file is src/openmc2donjon/web/commands.py, not web/commands.py; the defect itself is exactly as described.

### POLISH-14 `web/lib/api.ts:139`

baseUrl() uses `??` instead of `||`, so an empty NEXT_PUBLIC_API_BASE_URL (blank value in web/.env.local) yields base "" and every API call is issued relative to the Next.js server, which serves no /api routes.

**User impact:** A user who copies .env.local.example but leaves the value blank gets 'Cannot reach backend.' on every page even though `openmc2donjon serve` is running on the documented default port, with no hint that the empty env var is the cause.

**Evidence:** `return ( process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000" );` — "" is not nullish, so the localhost fallback is skipped; fetch("" + "/api/health") targets the frontend origin. next.config.ts contains only reactStrictMode and distDir, no proxy/rewrite for /api. The regex also strips only one trailing slash.

**Verifier nuance:** The mechanism and user-visible failure are real, but the trigger framing is off: web/.env.local does not exist in the repo, and .env.local.example ships with NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 already filled in — copying it verbatim works. The defect only manifests if the user explicitly blanks the value (NEXT_PUBLIC_API_BASE_URL=), not merely by copying the example.

### POLISH-15 `web/components/HomeDemoShortcuts.tsx:14`

HomeDemoShortcuts is an orphaned component imported nowhere; it is a near-duplicate of the DemoPanel now inlined in app/page.tsx, with drifted copy — a leftover from the home-page redesign.

**User impact:** No direct user impact (never rendered), but it duplicates the live Demo panel with drifted copy — the next editor can change the wrong file and see nothing happen.

**Evidence:** grep for "HomeDemoShortcuts" across web/app, web/components, web/lib returns no import sites — only the file itself. Its JSX duplicates app/page.tsx's DemoPanel/DemoDisabledMessage/DemoBadge (compare HomeDemoShortcuts.tsx:67-86 with app/page.tsx:312-331; badge text drift: "backend offline"/"mock mode" at lines 99/111 vs "offline"/"mock" at app/page.tsx:344/356).

### POLISH-16 `web/app/convert/page.tsx:78`

The backend-status card copy contains markdown backticks that BackendModeCard renders literally, since the card prints body as a plain string.

**User impact:** When the backend is down, the convert page's 'Backend status' card shows raw backtick characters around the commands instead of formatted code, reading as a typo in the most prominent error surface of the page.

**Evidence:** app/convert/page.tsx:78 passes body="Start or restart the FastAPI backend with `openmc2donjon serve`; the page will not show live minicase paths until `/api/health` responds." (line 58 similarly); BackendModeCard.tsx:20-22 renders it as `<p ...>{body}</p>` with no code formatting. Contrast the home page's equivalent card which uses real <code> elements (app/page.tsx:371-373).

**Verifier nuance:** The defect is real but only at line 78; the evidence's aside "(line 58 similarly)" is wrong — the line-58 body text contains no backticks.

### POLISH-17 `web/components/openmc/OpenmcWorkflowChoices.tsx:24`

Dead code surviving the recent page cleanup: OpenmcWorkflowChoices is imported nowhere, the exported openmcSphSidecarHref is unused (and its hash anchor targets no element on /equivalence), and the demo presets' sphTable field is consumed by nothing.

**User impact:** No direct user harm, but the component and helpers are orphans of the deleted triage/minicase sections; they invite future re-wiring of stale copy.

**Evidence:** grep across web/app, web/components, web/lib shows OpenmcWorkflowChoices only at its own definition (OpenmcWorkflowChoices.tsx:24); openmcSphSidecarHref defined at web/lib/openmcSphDemo.ts:86-91 (`#${encodeURIComponent(preset.sphSidecar)}` — no such id exists on /equivalence) with zero call sites; sphTable set at openmcSphDemo.ts:39,55 and read nowhere.

**Verifier nuance:** Minor nuance only: OpenmcWorkflowChoices was already unimported before cleanup commit 3e769bc (it was missed by that cleanup rather than newly orphaned by it); the dead-code finding itself is fully accurate.

### POLISH-18 `web/app/openmc/page.tsx:338`

The collapsed 'Detailed OpenMC SPH command map' hardcodes activeCommandId="export-volume-flux", which highlights BOTH steps 01 and 02 as active on a page where no builder command is open, and the panel's lg:grid-cols-5 layout orphans the sixth step onto its own row.

**User impact:** The 'you are here' highlight marks two steps at once on a page where the user is on neither, and the six-step map shows five cards plus one stray card alone on a second row.

**Evidence:** page.tsx:338 passes activeCommandId="export-volume-flux"; both 'ce-flux' and 'mg-flux' steps share commandId "export-volume-flux" (openmcSphWorkflow.ts:40,53) and the active predicate is commandId equality (lines 126-133), so two cards get the emerald active style (OpenmcSphWorkflowPanel.tsx:44-48). The steps array has six entries (openmcSphWorkflow.ts:33-110) but the grid is lg:grid-cols-5 (OpenmcSphWorkflowPanel.tsx:39).

### POLISH-19 `web/components/openmc/OpenmcSphPhysicsSummaryCard.tsx:75`

The physics-summary path input has no accessible name — no <label>, no aria-label, only a placeholder.

**User impact:** Screen-reader users hear an unnamed edit field; once text is entered the placeholder disappears and there is no programmatic hint of what the field is for.

**Evidence:** `<input value={path} onChange={...} className="..." placeholder="/path/to/handoff/physics_summary.json" />` (lines 75-80) with no htmlFor/id pairing or aria-label, unlike the page's TextField which wires label htmlFor={inputId} (app/openmc/page.tsx:693-713).

**Verifier nuance:** The field is not literally unnamed: per HTML-AAM, placeholder serves as the fallback accessible name and persists programmatically even after text is entered (only the visual placeholder disappears). The real defect is placeholder-only naming — no visible label and an example-path fallback as the accessible name instead of a purpose label — inconsistent with the labeled TextField pattern used elsewhere on the page.

## Browser-only findings (found live, not in the code sweep)

### BROWSER-01 File browser is stuck after a 404 listing

With the dialog showing `HTTP 404 path not found`, clicking `↑ parent` or any breadcrumb segment fires **no** `/api/files` request (verified via network trace) — the user is trapped in the error state; the only recovery is typing a new path + Go. Reproduce: /inspect → Browse… → enter any nonexistent path → Go → click parent/breadcrumbs.

### BROWSER-02 Dialog title/counter template doubles the word "file"

Field label "input file" is interpolated into templates that append "file"/"files": the dialog titles render "Browse for input file file" and the hidden-count line renders "3 non-input file files hidden" (/builder, /equivalence).

### BROWSER-03 Demo dead-ends at step 3 with un-runnable CLI

Demo steps 1–2 execute in-browser against the mock backend, but step 3 (bundle) lands on the copy-CLI-only /builder prefilled with fictitious /mock paths — the copied `openmc2donjon bundle --output-dir /mock/home/...` command cannot succeed in any real terminal. Related: BUNDLE-UNVERIFIED below.

### UNVERIFIED (verifier lost to API drop) `src/openmc2donjon/web/bundle.py:152`

Mock /api/bundle/inspect 404s every manifest except the hardcoded c5g7 one, so the bundle-validation leg only works for the default c5g7 output; the OpenMC-SPH minicase chain 404s. Evidence: bundle.py:151-153 compares against _MOCK_BUNDLE_MANIFEST (bundle.py:18) while convertNextSteps.ts:73-79 derives `<output_dir>/bundle/manifest.json` from whatever the user converted.

## Refuted claims (adversarial verification working as intended)

- The production-evidence panel renders 'Accepted SPH consumption route: <FORMAT> GROUP/*/NSPH' for whatever format the summary declares — including MULTICOMPO — and openmcSphOutputPath/openmcSphOutputFormat actively route multicompo summaries to /convert?format=multicompo, implying DONJON consumes MULTICOMPO NSPH, which it does not (NSPH in L_MULTICOMPO is inert to DONJON NCR).
  - Refutation: The "MULTICOMPO GROUP/*/NSPH" render is unreachable from product data — the only summary producer hardcodes accepted_sph_consumption_format="macrolib" (summarize_outputs.py:205, pinned by tests and the shipped fixture), the no-field fallback prints "ASCII" not "MULTICOMPO", and even a hand-crafted multicompo deep link lands on the Convert page where SphHandoffCard (ConvertReport.tsx:97, convertSphHandoff.ts:24-29) explicitly warns that only the L_MACROLIB NSPH route is validated — so nothing silently implies DONJON consumes MULTICOMPO NSPH.
- In the mock converted demo, the bundle manifest probe reports 'valid / ready to share' for a bundle the user never created, contradicting the sibling 'Manifest after bundle' label and the status line saying bundling still waits.
  - Refutation: The mock world deliberately (test-pinned in test_web_convert_workflow_bundle.py) models a pre-existing bundle at /mock/home/openmc-runs/c5g7/bundle — the mock file browser, file-status, and bundle-inspect endpoints all agree — and the same UI section that shows the probe explicitly says "bundle dir exists" (OutputActions.tsx:590) and "an existing bundle directory is present" (OutputActions.tsx:786), so the probe correctly reports on-disk state rather than contradicting it; moreover the cited "status line saying bundling still waits" cannot co-render, since all waiting/blocked bundle strings require !outputReady, which is mutually exclusive with the "converted" mode that enables the probe.
- Two competing numbered 01-03 step sequences for the same SPH route render stacked on one page — the 'recommended demo path' card and the 'Main line' panel — with conflicting step meanings and ordering.
  - Refutation: Both cards do co-render with 01-03 lists when equivalence=sph, but they are explicitly differentiated — eyebrows "recommended demo path" (OpenmcSphMainlineCard.tsx:27) vs "Main line" (OpenmcProductionPathPanel.tsx:143), emerald vs cyan styling, distinct titles and body text explaining the demo uses pre-bundled minicase evidence (hence no run step) — so the claimed impact "cannot tell which is the actual main line" is contradicted by the literal "Main line" label.

## What held up under attack (no action needed)

- Zero console errors across the entire walk (all pages, both demo flows).
- /donjon deck skeletons match the validated benchmark patterns exactly (HEXZ + SNT DIAM 1 SN 8 SCAT 2 + SPLITL 2, HBC COMPLETE VOID; the three field-tested caveats — 72-char SEQ_ASCII, REFL/ALBE hex leak, mixture_names order — are all in the checklist).
- /pygan mock compare is honest (labels itself "mock fixture") and the real doctor probe works.
- Settings persist via localStorage and propagate as placeholder + "Use saved prefix" (though the copy undersells the scope — see CONFUSING list).
- Copy buttons give "Copied" feedback; demo Fill/dry-run/convert progression on /convert is a genuinely good progressive flow.
- /openmc "Plan workflow" report (Readiness/Artifacts/Next actions) is clear and correct.