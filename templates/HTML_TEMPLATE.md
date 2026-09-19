# HTML Template

The output is a single self-contained HTML file. For **MiniMax H3**, the default is the approved dark card-based production layout in [H3_PRODUCTION_LAYOUT.md](H3_PRODUCTION_LAYOUT.md), including an expanded upload-order checklist for every unit. Its locally bundled CSS/JS and structure take precedence over the older H3 rowspanned-table layout below; keep the H3 prompt, runtime, boundary and text shot-planning metadata contracts. Do not depend on a historical project path or prior conversation to build it. For **Seedance**, retain the house-template layout (historically `Shotlist_21_23_EN.html`); use a self-contained equivalent when that file is unavailable.

If the historical house file is unavailable, use a self-contained local layout implementing this document's structure; do not depend on an inaccessible prior conversation.

## Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Shotlist — Scenes {SCOPE} (with {PROMPT_TITLE})</title>
  <style>{HOUSE_CSS}</style>
</head>
<body>
<div class="container">
  <header class="top">
    <h1>Shotlist — <span>Scenes {SCOPE} (with {PROMPT_TITLE})</span></h1>
    <div class="sub">Prepared for {USERNAME} · {N_SHOTS} shots across {N_SCENES} scenes · {PROMPT_LANGUAGE_SUMMARY}</div>
    <div class="stats">
      <div class="stat"><div class="v">{N_SCENES}</div><div class="l">scenes</div></div>
      <div class="stat"><div class="v">{N_SHOTS}</div><div class="l">total shots</div></div>
      <div class="stat"><div class="v">{N_PLANS}</div><div class="l">plan types</div></div>
      {H3_RUNTIME_STAT}
    </div>
  </header>

  <div class="toolbar">
    <input type="text" id="search" placeholder="Search by text, dialogue, locations...">
    <select id="planFilter">
      <option value="">All plans</option>
      {PLAN_OPTIONS}
    </select>
    <button onclick="window.print()">🖨 Print / PDF</button>
    <button class="clear" onclick="resetFilters()">Reset</button>
  </div>

  <div class="toc">
    <div class="toc-row"><span class="toc-label">Scenes</span>{TOC_LINKS}</div>
  </div>

  <h2 class="block-title first">Scenes {SCOPE}</h2>

  {H3_PROJECT_PLANNING_BLOCKS}

  {SCENE_BLOCKS}

  <div class="empty-state" id="emptyState" style="display:none;">Nothing found. Try resetting the filters.</div>
</div>
<script>{HOUSE_JS}</script>
</body>
</html>
```

## Per-scene block

```html
<section class="scene pal-red" id="sc{N}">
  <div class="scene-head">
    <div class="scene-num-row">
      <span class="scene-num">SCENE {N}</span>
    </div>
    <h2 class="scene-title">{INT_EXT_HEADER}</h2>
    <div class="scene-meta">
      <span><b>Location:</b> {LOCATION_DESC}</span>
      <span><b>Mood:</b> <i>{MOOD}</i></span>
      <span class="shot-count">{N_SHOTS} shots</span>
    </div>
  </div>
  <div class="table-wrap">
    <table class="shotlist">
      <colgroup>
        <col style="width:60px"><col style="width:140px"><col style="width:140px"><col style="width:auto"><col style="width:30%"><col style="width:35%">
      </colgroup>
      <thead>
        <tr><th>#</th><th>Plan</th><th>Camera</th><th>Action</th><th>Scene text</th><th>{PROMPT_COLUMN_LABEL}</th></tr>
      </thead>
      <tbody>
        {SHOT_ROWS_WITH_PROMPTS}
      </tbody>
    </table>
  </div>
