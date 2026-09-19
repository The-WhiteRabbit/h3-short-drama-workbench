# H3 production HTML — default delivery layout

Use this layout for H3 shotlist and prompt deliveries. It captures the user's approved production-card format, not the characters, runtime, unit count, source script, filenames or music decisions of any particular film. Do not request a new format confirmation on each project. Current explicit user layout changes take precedence.

## Page hierarchy

1. Project title, calculated runtime, unit count, effective spoken-character count, and truthful production status (planning / prompts ready / media generated).
2. Compact navigation: units, upload instructions, boundary ledger, postproduction text; print/PDF and optional search. Search does not change authoritative runtime totals.
3. For each unit: current storyboard-review link/thumbnail and truthful image-review status (do not treat asset thumbnails or text planning as approved panels); heading with ID, local duration and project time interval; scene/relationship turn; expanded **本段上传顺序**; shot timing/ladder; independently copyable Chinese and English prompts.
4. Complete adjacent-unit boundary ledger and exact postproduction text/timing.

Use dark blue-gray backgrounds, muted gold headings, readable light body text, wide centered content, bordered cards and generous paragraph spacing. Keep the 16:9 preview frames, mobile wrapping and copy controls. Summaries/tables may be collapsible, but the upload checklist must not be hidden in closed details, hover content, JSON, a global gallery, or another page. Do not require the user to scroll to a global asset list to discover a unit's input files.

Default style tokens (adapt spacing responsively): background `#101923`, card `#16232e`, border `#425361`, text `#e5e9ed`, accent `#e6c493`, link `#9ed8db`; main width about 1320px, padding 28px desktop / 12px mobile. Embed CSS and JS locally. Avoid external fonts or scripts. Never copy project-specific prose as template defaults.

## One input map, one visible checklist

Compile the actual upload map before prompt serialization. Render the checklist and prompt reference definitions from that same map. At each independent unit, numbering restarts at 1 **within each modality**; image 1 and audio 1 are independent positions. Preserve input roles: identity + wardrobe, environment, style-only, keyframe, motion source, audio timbre reference or original-signal reuse.

Each row must visibly show:

- **图片 1 / 视频 1 / 音频 1**, in the exact upload order;
- exact filename, linked to the actual local/approved remote asset, with a named subject and concise purpose;
- for audio, the target character/source, duration, `audio reference` versus `audio reuse`, and whether a short derivative or full original is intended;
- for ambiguous visual bindings, the corresponding model label (e.g. reusable `<Subject 2>` versus first-frame `<Picture 2>`) and its role. Image upload order is not automatically identical to Subject numbering; honor the actual mapping.

Prefer small linked image thumbnails where useful; always retain the exact visible filename. Full source paths may be secondary details. For portable deliveries use `assets/` and `audio/` links with matching packaged files; for a single HTML use verified absolute file links or embedded previews plus access to the actual upload file. A thumbnail or data URI alone is not an uploadable filename. Never claim a missing local file is available, and never use dead illustrative filenames in a final deliverable.

Repeat shared references at every consuming unit, including the actual global style input and its position. List only active references, not every project asset. If no audio/video is used, omit that modality's list; do not invent bindings. For units with no visual inputs under a supported mode, show an explicit empty-state reason instead of a fake image. H3 Ref2VA in this skill still requires real visual reference input.

Outside prompts, explain once that the Chinese and English blocks are alternatives for the same clip, not text to concatenate. Copy buttons must copy only prompt text through `textContent`, with success feedback and a selection fallback. Keep filenames and upload instructions outside the model-facing prompt grammar. Never silently change approved audio mappings, reference exclusions or an approved calibration prompt when improving the HTML.

## Machine-readable HTML component

Place exactly one expanded checklist inside its `h3-unit` article, after the unit plan and before its first prompt block. The scene preview may be before the article. Replace sample values with actual unit data and HTML-escape text/attributes. Repeat rows in actual upload order, images first, then any videos, then any audio. Reuse the canonical `h3-unit` timing/state attributes from `HTML_TEMPLATE.md`.

```html
<section class="upload-order" data-upload-unit="{UNIT_ID}" aria-label="本段上传顺序">
  <h3>本段上传顺序</h3>
  <ol class="upload-list">
    <li data-upload-kind="image" data-slot="1"
        data-filename="{ACTUAL_IMAGE_FILENAME}" data-role="{NAMED_SUBJECT_AND_ROLE}"
        data-model-label="{ACTUAL_MODEL_LABEL}">
      <strong>图片 1</strong> ·
      <a href="{ACTUAL_IMAGE_HREF}">{ACTUAL_IMAGE_FILENAME}</a>
      <span>{NAMED_SUBJECT_AND_ROLE}</span>
      <!-- Optional linked thumbnail uses the same actual file, not a substitute asset. -->
    </li>
  </ol>
  <!-- Add a separate ordered list only when actual audio inputs are active. -->
  <ol class="upload-list">
    <li data-upload-kind="audio" data-slot="1"
        data-filename="{ACTUAL_AUDIO_FILENAME}" data-role="{VOICE_PURPOSE}"
        data-target="{LOCKED_CHARACTER}" data-audio-mode="audio reference"
        data-model-label="&lt;Audio 1&gt;">
      <strong>音频 1</strong> ·
      <a href="{ACTUAL_AUDIO_HREF}">{ACTUAL_AUDIO_FILENAME}</a>
      <span>{LOCKED_CHARACTER} · {VOICE_PURPOSE} · {ACTUAL_DURATION}s · {ORIGINAL_OR_DERIVATIVE}</span>
    </li>
  </ol>
</section>
```

When the supported mode truly has zero visual inputs, use `data-no-visual-inputs="{EXPLICIT_REASON}"` on the checklist and show the same reason visibly. This is not a bypass for missing assets. Videos follow the same row contract with `data-upload-kind="video"`. Do not number audio after the final image; it begins at audio 1.

Minimal scoped CSS:

```css
.upload-order{padding:18px;margin:18px 0;border:1px solid #425361;border-radius:10px;background:#1c2a36}
.upload-list{list-style:none;padding:0;margin:10px 0}
.upload-list li{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 0;border-top:1px solid #425361}
.upload-list strong{color:#e6c493}.upload-list a{color:#9ed8db;overflow-wrap:anywhere}
.upload-list span{color:#c5d0d8}.upload-list img{max-width:160px;max-height:90px;object-fit:contain}
@media print{.upload-order{break-inside:avoid;background:white;color:black}.upload-list a,.upload-list strong,.upload-list span{color:black}}
```

## Delivery checks

Run `python scripts/h3_upload_order_lint.py <html-file>` alongside existing prompt/runtime linters. It checks structural association, ordering, filename links, required roles and audio targets, simple hidden/collapsed markup, and local-file existence. It does **not** prove semantic reference correspondence, media quality, remote-link reachability, or CSS visibility. Also compare rows against the real input map, inspect in a browser, follow the asset links, and test copy buttons and mobile layout. No media generation is needed to test a template.

For tool maintenance run `python scripts/h3_upload_order_tests.py`. Existing projects without these semantic attributes remain historical deliverables; a skill-only update does not authorize mass rewriting them.
