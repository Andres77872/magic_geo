"""Direct unit tests for :mod:`magic_geo.geo_layer_contracts`.

``evaluate_geo_layer_contracts`` is a pure function over a world mapping and a
list of validator checks, so every rule in the contract (artifact presence,
output kind, validator-domain coverage, dependency propagation, fatal-check
severity, and scope-specific omissions) is exercised here with hand-built
dicts.  End-to-end behaviour against a generated world lives in
``tests/test_geo_validation.py``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest import TestCase

from magic_geo.geo_layer_contracts import (
    GEO_LAYER_CONTRACTS,
    LAYER_CONTRACT_SCHEMA_VERSION,
    _output_matches_kind,
    evaluate_geo_layer_contracts,
)


LAYER_IDS = tuple(str(contract["id"]) for contract in GEO_LAYER_CONTRACTS)

# One valid sample value per declared output kind.
KIND_SAMPLES: dict[str, Any] = {
    "dict": {"present": True},
    "list": [],
    "nonempty_list": [{"present": True}],
    "nonempty_str": "spherical_excess",
}


def _all_domains() -> list[str]:
    """Every validator domain named by any layer contract, in declared order."""
    domains: list[str] = []
    for contract in GEO_LAYER_CONTRACTS:
        for domain in contract["validator_domains"]:
            if domain not in domains:
                domains.append(str(domain))
    return domains


def _passing_world(**overrides: Any) -> dict[str, Any]:
    """A world carrying a valid artifact for every required output."""
    world: dict[str, Any] = {}
    for contract in GEO_LAYER_CONTRACTS:
        for key, kind in contract["required_outputs"].items():
            world[str(key)] = deepcopy(KIND_SAMPLES[str(kind)])
    world.update(overrides)
    return world


def _passing_checks(*, skip: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """One ``passed`` check per validator domain (minus any skipped domain)."""
    return [
        {
            "domain": domain,
            "name": f"{domain}_evidence",
            "status": "passed",
            "severity": "error",
        }
        for domain in _all_domains()
        if domain not in skip
    ]


def _layers(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(layer["id"]): layer for layer in audit["layers"]}


class OutputKindTests(TestCase):
    """``_output_matches_kind`` is the primitive behind every artifact check."""

    def test_declared_kinds_accept_and_reject_the_right_values(self) -> None:
        cases: tuple[tuple[Any, str, bool], ...] = (
            ({"a": 1}, "dict", True),
            ({}, "dict", False),
            ([], "dict", False),
            (None, "dict", False),
            ([], "list", True),
            ([1], "list", True),
            ({}, "list", False),
            ("[]", "list", False),
            (None, "list", False),
            ([0], "nonempty_list", True),
            ([], "nonempty_list", False),
            ({"a": 1}, "nonempty_list", False),
            ("value", "nonempty_str", True),
            ("  ", "nonempty_str", False),
            ("", "nonempty_str", False),
            (b"value", "nonempty_str", False),
            (None, "nonempty_str", False),
        )
        for value, kind, expected in cases:
            with self.subTest(value=value, kind=kind):
                self.assertIs(_output_matches_kind(value, kind), expected)

    def test_every_contract_declares_a_known_output_kind(self) -> None:
        for contract in GEO_LAYER_CONTRACTS:
            for key, kind in contract["required_outputs"].items():
                with self.subTest(layer=contract["id"], output=key):
                    self.assertIn(kind, KIND_SAMPLES)

    def test_kind_samples_really_satisfy_the_kinds_they_stand_for(self) -> None:
        """Guards the fixture: ``_passing_world`` is only meaningful if every
        sample value is genuinely accepted for its kind."""
        for kind, sample in KIND_SAMPLES.items():
            with self.subTest(kind=kind):
                self.assertIs(_output_matches_kind(sample, kind), True)

    def test_unknown_output_kind_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError, r"^unknown geo layer output kind: bogus$"
        ):
            _output_matches_kind(1, "bogus")


class ContractTableTests(TestCase):
    """Structural invariants of the declared table and its projection."""

    def test_dependencies_are_declared_before_their_dependents(self) -> None:
        """``evaluate_geo_layer_contracts`` resolves dependencies in a single
        forward pass over ``GEO_LAYER_CONTRACTS``, so a dependency listed after
        its dependent would be silently reported as failed forever."""
        seen: list[str] = []
        for index, contract in enumerate(GEO_LAYER_CONTRACTS):
            layer_id = str(contract["id"])
            with self.subTest(layer=layer_id):
                self.assertEqual(contract["phase"], index)
                self.assertNotIn(layer_id, seen)
                for dependency in contract["dependencies"]:
                    self.assertIn(str(dependency), seen)
            seen.append(layer_id)

    def test_every_layer_echoes_its_declared_contract_metadata(self) -> None:
        """Under ``geo_only`` nothing is dropped, so each emitted layer must be
        an exact projection of its contract entry (no cross-layer mix-up)."""
        audit = evaluate_geo_layer_contracts(
            _passing_world(generation_scope="geo_only"), _passing_checks()
        )
        emitted = audit["layers"]
        self.assertEqual(len(emitted), len(GEO_LAYER_CONTRACTS))
        for contract, layer in zip(GEO_LAYER_CONTRACTS, emitted):
            with self.subTest(layer=contract["id"]):
                self.assertEqual(layer["id"], contract["id"])
                self.assertEqual(layer["phase"], contract["phase"])
                self.assertEqual(layer["name"], contract["name"])
                self.assertEqual(
                    layer["dependencies"], [str(d) for d in contract["dependencies"]]
                )
                self.assertEqual(
                    layer["required_outputs"], dict(contract["required_outputs"])
                )
                self.assertEqual(
                    layer["validator_domains"],
                    [str(d) for d in contract["validator_domains"]],
                )
                self.assertEqual(
                    layer["temporal_class"], contract["temporal_class"]
                )
                self.assertEqual(
                    layer["evidence_class"], contract["evidence_class"]
                )
                self.assertNotEqual(layer["temporal_class"], "")
                self.assertNotEqual(layer["evidence_class"], "")


class AuditShapeTests(TestCase):
    """The audit envelope and the fully satisfied baseline."""

    def test_complete_world_and_evidence_pass_every_layer_contract(self) -> None:
        audit = evaluate_geo_layer_contracts(_passing_world(), _passing_checks())

        # Pinned to the literal 1, not to the imported constant: comparing the
        # audit field against the module's own constant cannot fail if the
        # constant is bumped without a report_type change.
        self.assertEqual(LAYER_CONTRACT_SCHEMA_VERSION, 1)
        self.assertEqual(audit["schema_version"], 1)
        self.assertEqual(audit["report_type"], "geo_layer_contract_audit_v1")
        self.assertEqual(audit["scope"], "natural generation and maturation layers only")
        # The audit must keep disclaiming realism; a wording flip here would
        # turn a structural verdict into an empirical claim.
        self.assertIn("does not prove empirical realism", audit["interpretation"])
        self.assertEqual(audit["layer_count"], 14)
        self.assertEqual(audit["passed_layer_count"], 14)
        self.assertEqual(audit["failed_layer_count"], 0)
        self.assertTrue(audit["all_layer_contracts_passed"])
        for layer in audit["layers"]:
            with self.subTest(layer=layer["id"]):
                self.assertTrue(layer["contract_passed"])
                self.assertEqual(layer["missing_or_invalid_outputs"], [])
                self.assertEqual(layer["missing_validation_domains"], [])
                self.assertEqual(layer["failed_dependencies"], [])
                self.assertEqual(layer["failed_check_names"], [])
                self.assertEqual(layer["validation_error_failure_count"], 0)
                self.assertEqual(layer["validation_warning_count"], 0)
                self.assertEqual(layer["validation_not_applicable_count"], 0)
                # ``_passing_checks`` supplies exactly one passed check per
                # distinct domain, so both counts are the layer's domain count.
                domain_count = len(layer["validator_domains"])
                self.assertGreaterEqual(domain_count, 1)
                self.assertEqual(layer["validation_check_count"], domain_count)
                self.assertEqual(layer["validation_pass_count"], domain_count)
                self.assertEqual(
                    layer["validation_domain_coverage"],
                    {domain: 1 for domain in layer["validator_domains"]},
                )
                self.assertFalse(layer["empirical_realism_proven"])

    def test_none_world_fails_all_fourteen_layer_contracts(self) -> None:
        audit = evaluate_geo_layer_contracts(None, [])

        self.assertEqual(audit["report_type"], "geo_layer_contract_audit_v1")
        self.assertFalse(audit["all_layer_contracts_passed"])
        self.assertEqual(audit["layer_count"], 14)
        self.assertEqual(audit["passed_layer_count"], 0)
        self.assertEqual(audit["failed_layer_count"], 14)
        self.assertEqual([str(layer["id"]) for layer in audit["layers"]], list(LAYER_IDS))
        self.assertEqual(
            [layer["phase"] for layer in audit["layers"]], list(range(14))
        )
        for layer in audit["layers"]:
            with self.subTest(layer=layer["id"]):
                self.assertFalse(layer["contract_passed"])
                self.assertEqual(
                    layer["missing_or_invalid_outputs"],
                    list(layer["required_outputs"]),
                )
                self.assertEqual(
                    layer["missing_validation_domains"],
                    list(layer["validator_domains"]),
                )
                self.assertEqual(layer["validation_check_count"], 0)
                self.assertEqual(layer["validation_pass_count"], 0)
        # ``None`` normalizes to an empty root, so the default (non-``geo_only``)
        # scope applies and the provenance requirement is recorded as dropped.
        maturation = _layers(audit)["coupled_maturation"]
        self.assertEqual(
            maturation["scope_specific_omissions"],
            ["geo_evolution_provenance", "evolution_provenance"],
        )
        self.assertNotIn("geo_evolution_provenance", maturation["required_outputs"])

    def test_non_dict_checks_entries_are_ignored(self) -> None:
        clean = _passing_checks()
        checks: list[Any] = ["not a check", None, 7]
        checks.extend(_passing_checks())

        audit = evaluate_geo_layer_contracts(_passing_world(), checks)

        self.assertTrue(audit["all_layer_contracts_passed"])
        # Dropped, not coerced into evidence: the audit must be identical to the
        # one produced from the junk-free check list.
        self.assertEqual(audit, evaluate_geo_layer_contracts(_passing_world(), clean))
        for layer in audit["layers"]:
            with self.subTest(layer=layer["id"]):
                self.assertEqual(
                    layer["validation_check_count"], len(layer["validator_domains"])
                )

    def test_non_dict_world_never_passes_even_with_full_evidence(self) -> None:
        audit = evaluate_geo_layer_contracts("not-a-world", _passing_checks())

        self.assertFalse(audit["all_layer_contracts_passed"])
        self.assertEqual(audit["failed_layer_count"], 14)
        # Pin *why* it fails: the world normalizes to an empty root, so every
        # required artifact is missing even though every validator domain did
        # supply evidence (unlike the ``None``-world case, which has neither).
        for layer in audit["layers"]:
            with self.subTest(layer=layer["id"]):
                self.assertEqual(
                    layer["missing_or_invalid_outputs"],
                    list(layer["required_outputs"]),
                )
                self.assertEqual(layer["missing_validation_domains"], [])
                self.assertEqual(
                    layer["validation_check_count"], len(layer["validator_domains"])
                )
                self.assertFalse(layer["contract_passed"])
        # An empty root carries no ``generation_scope``, so the non-``geo_only``
        # contract applies rather than the stricter provenance-bearing one.
        maturation = _layers(audit)["coupled_maturation"]
        self.assertEqual(
            maturation["scope_specific_omissions"],
            ["geo_evolution_provenance", "evolution_provenance"],
        )
        self.assertNotIn("geo_evolution_provenance", maturation["required_outputs"])


class RequiredOutputTests(TestCase):
    """Artifact presence and kind enforcement, per layer."""

    def test_missing_required_output_is_named_on_its_own_layer(self) -> None:
        world = _passing_world()
        del world["sea_level_model"]

        audit = evaluate_geo_layer_contracts(world, _passing_checks())
        layers = _layers(audit)

        self.assertEqual(
            layers["sea_level_ocean"]["missing_or_invalid_outputs"],
            ["sea_level_model"],
        )
        self.assertFalse(layers["sea_level_ocean"]["contract_passed"])
        self.assertFalse(audit["all_layer_contracts_passed"])
        self.assertEqual(
            layers["relief_bathymetry"]["missing_or_invalid_outputs"], []
        )
        self.assertTrue(layers["relief_bathymetry"]["contract_passed"])

    def test_output_kinds_are_enforced_on_the_mesh_layer(self) -> None:
        world = _passing_world(
            cells=[],
            cell_area_model="   ",
            mesh_lod={},
            cell_adjacency_edges=[],
        )

        audit = evaluate_geo_layer_contracts(world, _passing_checks())
        mesh = _layers(audit)["spherical_mesh"]

        self.assertEqual(
            mesh["missing_or_invalid_outputs"],
            ["cells", "cell_area_model", "mesh_lod"],
        )
        self.assertNotIn("cell_adjacency_edges", mesh["missing_or_invalid_outputs"])
        self.assertNotIn(
            "spherical_spatial_index", mesh["missing_or_invalid_outputs"]
        )
        self.assertFalse(mesh["contract_passed"])

    def test_output_kind_rejections_are_reported_per_artifact(self) -> None:
        # ``expected`` is the *complete* invalid-artifact list for that layer,
        # so a rule that over-reports other artifacts is caught too.
        cases: tuple[tuple[str, str, Any, list[str]], ...] = (
            ("sea_level_ocean", "sea_level_model", {}, ["sea_level_model"]),
            ("sea_level_ocean", "sea_level_model", {"eustatic_m": 0.0}, []),
            ("sea_level_ocean", "marine_regions", [], []),
            ("sea_level_ocean", "marine_regions", {}, ["marine_regions"]),
            ("sea_level_ocean", "marine_regions", None, ["marine_regions"]),
            ("spherical_mesh", "cells", [], ["cells"]),
            ("spherical_mesh", "cells", [{"id": 0}], []),
            ("spherical_mesh", "cell_area_model", "  ", ["cell_area_model"]),
            ("spherical_mesh", "cell_area_model", "exact", []),
            ("spherical_mesh", "cell_area_model", b"exact", ["cell_area_model"]),
        )
        for layer_id, output, value, expected in cases:
            with self.subTest(output=output, value=value):
                world = _passing_world(**{output: value})
                audit = evaluate_geo_layer_contracts(world, _passing_checks())
                layer = _layers(audit)[layer_id]
                self.assertEqual(layer["missing_or_invalid_outputs"], expected)
                self.assertIs(layer["contract_passed"], not expected)


class ValidatorDomainTests(TestCase):
    """Every declared validator domain must supply at least one check."""

    def test_domain_without_evidence_fails_the_layer(self) -> None:
        audit = evaluate_geo_layer_contracts(
            _passing_world(), _passing_checks(skip=("ocean_circulation",))
        )
        ocean = _layers(audit)["sea_level_ocean"]

        self.assertEqual(ocean["missing_validation_domains"], ["ocean_circulation"])
        self.assertEqual(
            ocean["validation_domain_coverage"],
            {"sea_level": 1, "ocean_circulation": 0, "coastal_marine_landmass": 1},
        )
        self.assertEqual(ocean["missing_or_invalid_outputs"], [])
        self.assertFalse(ocean["contract_passed"])

    def test_not_applicable_evidence_is_counted_without_failing_the_layer(
        self,
    ) -> None:
        checks = [
            check
            for check in _passing_checks()
            if check["domain"] not in {"sea_level", "ocean_circulation"}
        ]
        checks.extend(
            {
                "domain": domain,
                "name": f"{domain}_skipped",
                "status": "not_applicable",
                "severity": "error",
            }
            for domain in ("sea_level", "ocean_circulation")
        )

        audit = evaluate_geo_layer_contracts(_passing_world(), checks)
        ocean = _layers(audit)["sea_level_ocean"]

        self.assertEqual(ocean["missing_validation_domains"], [])
        self.assertEqual(ocean["validation_pass_count"], 1)
        self.assertEqual(ocean["validation_not_applicable_count"], 2)
        self.assertEqual(ocean["validation_error_failure_count"], 0)
        self.assertTrue(ocean["contract_passed"])

    def test_layer_with_only_not_applicable_evidence_fails(self) -> None:
        checks = [
            check
            for check in _passing_checks()
            if check["domain"] not in {"contract"}
        ]
        checks.append(
            {
                "domain": "contract",
                "name": "planet_parameter_contract",
                "status": "not_applicable",
                "severity": "error",
            }
        )

        audit = evaluate_geo_layer_contracts(_passing_world(), checks)
        planet = _layers(audit)["planet_parameters"]

        self.assertEqual(planet["missing_validation_domains"], [])
        self.assertEqual(planet["validation_check_count"], 1)
        self.assertEqual(planet["validation_pass_count"], 0)
        self.assertEqual(planet["validation_not_applicable_count"], 1)
        self.assertFalse(planet["contract_passed"])


class CheckSeverityTests(TestCase):
    """Only ``failed`` + ``error`` is fatal; ``warning`` is recorded, not fatal."""

    @staticmethod
    def _with_sea_level_failure(severity: str) -> list[dict[str, Any]]:
        checks = _passing_checks()
        checks.append(
            {
                "domain": "sea_level",
                "name": "ocean_volume_closure",
                "status": "failed",
                "severity": severity,
            }
        )
        return checks

    def test_failed_error_check_fails_the_layer_and_is_named(self) -> None:
        audit = evaluate_geo_layer_contracts(
            _passing_world(), self._with_sea_level_failure("error")
        )
        ocean = _layers(audit)["sea_level_ocean"]

        self.assertFalse(ocean["contract_passed"])
        self.assertEqual(
            ocean["failed_check_names"], ["sea_level.ocean_volume_closure"]
        )
        self.assertEqual(ocean["validation_error_failure_count"], 1)
        self.assertEqual(ocean["validation_warning_count"], 0)
        self.assertEqual(ocean["validation_pass_count"], 3)
        self.assertEqual(ocean["validation_check_count"], 4)
        self.assertEqual(ocean["missing_or_invalid_outputs"], [])
        self.assertEqual(ocean["missing_validation_domains"], [])
        self.assertFalse(audit["all_layer_contracts_passed"])

    def test_failed_warning_check_leaves_the_layer_passing(self) -> None:
        audit = evaluate_geo_layer_contracts(
            _passing_world(), self._with_sea_level_failure("warning")
        )
        ocean = _layers(audit)["sea_level_ocean"]

        self.assertTrue(ocean["contract_passed"])
        self.assertEqual(ocean["failed_check_names"], [])
        self.assertEqual(ocean["validation_warning_count"], 1)
        self.assertEqual(ocean["validation_error_failure_count"], 0)
        self.assertEqual(ocean["validation_pass_count"], 3)
        self.assertEqual(ocean["validation_check_count"], 4)
        self.assertTrue(audit["all_layer_contracts_passed"])

    def test_failed_check_with_unclassified_severity_is_non_fatal(self) -> None:
        audit = evaluate_geo_layer_contracts(
            _passing_world(), self._with_sea_level_failure("info")
        )
        ocean = _layers(audit)["sea_level_ocean"]

        self.assertTrue(ocean["contract_passed"])
        self.assertEqual(ocean["failed_check_names"], [])
        self.assertEqual(ocean["validation_error_failure_count"], 0)
        self.assertEqual(ocean["validation_warning_count"], 0)
        self.assertEqual(ocean["validation_check_count"], 4)


class DependencyPropagationTests(TestCase):
    """A failed upstream contract is named by every dependent layer."""

    def test_phase_zero_failure_is_reported_by_the_phase_one_layer(self) -> None:
        checks = _passing_checks()
        checks.append(
            {
                "domain": "contract",
                "name": "planet_parameter_ranges",
                "status": "failed",
                "severity": "error",
            }
        )

        audit = evaluate_geo_layer_contracts(_passing_world(), checks)
        layers = _layers(audit)
        planet = layers["planet_parameters"]
        mesh = layers["spherical_mesh"]

        self.assertFalse(planet["contract_passed"])
        self.assertEqual(planet["phase"], 0)
        self.assertEqual(
            planet["failed_check_names"], ["contract.planet_parameter_ranges"]
        )

        self.assertEqual(mesh["phase"], 1)
        self.assertEqual(mesh["failed_dependencies"], ["planet_parameters"])
        self.assertEqual(mesh["missing_or_invalid_outputs"], [])
        self.assertEqual(mesh["missing_validation_domains"], [])
        self.assertEqual(mesh["validation_error_failure_count"], 0)
        self.assertEqual(mesh["validation_pass_count"], 3)
        self.assertFalse(mesh["contract_passed"])

    def test_root_failure_cascades_through_the_whole_dependency_graph(self) -> None:
        world = _passing_world()
        del world["planet_parameters"]

        audit = evaluate_geo_layer_contracts(world, _passing_checks())
        layers = _layers(audit)

        self.assertEqual(
            layers["planet_parameters"]["missing_or_invalid_outputs"],
            ["planet_parameters"],
        )
        self.assertEqual(audit["passed_layer_count"], 0)
        self.assertEqual(audit["failed_layer_count"], 14)
        for contract in GEO_LAYER_CONTRACTS:
            layer_id = str(contract["id"])
            if layer_id == "planet_parameters":
                continue
            layer = layers[layer_id]
            with self.subTest(layer=layer_id):
                declared = [str(dep) for dep in contract["dependencies"]]
                # Compared against the declared contract table, not against the
                # layer's own echoed ``dependencies`` field: that self-comparison
                # would hold even if both fields collapsed to the same wrong list.
                self.assertNotEqual(declared, [])
                self.assertEqual(layer["failed_dependencies"], declared)
                self.assertEqual(layer["dependencies"], declared)
                self.assertEqual(layer["missing_or_invalid_outputs"], [])
                self.assertEqual(layer["missing_validation_domains"], [])

    def test_only_declared_dependents_are_affected(self) -> None:
        checks = _passing_checks()
        checks.append(
            {
                "domain": "cryosphere_permafrost_glacial",
                "name": "permafrost_extent",
                "status": "failed",
                "severity": "error",
            }
        )

        audit = evaluate_geo_layer_contracts(_passing_world(), checks)
        layers = _layers(audit)

        self.assertFalse(layers["cryosphere"]["contract_passed"])
        self.assertEqual(
            layers["soils_pedogenesis"]["failed_dependencies"], ["cryosphere"]
        )
        self.assertEqual(
            layers["coupled_maturation"]["failed_dependencies"], ["cryosphere"]
        )
        self.assertTrue(layers["hydrology"]["contract_passed"])
        self.assertEqual(layers["hydrology"]["failed_dependencies"], [])
        self.assertTrue(layers["erosion_sediment"]["contract_passed"])


class GenerationScopeTests(TestCase):
    """``geo_only`` worlds must carry provenance; other scopes must not be asked."""

    def test_geo_only_scope_requires_evolution_provenance(self) -> None:
        world = _passing_world(generation_scope="geo_only")
        audit = evaluate_geo_layer_contracts(world, _passing_checks())
        maturation = _layers(audit)["coupled_maturation"]

        self.assertEqual(maturation["scope_specific_omissions"], [])
        self.assertIn("geo_evolution_provenance", maturation["required_outputs"])
        self.assertIn("evolution_provenance", maturation["validator_domains"])
        self.assertTrue(maturation["contract_passed"])
        self.assertTrue(audit["all_layer_contracts_passed"])

    def test_geo_only_scope_without_provenance_artifact_fails(self) -> None:
        world = _passing_world(generation_scope="geo_only")
        del world["geo_evolution_provenance"]

        audit = evaluate_geo_layer_contracts(world, _passing_checks())
        maturation = _layers(audit)["coupled_maturation"]

        self.assertEqual(
            maturation["missing_or_invalid_outputs"], ["geo_evolution_provenance"]
        )
        self.assertFalse(maturation["contract_passed"])
        self.assertFalse(audit["all_layer_contracts_passed"])

    def test_geo_only_scope_without_provenance_evidence_fails(self) -> None:
        world = _passing_world(generation_scope="geo_only")

        audit = evaluate_geo_layer_contracts(
            world, _passing_checks(skip=("evolution_provenance",))
        )
        maturation = _layers(audit)["coupled_maturation"]

        self.assertEqual(
            maturation["missing_validation_domains"], ["evolution_provenance"]
        )
        self.assertEqual(maturation["missing_or_invalid_outputs"], [])
        self.assertFalse(maturation["contract_passed"])

    def test_non_geo_only_scope_drops_the_provenance_requirement(self) -> None:
        world = _passing_world()
        del world["geo_evolution_provenance"]

        audit = evaluate_geo_layer_contracts(
            world, _passing_checks(skip=("evolution_provenance",))
        )
        maturation = _layers(audit)["coupled_maturation"]

        self.assertEqual(
            maturation["scope_specific_omissions"],
            ["geo_evolution_provenance", "evolution_provenance"],
        )
        self.assertNotIn("geo_evolution_provenance", maturation["required_outputs"])
        self.assertNotIn("evolution_provenance", maturation["validator_domains"])
        self.assertEqual(maturation["missing_or_invalid_outputs"], [])
        self.assertEqual(maturation["missing_validation_domains"], [])
        self.assertTrue(maturation["contract_passed"])
        self.assertTrue(audit["all_layer_contracts_passed"])

    def test_unknown_scope_value_is_treated_as_not_geo_only(self) -> None:
        world = _passing_world(generation_scope="full")
        del world["geo_evolution_provenance"]

        audit = evaluate_geo_layer_contracts(
            world, _passing_checks(skip=("evolution_provenance",))
        )
        maturation = _layers(audit)["coupled_maturation"]

        self.assertEqual(
            maturation["scope_specific_omissions"],
            ["geo_evolution_provenance", "evolution_provenance"],
        )
        self.assertTrue(maturation["contract_passed"])

    def test_scope_omissions_are_empty_for_every_non_maturation_layer(self) -> None:
        dropped = ["geo_evolution_provenance", "evolution_provenance"]
        for scope, expected_maturation in (
            ("geo_only", []),
            ("full", dropped),
            (None, dropped),
        ):
            with self.subTest(scope=scope):
                world = _passing_world()
                if scope is not None:
                    world["generation_scope"] = scope
                audit = evaluate_geo_layer_contracts(world, _passing_checks())
                for layer in audit["layers"]:
                    if layer["id"] == "coupled_maturation":
                        # The one layer that may record an omission, and only
                        # outside ``geo_only``.
                        self.assertEqual(
                            layer["scope_specific_omissions"], expected_maturation
                        )
                        continue
                    self.assertEqual(layer["scope_specific_omissions"], [])