</section>
```

## Shot row + prompt cell

The first row of a prompt group carries the rowspanned `c-script` and `c-prompt` cells. Subsequent rows in the same group only have `c-num`, `c-plan`, `c-cam`, `c-act`.

```html
<tr data-scene="{N}" data-plan="{PLAN_CODE}">
  <td class="c-num">{SHOT_NUM}</td>
  <td class="c-plan"><span class="badge p-{PLAN_CLASS}">{PLAN_LABEL}</span></td>
  <td class="c-cam">{CAMERA_NOTE}</td>
  <td class="c-act">{ACTION_BEAT_EN}</td>
  <td class="c-script" rowspan="{GROUP_SIZE}">
    <div class="script-inner">{FULL_SCENE_TEXT_EN}</div>
  </td>
  <td class="c-prompt" rowspan="{GROUP_SIZE}">
    <div style="font-size:11px; line-height:1.6;">
      {PROMPT_BLOCKS}
    </div>
  </td>
</tr>
{ADDITIONAL_ROWS_NO_RIGHT_CELLS}
```

## Prompt block (one per independently generated clip; `H3_UNIT` in the H3 branch)

```html
<div style="border-top:1px solid #333; margin:12px 0 8px; padding-top:8px;">
  <b style="color:#22c55e;">{PROMPT_BLOCK_LABEL} {N}</b>
  <span style="color:#666; font-size:10px;">[{TAG}]</span>
  <button style="margin-left:8px;padding:2px 8px;background:#27272a;border:1px solid #3f3f46;border-radius:4px;color:#a1a1aa;font-size:10px;cursor:pointer" onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.textContent)">Copy</button>
</div>
<div class="prompt-block">{VIDEO_PROMPT}</div>
```

The `{TAG}` is a short bracketed shorthand like `[MS-CU · door open + boots]` or `[ECU · polaroid + Roko face]` — describes the prompt at a glance. For MiniMax H3, prefix the tag with the generation mode, effective duration, and aspect ratio, for example `[I2VA · 15.00s · 21:9 · MS-CU · paper crane]`; keep this metadata outside the copyable canonical prompt.

## MiniMax H3 scene-wide edit map

Before scene blocks, H3 deliverables use `{H3_PROJECT_PLANNING_BLOCKS}` to show:

- the full `H3_UNIT_BLUEPRINT` outline with total unit count, declared/packed runtime, and per-scene subtotals;
- the project `VOICE_BIBLE`, copying each stable character profile once in full;
- `{AUDIO_REFERENCE_MAP_BLOCK}` only when audio reference is active, showing each exact filename, locked character/source, vocal role, mode, retention marker, scope, and exclusions; render it as an empty string when inactive rather than displaying a placeholder or “none” notice;
- all `POST_NODES` with exact text, reveal time, screen/object placement, clean-plate requirement, and compositing note.

For H3, calculate `{PACKED_RUNTIME}` by summing the final numeric `data-duration-seconds` values after every split, merge, and exception revision. Render `{H3_RUNTIME_STAT}` exactly as:

```html
<div class="stat" data-h3-packed-runtime-seconds="{PACKED_RUNTIME}"><div class="v">{PACKED_RUNTIME}s</div><div class="l">packed runtime</div></div>
```

The one visible runtime element must carry `data-h3-packed-runtime-seconds="{PACKED_RUNTIME}"` and print the same `{PACKED_RUNTIME}s` value. A copied or hand-entered total is a build failure.

For Seedance, both `{H3_RUNTIME_STAT}` and `{H3_PROJECT_PLANNING_BLOCKS}` are empty.

Before the first H3 prompt block in every scene, show one `SCENE_SHOT_LADDER` table covering all internal shots in final playback order. Do not restart the shot-size/axis plan at each independent unit. Include unit/shot ID, time window, shot size and crop, lens/axis, attention target, action/prop phase, and cut trigger.

For every adjacent ordered `H3_UNIT` pair, add exactly one machine-readable boundary row. Example:

```html
<tr class="h3-boundary"
    data-h3-boundary="H3-01__H3-02"
    data-boundary-strategy="neutral_bridge"
    data-outgoing-frame="profile CU, phone raised, gaze begins to lift"
    data-incoming-frame="bulb eyeline-target insert, no readable mouth"
    data-cut-trigger="Suwan's gaze lands on the bulb">
  <td>H3-01 → H3-02</td>
  <td>neutral_bridge</td>
  <td>侧面近景、手机抬起、视线上移</td>
  <td>视线目标灯泡空镜、不可见口型</td>
  <td>目光落到灯泡时切；雨声连续</td>
