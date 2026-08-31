# Frame packet: 09-attack-boundaries

## Project inputs

- Project: /Users/kodywildfeuer/.copilot/session-state/d9677ff3-485e-4a62-b74e-3e213b208701/files/rapp-vision-frame-chains-films/videos/frame-chains-paired-films
- Design tokens: /Users/kodywildfeuer/.copilot/session-state/d9677ff3-485e-4a62-b74e-3e213b208701/files/rapp-vision-frame-chains-films/videos/frame-chains-paired-films/frame.md
- RULES_DIR: /Users/kodywildfeuer/.agents/skills/hyperframes-animation/rules

## Assigned storyboard block

## Frame 9 — Attack every boundary

- scene: Control passes, nine attack receipts accumulate, and replay resolves the detector field into one inspectable rejection map.
- voiceover: "Now attack the timeline nine different ways. Every hostile candidate reaches the exact red boundary that explains its rejection, then replay rebuilds the receipt."
- duration: 11.179s
- transition_in: zoom-through
- status: outline
- src: compositions/frames/09-attack-boundaries.html
- type: social_proof
- persuasion: Adversarial proof
- beat: escalation + confidence
- blueprint: agent-progress-theater (Adapt)
- asset_candidates: assets/proof-clips/09-attack-timeline/source.webm — real control, nine attacks, quarantine, and replay receipt
- focal: assets/proof-clips/09-attack-timeline/source.webm
- roles: source.webm = background proof footage
- sfx: riser, error, chime

Adapt: keep the working-state theater, replacing a generic checklist with the real nine-detector attack sequence and replay receipt.
Scene 1 (0.0–2.4s): the real control result sits centered and large; `CONTROL / ACCEPT` reveals as a restrained technical title with one blue progress bar.
Scene 2 (2.4–7.2s): on “attack the timeline nine different ways,” nine detector labels cascade in over the live footage (`waterfall-entry`) as the red states accumulate; the count advances only when each real rejection appears.
Scene 3 (7.2–9.8s): when “the exact red boundary” is named, rack-focus to the detector grid (`depth-of-field-blur`) and draw one route from candidate to rejecting layer (`svg-path-draw`).
Scene 4 (9.8–11.179s): replay resolves into `9 REJECTED / HEAD PRESERVED`; a soft chime marks the completed receipt, then the frame holds.

narrativeRole: Replace a claim of robustness with visible evidence that each independent detector can turn red.
keyMessage: Rejection is explainable at the exact boundary that caused it.

## Selected blueprint: agent-progress-theater

# agent-progress-theater — Agent Progress Theater

**intent**: Agent work performed as WORKING-STATE theater — a short trigger beat hands the frame to the machine, which then visibly _works_: loaders spin, status phrases swap, dots pulse, counters tick — before the receipt arrives as a card whose rows cascade in and CHANGE STATE (badges flip to checks, labels strike through, severity pills read out), or as a conversation thread building message-by-message onto a camera push-in payoff. The subject is the machine performing labor over time. It is NOT a typed prompt awaiting output (no prompt/input is ever typed — the trigger is a click, a menu choice, or an already-running scan); NOT `cursor-ui-demo` (at most ONE igniting click here, then the cursor exits and the UI performs itself); NOT `grid-card-assemble` (rows there assemble into a static enumeration and hold — rows here are alive: they arrive as agent output and then MUTATE, checking off one by one while the viewer watches).

**roles served**

- Key_Feature (from `agent-progress-theater`): when the feature is the agent doing multi-step work (build a plan / scan a repo / fix a vulnerability / handle infra for you) and the proof is status theater — a loader lockup with a typed label, status couplets swapping under an `[accent]` spinner, then a checklist/findings card that populates and checks off in front of the viewer.
- Key_Feature (from `message-thread-payoff`): when the agent's work lives inside a conversation or automation thread — user/agent bubbles and tool-call/reply cards popping in sequence, the working state carried by pulsing loading dots or rapidly ticking diff counters, resolved by ONE camera push-in tight on the confirmation line (`[reaction pill]`, "Sent using `[@Bot]`", a thank-you bubble).

**duration**: 4.2–11.6s (short members are a single card-and-check-off or thread beat at ~4–5s; long members chain trigger → interstitial → status swaps → receipt card at ~9–12s; thread payoff spans 4.2–9.1s)

