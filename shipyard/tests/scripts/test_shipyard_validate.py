import copy
import json
import os
import tempfile
import unittest

from fixture_tree import REPO_ROOT, run_script
from shipyard_validate import extract_json, load_contract, validate

HIR = None  # humanInputRequested: null is the common case

FINDING = {
    "id": "code-001", "severity": "MAJOR", "category": "correctness", "location": "src/a.py:10-12",
    "finding": "Expiry is compared in local time.", "whyItMatters": "Links expire early in some zones.",
    "evidence": "src/a.py:11 uses datetime.now()", "requiredResolution": "Compare in UTC.",
    "confidence": "HIGH", "owner": "implementer", "reporters": ["code-reviewer"], "status": "OPEN",
}
COUNTS = {"BLOCKING": 0, "MAJOR": 1, "MINOR": 0, "NOTE": 0}
FACT = {"value": False, "evidence": "no such change"}

VALID = {
    "architect-result": {
        "mode": "CRITIQUE", "verdict": "SOUND", "findingsFile": ".ai/planning/architect.md", "counts": COUNTS,
        "findings": [FINDING], "abstractionsChallenged": 2, "abstractionsRejected": 1, "invariantsChanged": 0,
        "decisionRecord": None, "humanInputRequested": HIR,
    },
    "author-result": {
        "role": "implementer", "mode": "IMPLEMENT", "slice": "01", "round": 0, "acSatisfied": ["AC-1"],
        "acNotSatisfied": [], "filesChanged": ["src/a.py"], "commit": "abc1234", "fixed": [], "rebuttals": [],
        "architectureConcerns": [], "outOfScopeNoticed": [], "stubsRemaining": [], "build": "PASS",
        "humanInputRequested": HIR,
    },
    "discovery-result": {
        "mode": "SCAN", "artifactsWritten": [".ai/planning/discovery.md"], "couldNotInspect": [],
        "humanInputRequested": HIR,
        "facts": {"SPECIFIED": 1, "DERIVED": 4, "ASSUMED": 2, "UNRESOLVED": 0},
        "validationTiers": [{"name": "unit", "environment": "LOCAL"}],
    },
    "finding": FINDING,
    "goldfish-result": {
        "mode": "BRAINSTORM", "lens": "contrarian", "readiness": "NOT_APPLICABLE", "questions": [],
        "concepts": [{"title": "Do nothing", "summary": "Delete stale links nightly.", "why": "Smallest.",
                      "risks": "Users lose links.", "relativeSize": "S"}],
    },
    "planner-result": {
        "mode": "PLAN", "slices": 2, "orderingRationale": "Schema before behaviour.", "largestSlice": "01",
        "consumerMigrationOrder": [], "risks": [], "verdict": "PLANNED", "exceptionRequests": [],
        "humanInputRequested": HIR,
    },
    "rebuttal-response": {"findingId": "code-001", "response": "ACCEPT_REBUTTAL", "reason": "Cited ADR-001."},
    "reviewer-result": {
        "reviewer": "code-reviewer", "mode": "SLICE", "verdict": "CHANGES_REQUIRED",
        "findingsFile": ".ai/slices/01/findings/code-reviewer.md", "counts": COUNTS, "mostSerious": "code-001",
        "findings": [FINDING], "extras": {"anything": [1, 2]}, "abilityVersions": {"code-clarity": "1.0.0"},
        "humanInputRequested": HIR,
    },
    "discover-workflow-result": {"status": "NEEDS_HUMAN", "topConcepts": [], "gaps": [], "questions": [], "artifacts": [".ai/planning/concepts.md"], "reason": ""},
    "plan-workflow-result": {"status": "AWAITING_PLAN_APPROVAL", "slices": 2, "readiness": [], "findings": [], "humanInputRequests": [], "reason": ""},
    "slice-workflow-result": {
        "slice": "01", "status": "READY_FOR_HUMAN", "rounds": 1, "reason": "clean", "commit": "abc1234",
        "verify": {"build": "PASS"}, "testPlan": None, "reviewersRouted": [{"role": "code-review",
                                                                             "because": "productionCode"}],
        "reviewersNotRouted": [], "findings": [dict(FINDING, status="FIXED")], "openFindings": [],
        "humanInputRequests": [], "abilityVersions": {},
    },
    "state": {
        "schemaVersion": "1.0", "project": "demo", "status": "IMPLEMENTING", "featureBranch": "feature/x",
        "baseBranch": "main", "protectedBranches": ["main", "master"], "activeSlice": "01",
        "sliceBranch": "feature/x-slice-01", "brainstormBreadth": 1,
    },
    "test-plan-result": {
        "slice": "01", "testPlanFile": ".ai/slices/01/TEST_PLAN.md",
        "acCoverage": [{"ac": "AC-1", "tests": ["tests/test_expiry.py::test_expired"], "level": "unit"}],
        "acNotVerifiable": [], "failureCases": ["clock skew"], "benchmarks": [], "tiers": [],
        "humanInputRequested": HIR,
    },
    "verify-result": {
        "slice": "01", "commit": "abc1234", "testPlanStatus": "APPROVED", "scopeCheck": "IN_SCOPE", "drift": [], "build": "PASS",
        "staticAnalysis": "NOT_APPLICABLE", "unitTests": {"status": "PASS", "run": 12, "failures": 0},
        "integrationTests": "NOT_APPLICABLE", "tiers": [], "commandUsed": "pytest -q", "testsAdded": [],
        "acVerified": [{"ac": "AC-1", "test": "tests/test_expiry.py::test_expired"}], "acNotVerified": [],
        "invariantsChecked": [], "failureScenarios": [], "confidence": "HIGH", "confidenceReason": "all ACs tested",
        "routingFacts": {k: dict(FACT) for k in ("productionCode", "mechanicalOnly", "publicContract",
                                                 "concurrency", "consumerVisible", "security", "config")},
        "humanInputRequested": HIR,
    },
}

