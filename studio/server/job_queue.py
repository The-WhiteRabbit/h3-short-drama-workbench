import json
from pathlib import Path
from datetime import datetime

QUEUE_FILE='jobs.json'

def load_jobs(root):
    p=Path(root)/QUEUE_FILE
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding='utf-8'))

def add_job(root, job):
    jobs=load_jobs(root)
    job['created_at']=datetime.utcnow().isoformat()
    jobs.append(job)
    (Path(root)/QUEUE_FILE).write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf-8')
    return job
