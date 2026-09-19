"""Offline behavioral tests: no real media-generation requests or approvals."""

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h3_storyboard as h
from PIL import Image


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        for name, color in [("panel.png", "red"), ("character.png", "blue")]:
            Image.new("RGB", (32, 18), color).save(self.base / name)
        (self.base / "voice.wav").write_bytes(b"fixture-audio")
        (self.base / "en.txt").write_text("subject_definitions: fixture only")
        (self.base / "zh.txt").write_text("离线测试，非创作成片")
        (self.base / "source.md").write_text("fixture source")
        self.unit = {
            "id": "H3-001",
            "duration": 4,
            "mode": "ref2va",
            "shots": [{"id": "S01", "start": 0, "end": 4}],
            "panels": [
                {
                    "id": "P01",
                    "shot_id": "S01",
                    "at": 0,
                    "image": "panel.png",
                    "visual": "</script><img src=x onerror=alert(1)>",
                }
            ],
            "prompt_en": "en.txt",
            "prompt_zh": "zh.txt",
            "references": [
                {
                    "kind": "image",
                    "path": "character.png",
                    "role": "identity",
                    "label": "<Subject 1>",
                },
                {
                    "kind": "audio",
                    "path": "voice.wav",
                    "role": "voice",
                    "label": "<Audio 1>",
                    "target": "actor",
                },
            ],
        }
        self.doc = {
            "schema_version": 1,
            "sources": ["source.md"],
            "title": "fixture",
            "video": {"width": 1344, "height": 768, "fps": 24},
            "units": [self.unit],
        }
        self.manifest = self.base / "storyboard.json"
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.doc))

    def args(self, **kwargs):
        return argparse.Namespace(manifest=self.manifest, unit="H3-001", **kwargs)

    def receipt(self):
        snapshot, problems = h.inspect_unit(self.doc, self.base, self.unit)
        self.assertFalse(problems)
        path = self.base / "approved.json"
        path.write_text(
            json.dumps(
                {"unit_id": "H3-001", "snapshot": snapshot, "decision": "approved"}
            )
        )
        return path

    def test_prompt_source_and_image_changes_invalidate_approval(self):
        for filename in ["en.txt", "source.md", "character.png", "panel.png"]:
            receipt = self.receipt()
            path = self.base / filename
            original = path.read_bytes()
            if path.suffix == ".png":
                Image.new("RGB", (32, 18), "green").save(path)
            else:
                path.write_text("changed")
            with self.assertRaises(ValueError):
                h.approved(self.args(approval=receipt), self.doc, self.base, self.unit)
            path.write_bytes(original)

    def test_missing_images_and_bad_mapping_cannot_be_approved(self):
        (self.base / "panel.png").unlink()
        self.unit["panels"][0]["shot_id"] = "UNKNOWN"
        _, issues = h.inspect_unit(self.doc, self.base, self.unit)
        self.assertGreaterEqual(len(issues), 2)

    def test_graph_preserves_references_and_never_uploads_preview_implicitly(self):
        graph, mapping = h.compile_graph(
            self.doc, self.base, self.unit, self.base / "input"
        )
        refs = next(
            n for n in graph.values() if n["class_type"] == "VLLMOmniVideoReferences"
        )
        self.assertEqual(list(refs["inputs"]), ["image_1", "audio_1"])
        self.assertEqual([r["path"] for r in mapping], ["character.png", "voice.wav"])
        gen = next(
            n["inputs"]
            for n in graph.values()
            if n["class_type"] == "VLLMOmniGenerateVideo"
        )
        self.assertEqual(gen["num_frames"], 96)
        self.assertEqual(gen["api_key"], "")
        self.assertNotIn("frame", gen)
        for row in mapping:
            self.assertTrue((self.base / "input" / row["comfy_file"]).exists())

    def test_reordering_and_fl2va_are_not_silent_fallbacks(self):
        self.unit["references"].reverse()
        self.unit["mode"] = "fl2va"
        _, issues = h.inspect_unit(self.doc, self.base, self.unit)
        self.assertTrue(any("静默重排" in i for i in issues))
        self.assertTrue(any("仅启用 Ref2VA" in i for i in issues))

    def test_partial_review_does_not_approve(self):
        snapshot, _ = h.inspect_unit(self.doc, self.base, self.unit)
        review = self.base / "review.json"
        review.write_text(
            json.dumps(
                {
                    "units": [
                        {
                            "unit_id": "H3-001",
                            "snapshot": snapshot,
                            "decision": "approved",
                            "checked_panels": [],
                            "notes": "",
                        }
                    ]
                }
            )
        )
        with self.assertRaises(ValueError):
            h.approve(
                self.args(
                    review=review,
                    confirmation="fixture only",
                    out=self.base / "new.json",
                )
            )

    def test_render_escapes_html_and_marks_missing_images(self):
        (self.base / "panel.png").unlink()
        out = self.base / "review.html"
        with contextlib.redirect_stdout(io.StringIO()):
            h.render(self.args(out=out))
        text = out.read_text()
        self.assertNotIn("</script><img src=x", text)
        self.assertIn("待生成分镜图", text)
        with self.assertRaises(FileExistsError):
            h.render(self.args(out=out))

    def test_submit_once_injects_key_only_in_memory(self):
        receipt = self.receipt()
        args = self.args(
            approval=receipt,
            job=self.base / "job.json",
            input_dir=self.base / "input",
            credential_workflow=None,
            authorization="test only",
            comfy_url=h.COMFY_URL,
        )
        with (
            patch.dict("os.environ", {"MINIMAX_API_KEY": "fixture-secret"}),
            patch.object(
                h,
                "request_json",
                return_value={"prompt_id": "test-id", "node_errors": {}},
            ) as call,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                h.submit(args)
            self.assertIn("fixture-secret", json.dumps(call.call_args.args[1]))
            self.assertNotIn("fixture-secret", args.job.read_text())
            with self.assertRaises(FileExistsError):
                h.submit(args)
            self.assertEqual(call.call_count, 1)

    def test_uncertain_submission_leaves_journal(self):
        args = self.args(
            approval=self.receipt(),
            job=self.base / "job.json",
            input_dir=self.base / "input",
            credential_workflow=None,
            authorization="test only",
            comfy_url=h.COMFY_URL,
        )
        with (
            patch.dict("os.environ", {"MINIMAX_API_KEY": "fixture-secret"}),
            patch.object(h, "request_json", side_effect=TimeoutError),
            self.assertRaises(ValueError),
        ):
            h.submit(args)
        self.assertEqual(h.read_json(args.job)["status"], "submission-uncertain")

    def test_status_never_prints_original_graph(self):
        path = self.base / "job.json"
        path.write_text(json.dumps({"prompt_id": "x", "comfy_url": h.COMFY_URL}))
        out = io.StringIO()
        with (
            patch.object(
                h,
                "request_json",
                return_value={
                    "x": {
                        "prompt": {"api_key": "fixture-secret"},
                        "status": {"status_str": "success"},
                        "outputs": {},
                    }
                },
            ),
            contextlib.redirect_stdout(out),
        ):
            h.status(argparse.Namespace(job=path))
        self.assertNotIn("fixture-secret", out.getvalue())


if __name__ == "__main__":
    unittest.main()