# One field per contract that has an enum, used to build an invalid sample.
ENUM_FIELD = {
    "architect-result": "verdict", "author-result": "build", "discovery-result": "mode", "finding": "severity",
    "goldfish-result": "readiness", "planner-result": "verdict", "rebuttal-response": "response",
    "reviewer-result": "verdict", "slice-workflow-result": "status", "discover-workflow-result": "status", "plan-workflow-result": "status", "state": "status",
    "test-plan-result": None, "verify-result": "scopeCheck",
}


def contract_stems():
    cdir = os.path.join(REPO_ROOT, "contracts")
    return sorted(f[: -len(".schema.json")] for f in os.listdir(cdir) if f.endswith(".schema.json"))


class EveryContractHasSamples(unittest.TestCase):
    def test_samples_cover_all_contracts(self):
        self.assertEqual(sorted(VALID), contract_stems(), "add a valid sample for each new contract")


class ValidSamples(unittest.TestCase):
    def test_each_valid_sample_passes(self):
        for stem, sample in VALID.items():
            with self.subTest(contract=stem):
                self.assertEqual(validate(sample, load_contract(stem)), [])


class InvalidSamples(unittest.TestCase):
    def test_missing_required_property(self):
        for stem, sample in VALID.items():
            schema = load_contract(stem)
            with self.subTest(contract=stem):
                bad = copy.deepcopy(sample)
                del bad[schema["required"][0]]
                errors = validate(bad, schema)
                self.assertTrue(any("missing required property" in e for e in errors), errors)

    def test_additional_property_rejected(self):
        for stem, sample in VALID.items():
            with self.subTest(contract=stem):
                schema = load_contract(stem)
                bad = dict(sample, surprise=1)
                errors = validate(bad, schema)
                if schema.get("additionalProperties") is True:
                    self.assertEqual(errors, [])  # open result objects (discover/plan) accept extra fields
                else:
                    self.assertIn('$: additional property "surprise" is not allowed', errors)

    def test_enum_violation(self):
        for stem, field in ENUM_FIELD.items():
            if not field:
                continue
            with self.subTest(contract=stem):
                bad = dict(VALID[stem], **{field: "NOT_A_VALUE"})
                errors = validate(bad, load_contract(stem))
                self.assertTrue(any(e.startswith("$.%s:" % field) and "is not one of" in e for e in errors), errors)

    def test_wrong_type(self):
        for stem, sample in VALID.items():
            with self.subTest(contract=stem):
                self.assertTrue(validate([sample], load_contract(stem)))