</tr>
```

`data-boundary-strategy` must be exactly one of `exact_match_continuation`, `contrast_cut`, `neutral_bridge`, or `scene_transition`. `data-outgoing-frame`, `data-incoming-frame`, and `data-cut-trigger` must be nonempty. The visible table should also show continuity invariants, deliberate differences, requested versus supported/observed durations, head/tail edit handles, and current review status.

For MiniMax H3, replace the single block above with this paired Chinese director-storyboard and English six-section prompt block for every unit:

```html
<article class="h3-unit"
    data-h3-unit="{UNIT_ID}"
    data-unit-kind="{UNIT_KIND}"
    data-duration-seconds="{DURATION_SECONDS}"
    data-dialogue-effective-chars="{DIALOGUE_EFFECTIVE_CHARS}"
    data-relationship-turn="{RELATIONSHIP_TURN}"
    data-action-chain="{ACTION_CHAIN}"
    data-opening-state="{OPENING_STATE}"
    data-exit-state="{EXIT_STATE}"
    data-duration-exception-reason="{DURATION_EXCEPTION_REASON}">
  <div class="h3-unit-plan">
    <b>{UNIT_ID} · {DURATION_SECONDS}s · {UNIT_TITLE}</b>
    <div><b>事件：</b>{UNIT_EVENT}</div>
    <div><b>关系变化：</b>{RELATIONSHIP_TURN}</div>
    <div><b>主动作链：</b>{ACTION_CHAIN}</div>
    <div><b>有效台词：</b>{DIALOGUE_EFFECTIVE_CHARS} 字 · {SPEECH_TIMING_NOTE}</div>
    <div><b>首态：</b>{OPENING_STATE}</div>
    <div><b>尾态：</b>{EXIT_STATE}</div>
    <div><b>引用：</b>{UNIT_REFERENCES}</div>
    <div><b>声线：</b>{VOICE_BIBLE_REFERENCES}</div>
    <div><b>后期节点：</b>{POST_NODE_REFERENCES}</div>
  </div>

  {UNIT_UPLOAD_ORDER_CHECKLIST}

<div style="border-top:1px solid #333; margin:12px 0 8px; padding-top:8px;">
  <b style="color:#d1a461;">中文审稿版｜{UNIT_ID}｜{DURATION_SECONDS}秒</b>
  <span style="color:#666; font-size:10px;">[{TAG}]</span>
  <button style="margin-left:8px;padding:2px 8px;background:#27272a;border:1px solid #3f3f46;border-radius:4px;color:#a1a1aa;font-size:10px;cursor:pointer" onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.textContent)">复制提示词</button>
</div>
<div class="prompt-block">{H3_PROMPT_ZH_STORYBOARD}</div>

<div style="border-top:1px solid #333; margin:12px 0 8px; padding-top:8px;">
  <b style="color:#60a5fa;">English six-section prompt｜{UNIT_ID}｜{DURATION_SECONDS}s</b>
  <span style="color:#666; font-size:10px;">[{TAG}]</span>
  <button style="margin-left:8px;padding:2px 8px;background:#27272a;border:1px solid #3f3f46;border-radius:4px;color:#a1a1aa;font-size:10px;cursor:pointer" onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.textContent)">Copy prompt</button>
