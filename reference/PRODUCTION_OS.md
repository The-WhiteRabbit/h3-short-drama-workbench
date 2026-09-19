# Tudou Production OS

## Goal

Manage drama production assets without regenerating HTML.

## Principles

- JSON is the production source of truth.
- HTML is a live viewer.
- Assets use stable IDs and versions.
- Rejected generations remain history.
- Approved assets are referenced by manifest.

## Shot lifecycle

```
draft
 -> review
 -> approved
 -> generated
 -> reviewing
 -> final
```

## Replace workflow

Replace a video, image or prompt file in the asset folder.
Run scanner.
Refresh studio dashboard.

No HTML rebuild required.
