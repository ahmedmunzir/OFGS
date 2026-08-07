import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.dataset_parser import (
    FieldMinMaxDataset,
    PatchYPlusDataset,
    ResidualDataset,
    ScalarTimeSeriesDataset,
    VectorTimeSeriesDataset,
    parse_datasets,
)
from core.generator import AtomicPublicationError, write_monitor


class DatasetPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def output(self, owner, filename, contents):
        path = self.root / filename
        path.write_text(contents)
        return owner, {"files": [path], "type": filename}

    def test_physical_quantities_become_logical_datasets(self):
        outputs = dict(
            [
                self.output(
                    "residuals",
                    "solverInfo.dat",
                    "# Time p_solver p_initial p_final p_iters p_converged\n"
                    "0 GAMG 1e-2 1e-5 3 1\n"
                    "1 GAMG 2e-3 2e-6 2 1\n",
                ),
                self.output(
                    "surface",
                    "surfaceFieldValue.dat",
                    "# Time T U\n"
                    "0 300 (1 2 3)\n"
                    "1 301 (2 3 4)\n",
                ),
                self.output(
                    "limits",
                    "fieldMinMax.dat",
                    "# Time field min location(proc) max location(proc)\n"
                    "0 p 1 (0 0 0) 4 (1 1 1)\n"
                    "1 p 2 (0 0 0) 5 (1 1 1)\n",
                ),
                self.output(
                    "wallQuality",
                    "patchYPlus.dat",
                    "# Time patch min max average\n"
                    "0 inlet 1 10 5\n"
                    "0 outlet 2 20 8\n"
                    "1 inlet 2 11 6\n"
                    "1 outlet 3 21 9\n",
                ),
            ]
        )

        datasets = parse_datasets(outputs)

        self.assertEqual(
            [type(dataset) for dataset in datasets],
            [
                ResidualDataset,
                FieldMinMaxDataset,
                ScalarTimeSeriesDataset,
                VectorTimeSeriesDataset,
                PatchYPlusDataset,
                PatchYPlusDataset,
            ],
        )
        self.assertEqual(datasets[0].series["Initial"], (0.01, 0.002))
        self.assertEqual(set(datasets[3].series), {"x", "y", "z"})
        self.assertEqual(set(datasets[4].series), {"Min", "Max", "Average"})

    def test_flat_vector_columns_are_one_dataset(self):
        outputs = dict(
            [
                self.output(
                    "velocity",
                    "surfaceFieldValue.dat",
                    "# Time Ux Uy Uz\n0 1 2 3\n1 4 5 6\n",
                )
            ]
        )

        datasets = parse_datasets(outputs)

        self.assertEqual(len(datasets), 1)
        self.assertIsInstance(datasets[0], VectorTimeSeriesDataset)
        self.assertEqual(datasets[0].series["z"], (3.0, 6.0))

    def test_generator_uses_dataset_values_not_source_columns(self):
        outputs = dict(
            [
                self.output(
                    "surface",
                    "surfaceFieldValue.dat",
                    "# Time pressure velocity\n"
                    "0 4 (1 2 3)\n"
                    "1 5 (2 3 4)\n",
                )
            ]
        )
        write_monitor(self.root, parse_datasets(outputs))

        script = (self.root / "monitor.gp").read_text()

        self.assertEqual(script.count("\nplot "), 2)
        self.assertNotIn("surfaceFieldValue.dat", script)
        self.assertNotIn("using 1:", script)
        self.assertIn("$data_0_0 << EOD", script)
        self.assertIn("set title '[01] surface - pressure'", script)
        self.assertIn("set title '[02] surface - velocity'", script)

    def test_only_discovery_latest_files_are_parsed(self):
        old_directory = self.root / "postProcessing" / "outlet" / "0.5"
        latest_directory = self.root / "postProcessing" / "outlet" / "1.5"
        old_directory.mkdir(parents=True)
        latest_directory.mkdir(parents=True)
        old_file = old_directory / "surfaceFieldValue.dat"
        latest_file = latest_directory / "surfaceFieldValue.dat"
        old_file.write_text("# Time value\n0 10\n")
        latest_file.write_text("# Time value\n0 20\n")
        outputs = {
            "outlet": {
                "latest": latest_directory,
                "files": [old_file, latest_file, latest_file],
                "type": "surfaceFieldValue.dat",
            }
        }

        datasets = parse_datasets(outputs)

        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0].series["value"], (20.0,))

    def test_generator_orders_by_type_then_title(self):
        datasets = [
            PatchYPlusDataset("wall", (0.0,), {"Average": (2.0,)}),
            VectorTimeSeriesDataset("beta", (0.0,), {"x": (1.0,)}),
            ScalarTimeSeriesDataset("zeta", (0.0,), {"value": (1.0,)}),
            ResidualDataset("z residual", (0.0,), {"Initial": (0.1,)}),
            FieldMinMaxDataset("limits", (0.0,), {"Min": (0.0,)}),
            ScalarTimeSeriesDataset("Alpha", (0.0,), {"value": (1.0,)}),
        ]

        write_monitor(self.root, datasets)
        titles = [
            line
            for line in (self.root / "monitor.gp").read_text().splitlines()
            if line.startswith("set title")
        ]

        self.assertEqual(
            titles,
            [
                "set title '[01] z residual'",
                "set title '[02] limits'",
                "set title '[03] Alpha'",
                "set title '[04] zeta'",
                "set title '[05] beta'",
                "set title '[06] wall'",
            ],
        )

    def test_duplicate_min_max_quantities_are_merged_before_generation(self):
        first_directory = self.root / "postProcessing" / "fieldExtrema" / "1.5"
        second_directory = self.root / "postProcessing" / "otherExtrema" / "1.5"
        first_directory.mkdir(parents=True)
        second_directory.mkdir(parents=True)
        first_file = first_directory / "fieldMinMax.dat"
        second_file = second_directory / "fieldMinMax.dat"
        first_file.write_text(
            "# Time field min max\n"
            "0 T.gas 290 310\n"
            "1 T.liquid 280 300\n"
        )
        second_file.write_text(
            "# Time field min max\n"
            "1 T.gas 291 311\n"
            "2 T.liquid 282 302\n"
        )
        outputs = {
            "fieldExtrema": {
                "latest": first_directory,
                "files": [first_file],
                "type": "fieldMinMax.dat",
            },
            "otherExtrema": {
                "latest": second_directory,
                "files": [second_file],
                "type": "fieldMinMax.dat",
            },
        }

        datasets = parse_datasets(outputs)

        self.assertEqual(
            [dataset.title for dataset in datasets],
            ["T.gas (Min/Max)", "T.liquid (Min/Max)"],
        )
        self.assertEqual(len({dataset.identity for dataset in datasets}), 2)
        self.assertEqual(datasets[0].x_axis, (0.0, 1.0))
        self.assertEqual(datasets[1].x_axis, (1.0, 2.0))
        self.assertIn("fieldExtrema/1.5/fieldMinMax.dat", datasets[0].source)
        self.assertIn("otherExtrema/1.5/fieldMinMax.dat", datasets[0].source)

        write_monitor(self.root, datasets)
        script = (self.root / "monitor.gp").read_text()

        self.assertEqual(script.count("T.gas (Min/Max)"), 1)
        self.assertEqual(script.count("T.liquid (Min/Max)"), 1)

    def test_standalone_graphs_match_dashboard_graphs(self):
        datasets = [
            ScalarTimeSeriesDataset(
                "temperature",
                (0.0, 1.0),
                {"gas": (300.0, 301.0), "liquid": (290.0, 291.0)},
            ),
            ResidualDataset(
                "pressure residual",
                (0.0, 1.0),
                {"Initial": (0.1, 0.01), "Final": (0.01, 0.001)},
            ),
        ]

        write_monitor(self.root, datasets)

        dashboard = (self.root / "monitor.gp").read_text()
        residual_script = (self.root / "graphs" / "01.gp").read_text()
        scalar_script = (self.root / "graphs" / "02.gp").read_text()
        self.assertEqual(
            (self.root / "graphs" / "index.txt").read_text(),
            "01 pressure residual\n02 temperature\n",
        )
        for expected_line in (
            "set title '[01] pressure residual'",
            "set xlabel 'Time'",
            "set logscale y",
            "plot $data_0_0 with lines title 'Initial', "
            "$data_0_1 with lines title 'Final'",
            "pause mouse close",
        ):
            self.assertIn(expected_line, dashboard)
            self.assertIn(expected_line, residual_script)
        for expected_line in (
            "set title '[02] temperature'",
            "set xlabel 'Time'",
            "unset logscale y",
            "plot $data_1_0 with lines title 'gas', "
            "$data_1_1 with lines title 'liquid'",
            "pause mouse close",
        ):
            self.assertIn(expected_line, dashboard)
            self.assertIn(expected_line, scalar_script)
        self.assertNotIn("set multiplot", residual_script)
        self.assertNotIn("set multiplot", scalar_script)
        self.assertNotIn('set format x "%.3g"', residual_script)
        self.assertNotIn('set format y "%.3g"', scalar_script)
        self.assertIn('set format x "%.3g"', dashboard)
        self.assertIn('set format y "%.3g"', dashboard)
        self.assertIn(
            'if (!exists("LIVE_MODE")) pause mouse close',
            residual_script,
        )

    def test_stale_numbered_standalone_scripts_are_removed(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        (graphs_path / "01.gp").write_text("old")
        (graphs_path / "17.gp").write_text("stale")
        (graphs_path / "notes.gp").write_text("keep")

        write_monitor(
            self.root,
            [ScalarTimeSeriesDataset("temperature", (0.0,), {"value": (300.0,)})],
        )

        self.assertTrue((graphs_path / "01.gp").exists())
        self.assertFalse((graphs_path / "17.gp").exists())
        self.assertEqual((graphs_path / "notes.gp").read_text(), "keep")

    def test_staging_failure_preserves_previous_output(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        previous_files = {
            self.root / "monitor.gp": "previous monitor",
            graphs_path / "01.gp": "previous graph",
            graphs_path / "index.txt": "01 previous graph\n",
            graphs_path / "notes.gp": "not generated by OFGS",
        }
        for path, contents in previous_files.items():
            path.write_text(contents)

        with patch(
            "core.generator._standalone_lines",
            side_effect=RuntimeError("staging failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "staging failed"):
                write_monitor(
                    self.root,
                    [ScalarTimeSeriesDataset("replacement", (0.0,), {"value": (1.0,)})],
                )

        for path, contents in previous_files.items():
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])

    def test_commit_failure_restores_previous_output(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        previous_files = {
            self.root / "monitor.gp": "previous monitor",
            graphs_path / "01.gp": "previous graph one",
            graphs_path / "17.gp": "previous graph seventeen",
            graphs_path / "index.txt": "01 one\n17 seventeen\n",
        }
        for path, contents in previous_files.items():
            path.write_text(contents)

        from core import generator

        real_replace = generator.os.replace
        index_failure_raised = False
        rollback_observations = []

        def fail_first_index_publication(source, destination):
            nonlocal index_failure_raised
            if Path(destination) == graphs_path / "index.txt":
                if not index_failure_raised:
                    index_failure_raised = True
                    raise OSError("index publication failed")
                rollback_observations.append(
                    (
                        (graphs_path / "02.gp").is_file(),
                        (graphs_path / "01.gp").read_text(),
                    )
                )
            return real_replace(source, destination)

        with patch("core.generator.os.replace", side_effect=fail_first_index_publication):
            with self.assertRaisesRegex(OSError, "index publication failed"):
                write_monitor(
                    self.root,
                    [
                        ScalarTimeSeriesDataset(
                            "replacement one", (0.0,), {"value": (1.0,)}
                        ),
                        ScalarTimeSeriesDataset(
                            "replacement two", (0.0,), {"value": (2.0,)}
                        ),
                    ],
                )

        self.assertEqual(rollback_observations, [(True, "previous graph one")])
        for path, contents in previous_files.items():
            self.assertEqual(path.read_text(), contents)
        self.assertFalse((graphs_path / "02.gp").exists())
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])

    def test_symlinked_graphs_directory_is_rejected_before_publication(self):
        external_graphs = self.root / "external-graphs"
        external_graphs.mkdir()
        previous_files = {
            self.root / "monitor.gp": "previous monitor",
            external_graphs / "01.gp": "previous graph",
            external_graphs / "index.txt": "01 previous graph\n",
        }
        for path, contents in previous_files.items():
            path.write_text(contents)
        (self.root / "graphs").symlink_to(external_graphs, target_is_directory=True)

        with self.assertRaisesRegex(AtomicPublicationError, "graphs/ is a symlink"):
            write_monitor(
                self.root,
                [ScalarTimeSeriesDataset("replacement", (0.0,), {"value": (1.0,)})],
            )

        self.assertTrue((self.root / "graphs").is_symlink())
        for path, contents in previous_files.items():
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])

    def test_cross_filesystem_graphs_directory_is_rejected_before_publication(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        previous_files = {
            self.root / "monitor.gp": "previous monitor",
            graphs_path / "01.gp": "previous graph",
            graphs_path / "index.txt": "01 previous graph\n",
        }
        for path, contents in previous_files.items():
            path.write_text(contents)

        with patch("core.generator._filesystem_device", side_effect=(1, 2)):
            with self.assertRaisesRegex(
                AtomicPublicationError,
                "graphs/ is on a different filesystem",
            ):
                write_monitor(
                    self.root,
                    [ScalarTimeSeriesDataset("replacement", (0.0,), {"value": (1.0,)})],
                )

        for path, contents in previous_files.items():
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])

    def test_atomic_rename_probe_failure_preserves_previous_output(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        previous_files = {
            self.root / "monitor.gp": "previous monitor",
            graphs_path / "01.gp": "previous graph",
            graphs_path / "index.txt": "01 previous graph\n",
        }
        for path, contents in previous_files.items():
            path.write_text(contents)

        from core import generator

        real_replace = generator.os.replace

        def reject_probe(source, destination):
            if Path(source).name == ".ofgs-atomic-probe":
                raise OSError(errno.EXDEV, "cross-device link")
            return real_replace(source, destination)

        with patch("core.generator.os.replace", side_effect=reject_probe):
            with self.assertRaisesRegex(
                AtomicPublicationError,
                "cannot accept same-filesystem atomic replacement",
            ):
                write_monitor(
                    self.root,
                    [ScalarTimeSeriesDataset("replacement", (0.0,), {"value": (1.0,)})],
                )

        for path, contents in previous_files.items():
            self.assertEqual(path.read_text(), contents)
        self.assertEqual(list(graphs_path.glob(".ofgs-atomic-probe-*")), [])
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])

    def test_published_index_matches_numbered_graph_scripts(self):
        graphs_path = self.root / "graphs"
        graphs_path.mkdir()
        (graphs_path / "17.gp").write_text("stale")
        abandoned_staging = self.root / ".ofgs-generation-abandoned"
        abandoned_staging.mkdir()
        (abandoned_staging / "partial.gp").write_text("partial")
        datasets = [
            ScalarTimeSeriesDataset(
                f"quantity {number}",
                (0.0,),
                {"value": (float(number),)},
            )
            for number in range(1, 4)
        ]

        write_monitor(self.root, datasets)

        indexed_ids = {
            line.split(maxsplit=1)[0]
            for line in (graphs_path / "index.txt").read_text().splitlines()
        }
        published_ids = {
            path.stem
            for path in graphs_path.glob("*.gp")
            if path.stem.isdigit()
        }
        self.assertEqual(indexed_ids, published_ids)
        self.assertFalse((graphs_path / "17.gp").exists())
        self.assertFalse(abandoned_staging.exists())
        self.assertEqual(list(self.root.glob(".ofgs-generation-*")), [])


if __name__ == "__main__":
    unittest.main()