</div>
<div class="prompt-block h3-prompt-en">{H3_PROMPT_EN_SIX_SECTION}</div>
</article>
```

`{UNIT_KIND}` is normally `dialogue`, `narrative`, `action`, or `transition`. Dialogue and narrative units must use 10–15 seconds. A 5–9.99-second unit requires a nonempty `{DURATION_EXCEPTION_REASON}` allowed by `MINIMAX_H3_LONG_SCRIPT_UNITS.md`; leave that field empty for ordinary units. HTML-escape all data-attribute values as well as prompt text.

## Platform variables

Fill every platform placeholder consistently; never mix values across rows.

| Variable | Seedance 2.0 | MiniMax H3 |
| --- | --- | --- |
| `{PROMPT_TITLE}` | `Seedance 2.0 提示词` | `MiniMax H3 prompts` |
| `{PROMPT_LANGUAGE_SUMMARY}` | `with detailed Chinese cinematic prompts` | `with paired Chinese and English H3 prompts` |
| `{PROMPT_COLUMN_LABEL}` | `Seedance 2.0 提示词` | `MiniMax H3 中英双提示词` |
| `{PROMPT_BLOCK_LABEL}` | `提示词` | `中文审稿版` |
| `{VIDEO_PROMPT}` | The complete Chinese Seedance prompt | Replaced by `{H3_PROMPT_ZH_STORYBOARD}` |
| `{H3_PROMPT_ZH_STORYBOARD}` | N/A | One copyable Chinese prompt with title, `角色与场景：`, timed `镜头设计：`, `声音：`, and `音乐：` |
| `{H3_PROMPT_EN_SIX_SECTION}` | N/A | One copyable English prompt with `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, and `non_diegetic_music` |
| `{H3_RUNTIME_STAT}` | Empty | The single computed packed-runtime stat element with `data-h3-packed-runtime-seconds` |
| `{H3_PROJECT_PLANNING_BLOCKS}` | Empty | Unit blueprint, voice bible, post nodes, and runtime reconciliation |
| `{AUDIO_REFERENCE_MAP_BLOCK}` | Empty | Conditional approved filename-to-character audio lock table; empty when no audio reference was requested |

In the MiniMax H3 Chinese director storyboard, preserve exactly one `音乐：` section. A user instruction prohibiting background music takes priority: render `无配乐。` and English `non_diegetic_music: N/A`, with no score cues elsewhere. Otherwise follow the source or approved directing decision. Do not place audience-only score description elsewhere in the prompt block.

For Seedance, retain the original house layout. MiniMax H3 uses the card layout from `H3_PRODUCTION_LAYOUT.md`; keep each prompt pair inside one `h3-unit` article with its expanded upload checklist before both copy controls. The older prompt-cell example above defines metadata and prompt ordering, not a mandatory H3 table layout.

### MiniMax H3 HTML escaping

HTML-escape both prompt blocks before inserting them into `{H3_PROMPT_ZH_STORYBOARD}` and `{H3_PROMPT_EN_SIX_SECTION}` in this order:

1. `&` → `&amp;`
2. `<` → `&lt;`
3. `>` → `&gt;`

Do not otherwise rewrite the Chinese director storyboard or replace its line breaks. The Copy button uses `textContent`, so it preserves the exact user-facing prompt.

## CSS + JS

For H3, follow the responsive dark blue-gray cards, muted gold accents, wide readable content and local copy/print behavior in `H3_PRODUCTION_LAYOUT.md`. Preserve working prompt copy controls and text shotlist navigation; layout improvements must not change prompt text or upload order. For Seedance, retain house CSS/JS and director palette logic (`pal-black` / `pal-blue` / `pal-red`, default `pal-red`).

**Note on plan codes:** the skill now uses English plan codes (`WS`, `MS`, `CU`, `ECU`, `MACRO`, `PAN`, `OS`, `VO`, `VO+MS`, `DISSOLVE`) for both the visible badge label and the `data-plan` attribute. The plan filter dropdown's `<option value>` should match. If reusing CSS from older Cyrillic-coded HTMLs, swap the badge classes (`p-op` → `p-ws`, `p-sp` → `p-ms`, `p-kp` → `p-cu`, `p-dkp` → `p-ecu`, `p-vyk` → `p-os`) — the colors stay the same; only class names change.

## Filter dropdown

```html
<select id="planFilter">
  <option value="">All plans</option>
  <option value="WS">Wide shot</option>
  <option value="MS">Medium shot</option>
  <option value="CU">Close-up</option>
  <option value="ECU">Extreme close-up</option>
  <option value="MACRO">Macro</option>
  <option value="PAN">Pan</option>
  <option value="OS">Off-screen sound</option>
  <option value="VO">Voice-over</option>
  <option value="VO+MS">VO · medium shot</option>
  <option value="DISSOLVE">Dissolve</option>
</select>
```
