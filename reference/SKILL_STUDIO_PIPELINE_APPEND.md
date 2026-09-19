# Studio Pipeline Integration Appendix

This appendix extends `tudou-shotlist-builder-beta` with the local Tudou Studio production runtime.

## Output contract

Every new production project should create and maintain:

- `episode_manifest.json`
- `shot.json`
- `generation_record.json`
- `h3_job_request.json`

## Production gates

```
script
  -> human script review
  -> storyboard
  -> human storyboard review
  -> H3 generation job
  -> candidate clips
  -> human clip selection
  -> timeline export
```

## Asset rules

- Generated files are candidates until reviewed.
- Replacing an asset creates a new version.
- Approved status is bound to a file hash and asset version.
- Timeline export only uses selected approved versions.

## Runtime handoff

The skill layer controls:

- screenplay interpretation
- shot design
- prompt generation
- directing decisions

Studio runtime controls:

- asset indexing
- version tracking
- review state
- generation queue
- candidate management
- export timeline

## H3 integration

A H3 generation request should contain:

- shot id
- prompt references
- input asset IDs
- workflow information
- generation metadata

The runtime records results separately from prompts so historical generations remain traceable.