class Keywords(unittest.TestCase):
    def test_nested_path_and_min_length(self):
        bad = copy.deepcopy(VALID["reviewer-result"])
        bad["findings"][0]["evidence"] = ""
        self.assertEqual(validate(bad, load_contract("reviewer-result")),
                         ["$.findings[0].evidence: string shorter than minLength 1"])

    def test_minimum(self):
        bad = copy.deepcopy(VALID["reviewer-result"])
        bad["counts"]["MAJOR"] = -1
        self.assertEqual(validate(bad, load_contract("reviewer-result")),
                         ["$.counts.MAJOR: -1 is less than minimum 0"])

    def test_type_array_accepts_null_and_string(self):
        schema = load_contract("state")
        for value in (None, "07"):
            self.assertEqual(validate(dict(VALID["state"], activeSlice=value), schema), [])
        errors = validate(dict(VALID["state"], activeSlice=7), schema)
        self.assertEqual(errors, ["$.activeSlice: expected type string | null, got integer"])

    def test_boolean_is_not_integer(self):
        schema = load_contract("state")
        errors = validate(dict(VALID["state"], brainstormBreadth=True), schema)
        self.assertEqual(errors, ["$.brainstormBreadth: expected type integer, got boolean"])

    def test_integer_enum(self):
        errors = validate(dict(VALID["state"], brainstormBreadth=3), load_contract("state"))
        self.assertEqual(errors, ["$.brainstormBreadth: 3 is not one of [0, 1, 2]"])

    def test_additional_properties_schema(self):
        schema = load_contract("reviewer-result")
        bad = dict(VALID["reviewer-result"], abilityVersions={"x": 1})
        self.assertEqual(validate(bad, schema), ["$.abilityVersions.x: expected type string, got integer"])

    def test_additional_properties_true(self):
        schema = {"type": "object", "properties": {}, "additionalProperties": True}
        self.assertEqual(validate({"a": 1}, schema), [])

    def test_items(self):
        schema = {"type": "array", "items": {"type": "string"}}
        self.assertEqual(validate(["a", 2], schema), ["$[1]: expected type string, got integer"])

    def test_major_version_suffix(self):
        self.assertTrue(load_contract("state@1"))
        with self.assertRaises(Exception):
            load_contract("state@2")


class Extraction(unittest.TestCase):
    def test_pure_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_last_fenced_block_wins(self):
        text = 'Summary.\n\n```json\n{"a": 1}\n```\n\nMore.\n\n```json\n{"a": 2}\n```\n'
        self.assertEqual(extract_json(text), {"a": 2})

    def test_no_json(self):
        with self.assertRaises(ValueError):
            extract_json("Just prose, no block.")


class Cli(unittest.TestCase):
    def test_valid_markdown_from_stdin(self):
        msg = "Done.\n\n```json\n%s\n```\n" % json.dumps(VALID["rebuttal-response"])
        proc = run_script("shipyard_validate.py", "rebuttal-response", "-", stdin=msg)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_invalid_file_exit_1_with_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            with open(path, "w") as fh:
                json.dump(dict(VALID["state"], status="NOPE"), fh)
            proc = run_script("shipyard_validate.py", "state", path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("$.status", proc.stdout)

    def test_no_json_is_invalid(self):
        proc = run_script("shipyard_validate.py", "state", "-", stdin="no json here")
        self.assertEqual(proc.returncode, 1)

    def test_usage_errors_exit_2(self):
        self.assertEqual(run_script("shipyard_validate.py").returncode, 2)
        self.assertEqual(run_script("shipyard_validate.py", "no-such-contract", "-", stdin="{}").returncode, 2)
        self.assertEqual(run_script("shipyard_validate.py", "state", "/no/such/file.json").returncode, 2)

    def test_runs_from_any_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_script("shipyard_validate.py", "rebuttal-response", "-", cwd=tmp,
                              stdin=json.dumps(VALID["rebuttal-response"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class SampleProject(unittest.TestCase):
    """The illustrative sample project must follow the formats it illustrates."""

    AI = os.path.join(os.path.dirname(REPO_ROOT), "examples", "sample-project", ".ai")

    def test_state_json_is_valid(self):
        with open(os.path.join(self.AI, "state.json")) as fh:
            self.assertEqual(validate(json.load(fh), load_contract("state")), [])

    def test_test_plan_status_lines(self):
        for slice_id, status in (("01", "APPROVED"), ("02", "DRAFT")):
            with open(os.path.join(self.AI, "slices", slice_id, "TEST_PLAN.md"), encoding="utf-8") as fh:
                head = [line.rstrip("\n") for line in fh.readlines()[:10]]
            self.assertIn("Status: " + status, head)

    def test_slices_have_touch_sets_and_branch(self):
        for slice_id in ("01", "02"):
            with open(os.path.join(self.AI, "slices", slice_id, "SLICE.md"), encoding="utf-8") as fh:
                text = fh.read()
            for heading in ("## Expected touch set — code", "## Expected touch set — tests", "## Branch"):
                self.assertIn(heading, text)


if __name__ == "__main__":
    unittest.main()
