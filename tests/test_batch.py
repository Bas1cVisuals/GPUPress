import tempfile
import unittest
from pathlib import Path

from app.core.batch import (
    BatchJobSnapshot,
    SUPPORTED_MEDIA_EXTENSIONS,
    discover_media_files,
    relative_output_directory,
    unique_output_path,
)
from app.core.encoding_plan import Codec, ResolutionMode, UserEncodingOptions


class BatchDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_supported_extensions_are_centralized_and_unsupported_ignored(self):
        expected = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".ts", ".mts", ".m2ts"}
        self.assertEqual(set(SUPPORTED_MEDIA_EXTENSIONS), expected)
        (self.root / "clip.MP4").touch()
        (self.root / "document.txt").touch()
        self.assertEqual(
            [path.name for path in discover_media_files(self.root)],
            ["clip.MP4"],
        )

    def test_recursive_discovery_is_deterministic_and_non_recursive_by_default(self):
        (self.root / "z.mp4").touch()
        (self.root / "B").mkdir()
        (self.root / "a").mkdir()
        (self.root / "B" / "inside.mkv").touch()
        (self.root / "a" / "inside.mov").touch()
        self.assertEqual(
            [path.name for path in discover_media_files(self.root)],
            ["z.mp4"],
        )
        recursive = discover_media_files(self.root, recursive=True)
        self.assertEqual(
            [path.relative_to(self.root).as_posix() for path in recursive],
            ["a/inside.mov", "B/inside.mkv", "z.mp4"],
        )

    def test_excludes_output_directories_and_partial_outputs(self):
        output = self.root / "Compressed"
        output.mkdir()
        (output / "generated.mp4").touch()
        (self.root / ".gpupress-job.partial.mp4").touch()
        (self.root / "take_compressed.mp4").touch()
        (self.root / "source.mp4").touch()
        files = discover_media_files(
            self.root,
            recursive=True,
            excluded_directories=(output,),
        )
        self.assertEqual([path.name for path in files], ["source.mp4"])

    def test_unique_output_paths_disambiguate_collisions(self):
        output = self.root / "out"
        output.mkdir()
        reserved = set()
        first = unique_output_path(
            output, self.root / "a" / "same.mp4",
            container="mp4", reserved_paths=reserved,
        )
        second = unique_output_path(
            output, self.root / "b" / "same.mov",
            container="mp4", reserved_paths=reserved,
        )
        self.assertEqual(first.name, "same_compressed.mp4")
        self.assertEqual(second.name, "same_compressed_1.mp4")

    def test_folder_outputs_retain_relative_directories(self):
        source = self.root / "input" / "nested" / "clip.mkv"
        source.parent.mkdir(parents=True)
        source.touch()
        self.assertEqual(
            relative_output_directory(self.root / "input", source),
            Path("nested"),
        )

    def test_job_snapshot_keeps_per_file_options_and_path_immutable(self):
        options = UserEncodingOptions(
            codec=Codec.HEVC,
            resolution_mode=ResolutionMode.P1080,
        )
        snapshot = BatchJobSnapshot(
            input_path=self.root / "input.mp4",
            output_path=self.root / "output.mp4",
            options=options,
            preset_id="high_quality_delivery",
        )
        self.assertEqual(snapshot.options.codec, Codec.HEVC)
        self.assertEqual(snapshot.options.resolution_mode, ResolutionMode.P1080)
        self.assertEqual(snapshot.preset_id, "high_quality_delivery")
        with self.assertRaises(AttributeError):
            snapshot.output_path = self.root / "changed.mp4"


if __name__ == "__main__":
    unittest.main()