**shot structure** (a warm flat canvas — `[off-white / warm beige / near-white bg]`, optional `[faint grid / dot-grid / wavy-line]` texture; white rounded cards with soft drop shadows; ONE `[working accent]` color reserved for the machine (spinner, status words, active step) and one `[done color]` for completion (checks, "Completed"); camera static or ONE slow move — motion is overwhelmingly element-level springs, staggers, and state flips. Two folded sub-shapes — **(A) checklist/findings theater** and **(B) message-thread payoff**.)

- **Scene 1 (0.0–~1.5s) — the trigger.** Something asks the machine to work, in ONE beat:
  - _Variant — option menu (A)_: a centered white pill card poses `[the question]`; it SPRINGS open downward into a rounded menu — `[3–4 option rows]` fade/slide in staggered, each with a number badge. A cursor enters, hover-dances between rows (a pale `[hover fill]` highlight follows it), and CLICKS the chosen row (~press-down spring); the whole menu scales down toward its center and fades out. This is the only cursor appearance in the shot.
  - _Variant — modal click (A)_: close-up of a white modal with `[Dismiss]` / `[action button]`; a hand cursor clicks the action (quick press-down spring); the modal fades away. Optionally followed by a serif `[interstitial line]` on the bare canvas — words land staggered, hold, fade out word-staggered as the bg swaps.
  - _Variant — already working (A)_: a `[Scan in progress]`-style state — a thin `[accent]` arc spinner rotating over a heading + body copy + a `[Starting…]` pill (cursor resting on it, motionless); only the spinner moves. The whole scene then rapidly scales up and fades — a push-through exit.
  - _Variant — workspace push-through (A)_: a rapid camera push-in THROUGH a multi-panel `[workspace: builder / editor / terminal]` — panels scale past the viewport edges and clear away to the bare canvas.
  - _Variant — thread opener (B)_: a `[user bubble]` spring-pops in ("`[the ask]`"), OR a stats card pops in whose green/red `[diff counters]` rapidly tick and settle — the automation's opening receipt.

- **Scene 2 (~1–4s) — the working state (the machine performs).** The frame belongs to the machine; nothing is clickable. Pick 1–3 working motifs and CHAIN them:
  - A loader lockup: a spinning `[accent asterisk / arc]` beside a `[working label]` typed on rapidly ("`Buildi` → `Building plan…`"), a left→right shimmer sweep passing through the letters; the spinner may momentarily morph asterisk↔dot and back.
  - Status couplets: 2–3 centered pairs — a dark `[action line]` over an `[accent status word]` ("Thinking…", "Noodling…") with its spinner — swapping via quick fades/slides at a steady cadence.
  - A `[scan/tool label]` types/expands rightward to its full string, then SHRINKS and DOCKS to the top-left as a fixed corner header (the canvas now belongs to what it produces).
  - A status heading flips tense as rows land beneath it ("Using `[Tool]`" → "Used `[Tool]`"), with a gently pulsing "Thinking" and gray meta-lines ("Exploring `[N]` files…") fading in below.
  - _Variant — thread machinery (B)_: the `[agent reply]` fades/slides up, then a monospace `[tool_call]` line appears beneath it — small icon + `[tool name]` + three pulsing loading dots; OR an instruction bubble scrolls into view (internal window scroll, frame static) followed by a `[brand logo]` pop-in beside a "Sending message…" row. **The pulse dies the instant the result lands** — dots vanish as the payload arrives.

- **Scene 3 (~2–4s) — the receipt cascades in (the payoff engine).** The work materializes as a card that BUILDS:
  - _Variant — checklist (A)_: a white `[Progress / summary]` pill or card SPRING-pops in with a bounce, then springs open downward (or the summary card glides UP as a taller `[findings]` panel expands beneath it). Rows cascade in one by one — slide-up + fade, staggered — each with `[number badge / severity pill]` + `[label]` + optional gray `[meta line]`. Then the STATE MUTATION runs: badges flip one by one from numbered outline to a solid `[done color]` circle + white checkmark (slight scale bounce), the checked label simultaneously strikes through and dims; pending items keep partially-drawn arc outlines animating. End the run mid-list — some items checked, some still numbered — the work is visibly _ongoing_.
  - _Variant — thread payload (B)_: the camera pushes in / pans down centering the `[tool_call]` line as a white payload card expands downward from it — 2–4 light monospace `[key: value]` lines fading in. Then the `[resolution message]` expands into place below (inline `[code chips]` and `[link]` coloring), OR a dark `[thread card]` scales up from a status row to DOMINATE the frame while the background darkens, its `[reply]` expanding into place under a "1 reply" divider.

