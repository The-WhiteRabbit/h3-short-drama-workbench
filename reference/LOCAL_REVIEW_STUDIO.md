# Local Review Studio

## Purpose

Extend Tudou Shotlist Builder with a local asset review layer.

## Three manual gates

1. Episode screenplay approval.
2. Storyboard and shot design approval.
3. Generated media candidate approval.

Generation completion does not equal approval.

## Asset rules

- Every generated attempt keeps its own version.
- Current production assets are selected explicitly.
- Replacing a file creates a new content fingerprint.
- Approval is invalidated when approved content changes.

## Recommended project structure

```
project/
  asset_manifest.json
  episodes/
    EP001/
      shots/
        EP001-SH001/
          shot.json
          prompts/
          images/
          videos/
  reviews/
```

## Viewer

Use a fixed local HTML application reading project state from a local service. Do not regenerate HTML after every asset change.

The viewer should support:

- asset browsing
- prompt editing
- candidate selection
- review history
- stale approval detection
- export of approved timeline only
