# Skill Integration

Tudou Shotlist Builder outputs should connect to Studio through these files:

- episode_manifest.json
- shot.json
- generation_record.json
- h3_job_request.json

Production flow:

1. Generate screenplay package.
2. Create episode manifest.
3. Wait for script approval.
4. Create shot definitions.
5. Wait for storyboard approval.
6. Create H3 jobs.
7. Register generated candidates.
8. Wait for clip approval.
9. Export selected timeline.

The Studio layer owns versioning and review state. The skill layer owns directing decisions and prompt creation.
