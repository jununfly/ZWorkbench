"""The fixed semantic coverage matrix and how coverage may be counted.

The matrix is an acceptance specification transcribed from the PRD. It is
deliberately independent of the manifest: if the denominator came from what is
already declared, an unimplemented unit would vanish from the report instead of
showing up as a gap, and coverage would approach 100% by doing nothing.
"""

import pathlib
import unittest

from zworkbench.ui_matrix import (
    MATRIX,
    REQUIRED_VIEWPORTS,
    REQUIRED_MODES,
    CoverageError,
    coverage_report,
    required_units,
    required_scenarios,
)


class MatrixSpecificationTests(unittest.TestCase):
    """1-8-4 — the specification exists on its own terms."""

    def test_all_three_prd_views_are_specified(self):
        self.assertEqual(set(MATRIX), {"home", "task-detail", "record-view"})

    def test_every_view_names_units_and_scenarios(self):
        for view in MATRIX:
            self.assertTrue(required_units(view))
            self.assertTrue(required_scenarios(view))

    def test_the_prd_state_vocabulary_is_present(self):
        detail = set(required_scenarios("task-detail"))
        self.assertLessEqual(
            {"denied", "running", "recovering", "completed", "failed",
             "safe-stopped", "unknown"},
            detail,
        )

    def test_both_viewports_and_both_modes_are_required(self):
        self.assertEqual(set(REQUIRED_VIEWPORTS), {"compact", "wide"})
        self.assertEqual(set(REQUIRED_MODES), {"normal", "review"})

    def test_the_specification_does_not_depend_on_the_manifest(self):
        """The matrix must be a constant, not a projection of the manifest.

        Asserting that some unit is currently undeclared would only hold until
        the gap is filled. What must hold permanently is that the specification
        is fixed: an empty manifest leaves the required set unchanged.
        """
        import zworkbench.ui_matrix as matrix

        source = pathlib.Path(matrix.__file__).read_text(encoding="utf-8")
        self.assertNotIn("home_manifest", source)
        self.assertNotIn("build_manifest", source)

        before = required_units("home")
        self.assertEqual(coverage_report("home", declared_refs=())["required"], len(before))
        self.assertEqual(required_units("home"), before)
        self.assertEqual(
            len(before), len(coverage_report("home", declared_refs=("x",))["gaps"])
        )


class DenominatorTests(unittest.TestCase):
    """1-8-4 — a missing declaration must widen the gap, not shrink the base."""

    def test_the_denominator_comes_from_the_specification(self):
        report = coverage_report("home", declared_refs=())
        self.assertEqual(report["required"], len(required_units("home")))

    def test_declaring_nothing_yields_zero_coverage_not_full_coverage(self):
        report = coverage_report("home", declared_refs=())
        self.assertEqual(report["covered"], 0)
        self.assertEqual(report["ratio"], 0.0)

    def test_an_undeclared_unit_is_reported_as_a_gap(self):
        report = coverage_report("home", declared_refs=())
        self.assertEqual(set(report["gaps"]), set(required_units("home")))

    def test_extra_declarations_never_inflate_coverage(self):
        report = coverage_report(
            "home", declared_refs=tuple("home.extra-%d" % i for i in range(50))
        )
        self.assertEqual(report["covered"], 0)
        self.assertLessEqual(report["ratio"], 1.0)

    def test_an_unknown_unit_cannot_be_marked_not_applicable(self):
        with self.assertRaises(CoverageError):
            coverage_report("home", declared_refs=(), not_applicable={"home.ghost": "无此单元"})

    def test_not_applicable_requires_a_stated_reason(self):
        unit = required_units("home")[0]
        with self.assertRaises(CoverageError):
            coverage_report("home", declared_refs=(), not_applicable={unit: ""})

    def test_a_not_applicable_unit_leaves_the_denominator_intact(self):
        unit = required_units("home")[0]
        report = coverage_report(
            "home", declared_refs=(), not_applicable={unit: "该视图不展示此单元"}
        )
        self.assertEqual(report["required"], len(required_units("home")))
        self.assertEqual(report["not_applicable"], 1)
        self.assertNotIn(unit, report["gaps"])

    def test_a_not_applicable_unit_is_not_counted_as_covered(self):
        unit = required_units("home")[0]
        report = coverage_report(
            "home", declared_refs=(), not_applicable={unit: "该视图不展示此单元"}
        )
        self.assertEqual(report["covered"], 0)

    def test_full_coverage_requires_every_unit(self):
        report = coverage_report("home", declared_refs=required_units("home"))
        self.assertEqual(report["ratio"], 1.0)
        self.assertEqual(report["gaps"], ())

    def test_an_unknown_view_is_refused(self):
        with self.assertRaises(CoverageError):
            coverage_report("no-such-view", declared_refs=())


class HonestyTests(unittest.TestCase):
    """The report must state what it did not verify."""

    def test_the_report_carries_the_unverified_interaction_surfaces(self):
        report = coverage_report("home", declared_refs=required_units("home"))
        self.assertTrue(report["unverified"])
        for surface in report["unverified"]:
            self.assertEqual(surface["status"], "unknown")

    def test_full_structural_coverage_is_not_reported_as_acceptance(self):
        report = coverage_report("home", declared_refs=required_units("home"))
        self.assertEqual(report["ratio"], 1.0)
        self.assertFalse(report["accepted"])
        self.assertIn("unknown", report["conclusion"])

    def test_the_report_states_which_evidence_class_it_is(self):
        report = coverage_report("home", declared_refs=())
        self.assertEqual(report["evidence"], "structural-only")


if __name__ == "__main__":
    unittest.main()
