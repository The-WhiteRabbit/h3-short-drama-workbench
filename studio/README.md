# Tudou Studio Local Review Architecture

This directory defines the asset-driven production workflow extension.

Goals:

- Keep script review, storyboard review, and generated clip review as separate human gates.
- Keep assets replaceable without regenerating reports.
- Use a fixed local HTML viewer that reads current project state.
- Track selected asset versions explicitly instead of relying on filenames.

Workflow:

1. Generate episode script -> human review.
2. Generate storyboard package -> human review.
3. Generate media candidates -> human selects approved version.
4. Export only approved assets.

Core rule:

A generated file is not an approved file. Approval belongs to the selected version recorded in shot.json.
