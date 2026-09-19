# MiniMax H3 Chinese + English Dual-Prompt Contract

Use this contract for every `H3_UNIT` produced by the MiniMax H3 branch. Each unit has two separately labeled and independently copyable prompts:

1. a Chinese director storyboard for review and Chinese free-form H3 callers;
2. an English six-section full-reference prompt for explicit reference binding.

Neither block is a loose translation or optional appendix. They are two serializations of one approved unit truth.

## 1. Author one unit truth, serialize it twice

Finish the unit's `CLIP_TRUTH_LEDGER`, `OPENING_STATE`, `SHOT_SCORE`, dialogue timing, sound plan, and exit state before writing either prompt. Then compile both blocks from that shared record.

The two prompts must agree on:

- unit ID, target duration, aspect ratio, scene, time, weather, and lighting;
- active characters, identity, wardrobe, left/right/depth positions, eyelines, and prop states;
- shot count, shot order, cut times, lenses, framing, camera movement, action onset/change/result, and final edit handle;
- speaker identity, audible-event order, voice baseline, line delivery, original-language dialogue, and dialogue timing;
- ambience, synchronized physical sounds, diegetic playback, and audience-only score;
- reference roles, the approved `AUDIO_REFERENCE_MAP` when active, post-node/clean-plate decisions, relationship turn, and exit state.

If an edit changes any of these facts, update both blocks before delivery. The English block does not add shots, gestures, props, dialogue, sound, or style that the Chinese block does not support; the Chinese block does not omit an action or state merely because it appears in `retention_analysis`.

## 2. Chinese block

Keep the existing five-part Chinese director-storyboard format exactly:

```text
中文审稿版｜H3-XXX｜N秒

角色与场景：
...

镜头设计：
【镜头1｜0.0—2.0秒】
...

声音：
...

音乐：
...
```

The Chinese block never contains `<Subject N>`, `<Picture N>`, `<Video N>`, `(Sx)`, `<d>`, English six-section field names, or an English mirror. Put each spoken line alone after its delivery colon.

When the user has explicitly approved an `AUDIO_REFERENCE_MAP`, render its filename-to-upload-slot rows as an operator checklist outside both copyable prompts. Inside the Chinese block, add one filename-free compact `<Audio N>` binding line per active audio under `角色与场景：`, including target character/source, `Audio mode`, `Retention`, scope, and exclusions; cite the same token again at its owning vocal event. `<Audio N>` is the only H3 reference label allowed in the Chinese block. When no audio map is active, omit all audio-routing syntax.

## 3. English six-section block

Write these fields exactly once and in this order:

```text
subject_definitions:
...

summary:
...

retention_analysis:
...

detailed_description:
...

overall_soundscape:
...

non_diegetic_music:
...
```

Write explanatory prose in English. Preserve dialogue, lyrics, and deliberately model-rendered visible text in the original language.

### Reference labels

- Define only the real reference units needed by the current H3 unit. Do not pad labels. Ref2VA accepts at most nine image inputs, three video inputs, and three audio inputs; enforce the duration and modality conditions in `MINIMAX_H3_PLATFORM_LIMITS.md`.
- Use `<Subject N>` for reusable visible identities, environments, props, or style-only content.
- Use standalone `<Picture N>` only for a concrete first frame, last frame, keyframe, or shot-planning anchor.
- Use `<Video N>` only for a source-video edit, continuation, or temporal-structure relationship.
- Use `<Audio N>` only for an actual audio copy/reference role.
- Every character-voice `<Audio N>` definition binds the operator checklist's actual upload slot to the same target character and `(Sx)` source recorded in `AUDIO_REFERENCE_MAP`, without naming the source file in prompt prose.
- Keep every label's meaning stable across all six sections.
- Style-only references use `attribute_transfer` or `weak_reference` as appropriate and may control photography and grading only.

### Summary and retention

- Begin `summary` with the truthful task-type prefix, such as `[reference generation]`, `[keyframe completion + reference generation]`, or another combination allowed by `MINIMAX_H3_FULL_REFERENCE_EN.md`.
- Give every defined label exactly one compatible `retention_analysis` entry.
- Use only the canonical relationship markers from `MINIMAX_H3_FULL_REFERENCE_EN.md`.
- Retention prose identifies the actual asset role and concrete retained traits; generic “keep the reference” wording fails.

### Detailed description and timing

- `[Shot 1]` is the opening shot and has no timestamp.
- Every later cut begins `[Shot N] At MM:SS.mmm, ...` using the same cut time as the corresponding Chinese shot boundary.
- The shot count and order must match the Chinese block. The final described state must reach the declared unit duration even though the six-section syntax records cut times rather than end ranges.
- State composition, lens, camera height/angle, screen geography, focus, action progression, performance, synchronized sound, and landing state in playback order.
- Preserve the Chinese block's anti-subtitle intent as visual direction: dialogue is audible speech, while no subtitle, translation, dialogue text, caption, title, speech bubble, or unintended readable screen text appears unless a model-rendered text event is explicitly approved.

### Speakers and dialogue

- Assign `(S1)`, `(S2)`, and later IDs by first audible-event order inside the current unit; reuse them consistently.
- The immediately preceding vocal clause must bind every `<d>` event to the real speaking character or explicit off-screen source.
- Use `<d>[Chinese] exact approved line</d>` for Chinese dialogue. Keep the approved dialogue text and punctuation identical to the Chinese block; the language tag and XML wrapper are not spoken.
- Put voice baseline, emotion, pace, pause, and delivery before `<d>`. Put a long post-line reaction in the next silent shot sentence rather than after the tag.
- Never assign `(Sx)` to an environment, style reference, or non-vocal prop.

### Sound and music

- `overall_soundscape` summarizes only current-scene ambience and physical sounds. Dialogue remains in `detailed_description`.
- `non_diegetic_music` must match the Chinese `音乐：` decision. Translate `无配乐。` as `N/A`; otherwise describe the same instrumentation/texture, pulse, entry, and exit in English.
- Diegetic music remains in `detailed_description`, not in `non_diegetic_music`.

## 4. Pair parity audit

Before delivery, compare the two blocks mechanically and semantically:

1. same unit ID and duration metadata;
2. same shot count and cut boundaries;
3. same characters, positions, wardrobe, props, and state transitions;
4. same dialogue sequence and exact original-language payloads;
5. same speaker-source mapping and voice intent;
6. when audio reference is active, the operator checklist and both prompts agree on `<Audio N>` upload slots, locked characters, reuse/reference mode, retention markers, scopes, exclusions, and owning vocal events; filenames appear only in the checklist;
7. same sound events and score decision;
8. same opening state, relationship turn, action chain, and exit state;
9. no subtitle/visible-text contradiction;
10. one Chinese copy control and one English copy control inside the same `h3-unit` article.

Any mismatch blocks delivery. Repair the shared unit truth or both serializations; never declare one block authoritative as an excuse for leaving the other stale.