- **Scene 4 (final ~1–2.5s) — resolve.** Two endings:
  - _Variant — hold / scroll (A)_: the finished (or mid-mutation) card stack holds static to the end, OR the viewport scrolls down the final card (fast in the last beat) revealing `[a second heading + numbered list]`, ending mid-list. A slow continuous zoom into the card may run underneath (the header drifts off the top of frame).
  - _Variant — payoff push-in (B)_: ONE camera push-in + pan-down lands tight on the payoff line — "`Sent using [@Bot]`" / the confirmation + `[thank-you bubble]` spring-in — then a `[reaction button]` springs into an active pill with bouncy overshoot and a count. The push eases into a gentle near-imperceptible drift and the clip ends on the close-up. No end card.

**motion vocabulary**: pill springs open downward into a menu/checklist · option rows fade/slide in staggered · cursor hover-dance (pale highlight fill follows the cursor between rows) · single igniting click with press-down spring · menu scale-down fade exit · modal fade-away · thin `[accent]` arc spinner rotation · spinning asterisk loader · asterisk↔dot morph · typed-on loader label with caret · left→right text shimmer sweep · serif interstitial with word-staggered fade in/out · status couplets swapping via quick fades/slides under an `[accent]` spinner · pulsing "Thinking" label · status heading tense flip (Using→Used) · label types/expands rightward then shrinks and docks as a corner header · scene scale-up/fade push-through exit · rapid camera push-in through a multi-panel workspace · slow continuous zoom into a card (header drifts off frame) · summary card spring pop with bounce · card glides up as a panel expands beneath it · anchored downward panel/payload expansion · rows stagger in (slide-up + fade) · badge flip from numbered outline to solid circle + white checkmark with scale bounce · strikethrough + dim on completion · partially-drawn arc outlines animating on pending items · severity-pill readouts (Critical / High) · viewport scroll down the final card · chat bubble spring scale-up pop-in · reply fade/slide-up · monospace tool-call line with three pulsing loading dots (dots die the instant the result lands) · payload card expands downward from the line · green/red diff counters rapid tick-and-settle · internal window scroll (frame static) · brand logo pop-in beside a status row · card scales up from a row to dominate the frame while the background darkens · reply message expands into place · inline code chips / link coloring · reaction button springs into an active pill with bouncy overshoot + count · camera push-in + pan-down centering the payoff · slight pull-back · gentle end drift · static hold.

**rule mapping**

- pill springs open downward into a menu / panel expands beneath a gliding card / payload card expands downward from a tool-call line → `anchored-layout-expand` (edge-anchored container growth: height-masked wrapper + inner counter-translate, container drawn at final size); spring flavor from `spring-pop-entrance`
- option rows / findings rows / task rows stagger in (slide-up + fade) → `spring-pop-entrance` (staggered-group form, ≤500ms cap) or `gsap-effects` (plain fade+translate stagger) — NOT `waterfall-entry` (its binary no-fade arrival law contradicts this dialect's soft fade/slide cascade)
- cursor glides to a row and clicks; hand cursor clicks the modal button → `cursor-click-ripple` (move + press) + `press-release-spring` (the button's press-down spring)
- pale hover-highlight fill following the cursor between rows → `gsap-effects` (a background fill translated row-to-row; no dedicated rule needed)
- menu scale-down fade exit / scene scale-up push-through exit / palette-for-window swap → `scale-swap-transition`
- thin arc spinner rotation / spinning asterisk loader → `svg-icon-enrichment` (rotating internal SVG parts via `setAttribute('transform','rotate(deg cx cy)')`; timeline-driven, finite)
- asterisk↔dot morph and back → `scale-swap-transition` (two elements morphing at the same center)
- typed-on loader label ("Building plan…") / scan label typing to its full string → `discrete-text-sequence` (+ `context-sensitive-cursor` for the caret)
- left→right shimmer sweep through the loader letters → `ambient-glow-bloom` (single-pass traveling sheen) or `css-marker-patterns` (highlight sweep) — pick sheen for light-on-text, marker for a drawn band
- serif interstitial word-staggered fade in/out; status couplets swapping on a cadence → `dynamic-content-sequencing` (phrase windows) + `discrete-text-sequence` (the whole-state swaps); per-word stagger via `gsap-effects`
- pulsing "Thinking" label / three pulsing loading dots (phase-offset) → `sine-wave-loop` (finite repeats; kill the tween at the resolve beat — see doctrine note)
- status heading tense flip (Using→Used) / gray meta-lines fading in / final-token snaps → `discrete-text-sequence`
- label shrinks and docks to the top-left as a fixed corner header → `gsap-effects` (plain scale + translate tween; no dedicated rule needed)
- rapid camera push-in through the multi-panel workspace → `viewport-change` (the push) + `multi-phase-camera` (phasing) + optional `motion-blur-streak` (velocity blur as panels clear the frame)
- slow continuous zoom into the receipt card (header drifts off top) → `multi-phase-camera` (steady-push phase) or `viewport-change`
- summary card / progress pill / chat bubble / brand logo / file chip spring pop-in → `spring-pop-entrance`
- summary card glides up as the findings panel expands beneath → `gsap-effects` (the glide) + `anchored-layout-expand` (the panel)
- badge flip: numbered outline → solid circle + white checkmark with scale bounce → `scale-swap-transition` (outline↔solid swap at same center) + `svg-path-draw` (checkmark draw-in) + `spring-pop-entrance` (the bounce); the pending→active→complete progression itself → `dynamic-content-sequencing` (a snap state machine, per cursor-ui-demo's workflow-approve-press precedent)
- strikethrough + dim on the checked label → `css-marker-patterns` (strike-through draw) + `gsap-effects` (opacity dim)
- partially-drawn arc outlines animating on pending items → `svg-path-draw` (partial dashoffset, held mid-draw)
- viewport scroll down the final card / internal window scroll under a static frame → `gsap-effects` (transform-only content translate inside a masked window) — use `viewport-change` only if the FRAME moves
- green/red diff counters rapid tick-and-settle → `counting-dynamic-scale` (numeric proxy count-up; suppress the scale-growth component — these tick at fixed size)
- dark thread card scales up from a row to dominate the frame → `card-morph-anchor` (row → full-frame morph + handoff) with the background darkening as a `gsap-effects` overlay fade
- reply message / resolution line expands into place → `spring-pop-entrance` (soft overshoot) or `anchored-layout-expand` for a true downward growth
- reaction button springs into an active pill with overshoot + count → `spring-pop-entrance` (the pop) + `press-release-spring` (activation flavor) + `counting-dynamic-scale` (the count, if it ticks)
- camera push-in + pan-down centering the tool call / the payoff line → `coordinate-target-zoom` (non-centered target: scale + counter-translate) or `viewport-change`
- slight pull-back then gentle end drift → `multi-phase-camera` (pull-back phase + continuous micro-drift; keep the drift near-imperceptible)
- static hold on the final stack → no rule needed

**camera modifier** (default is a STATIC frame — the theater is element-level; at most ONE real move per shot, chosen from):

- Trigger push-through: a rapid push-in through the opening workspace that clears to the bare canvas → `viewport-change` + `multi-phase-camera`, optional `motion-blur-streak`.
- Receipt zoom: one slow continuous zoom into the checklist card across the whole mutation run, letting the header drift off the top → `multi-phase-camera` (steady push).
- Payoff push-in (sub-shape B's defining move): static through the build, then ONE push-in + pan-down tightening onto the confirmation line, easing to a micro-drift end → `coordinate-target-zoom` / `viewport-change` + `multi-phase-camera` (drift).
- Everything else — swaps, cascades, check-offs, scrolls — happens on a locked frame (any "scroll" is the content translating inside its window, not the camera).

**doctrine note (idle-motion ban)**: the working-state motifs (spinner rotation, pulsing dots, pulsing "Thinking") brush against motion-doctrine's idle-motion ban — here they are DIEGETIC: the pulse _performs_ "the machine is working" and is the narrative content of Scene 2, not decorative breathing. Keep every loop finite, timeline-driven, and seek-safe (`sine-wave-loop` finite repeats, `svg-icon-enrichment` rotation), and kill it at the exact frame the state resolves — the corpus does this explicitly (the loading dots vanish the instant the payload card expands; the spinner swaps out with the loader lockup).

## Selected motion rule: depth-of-field-blur

---
name: depth-of-field-blur
description: Selective-focus rack-focus — pull the eye to a focal element by GSAP-tweening filter blur (+ a small opacity dim) on the off-focus layers while the focal one stays sharp. Drive blur via a `--dof` CSS var; finite tweens, no CSS transition, deterministic. Covers single focal pull, rack-focus between two depth planes, and blur-the-cluster-while-pushing-in.
metadata:
  tags: blur, focus, depth-of-field, dof, rack-focus, filter, dim, spotlight, cinematic, push-in
---

# Depth-of-Field Blur (Selective Focus / Rack Focus)

Pulls the eye to one focal element by **blurring** (and slightly **dimming**) everything around it while the focal layer stays sharp — the camera's depth-of-field falling off the background, or a rack-focus shifting which plane is in focus. `filter` and `opacity` are paint-only, so both tween seek-safe. This is the backing rule for the focus-falloff beat the blueprints reach for: outer nodes blurring during a push-in (`constellation-hub`), rack-focus across a parallax card stack (`cursor-ui-demo`), non-highlighted cards dimming to spotlight a hero metric (`dataviz-countup`).

## How It Works

Every layer carries a `--dof` custom property (px of blur), read by `filter: blur(var(--dof))`, plus its own `opacity`. A GSAP tween advances each layer's `--dof` from `0` to its target blur and its opacity from `1` to a dim level over the focus-shift window. The focal layer's `--dof` stays `0`. Per-layer targets derive from `data-depth` / index, so the falloff is identical on every seek.

Three mechanics, same primitive:

1. **Focal pull** — one window: off-focus layers go sharp(0) → blurred while the focal layer holds at 0. The eye is pulled to the only thing still crisp.
2. **Rack focus** — two adjacent windows on the same property: plane A's blur ramps 0 → max at the same position plane B's ramps max → 0. State continuity matters exactly as in `press-release-spring`: A's resting blur after the rack must equal what B held before it — author both as tweens on the same `--dof` at the same position so the hand-off is seamless.
3. **Blur-the-cluster-while-pushing-in** — the DoF tween runs at the SAME timeline position as a camera push-in (`multi-phase-camera` / `coordinate-target-zoom`): "the world recedes" and "we push in" read as one move.

## Recipe

```html
<div class="world" id="world">
  <!-- Focal layer — stays sharp -->
  <div class="layer focal" id="focal">{FocalLabel}</div>
  <!-- Off-focus layers — blur + dim; data-depth orders near→far -->
  <div class="layer ctx" data-depth="1">{Context A}</div>
  <div class="layer ctx" data-depth="2">{Context B}</div>
  <div class="layer ctx" data-depth="3">{Context C}</div>
</div>
```

```css
.world {
  /* single wrapper so a concurrent camera push-in transforms everything
     together; DoF is independent of the camera */
  position: relative;
  width: 100%;
  height: 100%;
  transform-origin: 50% 50%;
}
.layer {
  --dof: 0px; /* px of blur; filter reads it — starts sharp */
  filter: blur(var(--dof));
  will-change: filter; /* promotes the layer so per-frame re-rasterization is cheap */
}
.focal {
  z-index: 2; /* sharp layer must sit ABOVE the blurred ones, or its crisp
     edges read as bleeding into the haze */
}
.ctx {
  z-index: 1;
}
```

```js
// Mechanic 1 — FOCAL PULL. Blur scales with data-depth so far planes blur
// more than near ones; the focal layer (--dof: 0, opacity: 1) is untouched.
gsap.utils.toArray(".ctx").forEach((el) => {
  const depth = Number(el.dataset.depth) || 1;
  tl.to(
    el,
    {
      "--dof": `${BLUR_PER_DEPTH * depth}px`,
      opacity: DIM_LEVEL, // dim, not gone
      duration: FOCUS_DUR,
      ease: "power2.inOut",
    },
    FOCUS_START,
  );
});
```

## Variations

- **Rack focus between two depth planes** — `gsap.set` plane B pre-blurred BEFORE the rack (no pop), then two tweens sharing `RACK_START` + `RACK_DUR`: A → `MAX_BLUR` + `DIM_LEVEL`, B → `0px` + `1`. Shared window makes them cross at the midpoint.
- **Blur the cluster while pushing in** — run the focal-pull tweens at the same position + duration as a camera tween on `#world` (`scale/x/y`, `power2.inOut`). Camera transforms the world; DoF tweens the layers — independent property channels, no conflict.
- **Spotlight a hero metric in a card grid** — `gsap.utils.toArray(".card:not(.hero)")` all defocus (`GRID_BLUR` + `DIM_LEVEL`) on one shared window; heroes are skipped.
- **Refocus / settle** — if the beat resolves back to "everything visible" (or hands off to a crossfade needing a clean outgoing frame), ramp all `--dof` back to `0px` / opacity 1 over the tail (`REFOCUS_START + REFOCUS_DUR ≤ DURATION`).
- **Bounded focus-breathing on the focal layer (optional)** — a finite `ease:"none"` driver writes `Math.max(0, Math.sin(p)) * FOCAL_BREATH_PX` into the focal `--dof` during a hold. Keep it ≤ ~0.6px or it reads as "still focusing"; default to omitting it.

## Values

| token                 | range                                  | notes                                                                                                    |
| --------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| BLUR_PER_DEPTH        | 3–6 px per depth step                  | a 3-plane stack tops out ~9–18 px; low = gentle DoF, high = tilt-shift falloff                           |
| MAX_BLUR              | 8 soft → 16 default → 24 heavy px      | terminal blur for a fully-defocused plane; above ~24 px on a big surface, shrink/group the layer instead |
| GRID_BLUR             | 6–12 px                                | pushes cards back without losing the grid's shape                                                        |
| DIM_LEVEL             | 0.4 strong → 0.55 default → 0.7 subtle | rarely below 0.35 — fully dark reads as "removed," not "defocused"                                       |
| FOCUS_DUR             | 0.5–1.2 s                              | a rack/pull is a deliberate move, not a snap; shorter = snap focus, longer = languid                     |
| RACK_START / RACK_DUR | shared by both planes                  | `gsap.set` the pre-blurred plane BEFORE `RACK_START`                                                     |
| FOCAL_BREATH_PX       | ≤ 0.6 px, period 2–3 s                 | barely-there nicety                                                                                      |
| FOCAL vs CTX sizing   | context smaller / grouped              | small context layers let a modest radius still read as "out of focus" — and blur cheaply                 |

Tokens: dark `{bgGradient}` so the sharp focal layer reads as lit and forward; heavy display `{font}` weight — blurred copy needs it to stay shape-legible.

## Critical Constraints

- **Tween the `--dof` variable on the timeline** — reading `filter: blur(var(--dof))` keeps the blur on the HF seek clock.
- **Blur the SMALL / GROUPED layers, not the giant one.** Filter cost scales with radius × pixel area; a 20 px blur on a full-frame background is the worst case. Keep per-layer radius ≤ ~24 px on large surfaces and lean on the `opacity` **dim** to do the push-back work — dim + modest blur reads more like real DoF than blur cranked to the max.
- **`will-change: filter`** on every layer whose blur animates (drop it after settle if the layer also does heavy transform work).
- **Focal layer stays genuinely sharp** — `--dof: 0`, untouched (or breathing ≤ 0.6 px). Any visible blur on the focal element kills the "this is the thing" read.
- **State continuity on a rack** — the outgoing plane starts at the blur the incoming plane was holding, and vice-versa; adjacent tweens on the same `--dof` at the same position.
- **DoF is independent of the camera** — blur the layers, transform `.world` for the push-in; don't fake DoF with the camera transform or vice-versa.
- **Settle sharp before a hand-off** — refocus to `--dof: 0` in the tail if the next beat is a crossfade/push; handing off mid-defocus reads as "the render glitched."
- **Sharp focal layer above blurred layers** (`z-index`).

## See also

[multi-phase-camera.md](multi-phase-camera.md) (the push-in this rule's falloff accompanies) · [coordinate-target-zoom.md](coordinate-target-zoom.md) (zoom onto the focal core — the `constellation-hub` hook) · [viewport-change.md](viewport-change.md) (pan + rack across a tilted card plane) · [counting-dynamic-scale.md](counting-dynamic-scale.md) (hero metric counts up sharp — the `dataviz-countup` spotlight) · [3d-page-scroll.md](3d-page-scroll.md) (the parallax stack to rack between) · [sine-wave-loop.md](sine-wave-loop.md) (post-rack idle; keep both amplitudes tiny).

## Selected motion rule: svg-path-draw

---
name: svg-path-draw
description: Animate SVG paths drawing progressively using stroke-dasharray and stroke-dashoffset.
metadata:
  tags: svg, stroke, draw, path, reveal, icon, vector
---

# SVG Path Draw

Reveals an SVG shape by animating its stroke as if a pen were tracing it. Two stroke properties together: **`stroke-dasharray = <pathLength>`** makes the entire path one dash; **`stroke-dashoffset`** starts at the path length (dash shifted fully out of view → invisible) and tweens to `0` (fully drawn). The length comes from the DOM API `path.getTotalLength()` — measured, never guessed.

Works on anything with a stroke: `<path>`, `<circle>`, `<rect>`, `<line>`, `<polyline>`, `<polygon>`, `<ellipse>`.

## Recipe

```html
<!-- inside a standard scene clip -->
<svg class="logo-mark" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
  <path id="bar-left" d="M 60 40 L 60 160" />
  <path id="bar-right" d="M 140 40 L 140 160" />
  <path id="bar-mid" d="M 60 100 L 140 100" />
</svg>
```

```css
.logo-mark path {
  fill: none; /* outline-only draw — a fill would appear immediately and ruin the reveal */
  stroke: {accentColor};
  stroke-width: 12;
  stroke-linecap: round; /* softer endpoints */
  stroke-linejoin: round;
}
```

```js
// Setup: measure each path and set its dash pattern. Real measured geometry, not a magic number.
document.querySelectorAll(".logo-mark path").forEach((p) => {
  const len = p.getTotalLength();
  p.style.strokeDasharray = `${len}`;
  p.style.strokeDashoffset = `${len}`;
});

// Stagger draws so the eye reads continuous motion — each segment starts at
// ~70-80% of the previous segment's duration, before it finishes.
tl.to(
  "#bar-left",
  { strokeDashoffset: 0, duration: SEGMENT_DRAW_DUR, ease: "power2.out" },
  SEG_1_START,
);
tl.to(
  "#bar-right",
  { strokeDashoffset: 0, duration: SEGMENT_DRAW_DUR, ease: "power2.out" },
  SEG_2_START,
);
tl.to(
  "#bar-mid",
  { strokeDashoffset: 0, duration: FINAL_SEGMENT_DUR, ease: "power2.out" },
  SEG_3_START,
);

// Companion wordmark fades in only after the last stroke settles.
tl.to(
  ".brand-line",
  { opacity: 1, duration: BRAND_FADE_DUR, ease: "power1.out" },
  BRAND_FADE_START,
);
```

## Variations

- **Ring starting at 12 o'clock** — `<circle>` / `<rect>` strokes start at 3 o'clock by default; rotate the element `-90deg` so a progress ring draws from the top:

```html
<circle
  cx="100"
  cy="100"
  r="60"
  id="ring"
  style="transform-origin: 100px 100px; transform: rotate(-90deg)"
/>
```

- **Linear (constant-speed) draw** — `ease: "none"` for a steady-rate "real pen" trace.
- **Draw then fill** — for filled shapes, tween `fillOpacity: 0 → 1` AFTER the stroke completes (requires `fill-opacity: 0` initially and a real `fill` in CSS):

```js
tl.to(
  "#path",
  { strokeDashoffset: 0, duration: SEGMENT_DRAW_DUR, ease: "power2.out" },
  SEG_1_START,
);
tl.to(
  "#path",
  { fillOpacity: 1, duration: FILL_FADE_DUR, ease: "power1.out" },
  SEG_1_START + SEGMENT_DRAW_DUR,
);
```

## Values

| token             | range                                   | notes                                                                                              |
| ----------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------- |
| SEGMENT_DRAW_DUR  | 0.3–0.8s                                | fast snap vs deliberate pen trace; >~1s feels sluggish for a logo reveal                           |
| FINAL_SEGMENT_DUR | 60–80% of SEGMENT_DRAW_DUR              | proportional to segment length — a short connector at full duration reads slower than its siblings |
| SEG_N_START       | previous start + 70–80% of its duration | reads as continuous motion, not N isolated animations                                              |
| SEG_1_START       | 0–0.4s                                  | a small ~0.2s lead-in lets the viewer settle before motion                                         |
| BRAND_FADE_START  | ≥ last stroke end (+ ~0.2s beat)        | earlier and the wordmark competes with the draw                                                    |
| BRAND_FADE_DUR    | 0.3–0.8s                                | snap (urgent) vs glide (premium)                                                                   |

Ease families are discrete choices: **stroke draws** use `power2.out` (a hand lifting at end of stroke) or `none` for constant speed — never `back.out` / `elastic.out` (pens don't bounce). **Fades** use `power1.out`.

## Critical Constraints

- **`fill: none`** for outline-only draws — otherwise the fill appears immediately.
- **Dasharray/dashoffset = the measured `getTotalLength()`**, set at setup; requires the SVG in the DOM (inline SVG is fine; a loaded `<image>` SVG is not).
- **Complex paths**: if `getTotalLength()` looks wrong, overestimate slightly (`len * 1.05`) — too large is invisible at animation start; too small clips the end.
- **Stagger multi-path draws at ~70–80%** of the previous segment's duration.
- **A drawn line must land on something.** When the path is a connector (rail, beam, underline, callout) rather than a shape, both endpoints must sit on real elements and the draw must do a job — reveal, route, validate, or emphasize. A stroke that only decorates empty space reads as filler; attach it or cut it.

## See also

`svg-icon-enrichment` (internal parts animate after the outline draws) · `counting-dynamic-scale` (stroke draws an icon while a number counts up) · `hacker-flip-3d` (logo draws, wordmark decodes beneath).

## Selected motion rule: waterfall-entry

---
name: waterfall-entry
description: Staggered ARRIVAL cascade — words/elements whip in from below (one consistent direction), each starting before the previous settles, an accelerating wave that resolves into a composed layout. Title cards, segment openers, list/feature intros. Opacity is BINARY 0→1 via tl.set — never fade an arrival.
metadata:
  tags: entrance, cascade, stagger, kinetic-text, title-card, segment-opener, arrival, waterfall, whip
---

# Waterfall Entry

Staggered ARRIVAL cascade: words/elements whip in from below (one consistent direction),
each starting before the previous settles — an accelerating wave that resolves into a
composed layout. Title cards, segment openers, list/feature intros.

**This is an in-scene arrival, not a seam.** Its seam sibling is the waterfall CUT
(`cut-the-curve` doctrine skill, `seams/waterfall-cut.md`); do not mix their rules:

|               | Entry (this rule — arrival)                   | Waterfall Cut (seam)                                      |
| ------------- | --------------------------------------------- | --------------------------------------------------------- |
| Opacity       | BINARY 0→1 via `tl.set` at entry — never fade | ignites at 0.35 mid-path — the fade IS the velocity trick |
| Axis default  | Y, from below                                 | X, riding the current                                     |
| Outgoing side | none                                          | words ramp out on mirrored power4.in                      |

## Choreography

- **Overlap, don't queue** — next element starts within ±2 frames of the previous
  settling; gaps SHRINK across the cascade; the last element snaps.
- **Velocity varies by weight** — heavy/anchor elements travel further and longer;
  light words/punctuation snap in tight:

| Parameter | Anchor/heavy | Normal word | Light/punctuation |
| --------- | ------------ | ----------- | ----------------- |
| Y offset  | 60–80px      | 40–50px     | 30–48px           |
| Duration  | 0.16–0.20s   | 0.13–0.16s  | 0.10–0.13s        |
| Overlap   | 0–2f gap     | 1f overlap  | 1–2f overlap      |

- Ease `power4.out` (`expo.out` for extra snap); never `.inOut` on an entry.
- One direction per cascade.
- Split the FINAL word into fragments to extend the climax; fragments travel further.
- Post-settle, the group usually slides to make room for the next beat — that's
  [nudge-curve.md](nudge-curve.md).

## JS

Each element: `tl.set` (instant reveal + offset) then `tl.to` (whip to rest).
`nextStart = prevStart + prevDuration − (overlapFrames × F)`; +overlap = cascade,
−overlap = deliberate gap. CSS: elements start `opacity: 0; display: inline-block`.

```js
var F = 1 / 60;
var t0 = 0.1;
// anchor (heaviest): biggest travel, longest settle
tl.set("#el-1", { opacity: 1, y: 80 }, t0);
tl.to("#el-1", { y: 0, duration: 0.18, ease: "power4.out" }, t0);
// normal word: 2 frames after the anchor finishes
var t1 = t0 + 0.18 + 2 * F;
tl.set("#el-2", { opacity: 1, y: 45 }, t1);
tl.to("#el-2", { y: 0, duration: 0.15, ease: "power4.out" }, t1);
// light word: 1 frame BEFORE the previous finishes (overlap)
var t2 = t1 + 0.15 - F;
tl.set("#el-3", { opacity: 1, y: 40 }, t2);
tl.to("#el-3", { y: 0, duration: 0.14, ease: "power4.out" }, t2);
// split final-word fragments: tightest overlap, extra travel (lighter)
var t3 = t2 + 0.14 - F;
tl.set("#frag-a", { opacity: 1, y: 70 }, t3);
tl.to("#frag-a", { y: 0, duration: 0.16, ease: "power4.out" }, t3);
var t4 = t3 + 0.14 - F;
tl.set("#frag-b", { opacity: 1, y: 70 }, t4);
tl.to("#frag-b", { y: 0, duration: 0.15, ease: "power4.out" }, t4);
// punctuation: lightest, fastest
var t5 = t4 + 0.13 - 2 * F;
tl.set("#dot", { opacity: 1, y: 48 }, t5);
tl.to("#dot", { y: 0, duration: 0.12, ease: "power4.out" }, t5);
```

## Anti-patterns

| Don't                                                  | Instead                                                                           |
| ------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Queued entries (each waits for the previous to settle) | Overlap ±1–2 frames — the cascade is a wave, not a queue                          |
| Same offset/duration for every cascade element         | Vary by weight: anchors travel further, punctuation snaps                         |
| Gradual opacity fade on an arrival                     | Binary 0→1 via `tl.set` — fading fights the snap (seam cuts fade; arrivals don't) |
