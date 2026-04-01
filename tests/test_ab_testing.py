from pathlib import Path

from reagent.core.catalog import Catalog, CatalogEntry
from reagent.core.parsers import AssetType
from reagent.evaluation.evaluator import ABTestStore, create_variant, promote_variant


class TestABTestStoreBasics:
    def test_empty_store(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.load()
        assert store.all_tests() == []

    def test_create_save_load(self, tmp_path: Path) -> None:
        path = tmp_path / "ab.jsonl"
        store = ABTestStore(path)
        store.create_test("repo:skill:deploy", "v2", "faster deploys")
        store.save()

        store2 = ABTestStore(path)
        store2.load()
        tests = store2.all_tests()
        assert len(tests) == 1
        assert tests[0].test_id == "repo:skill:deploy::v2"
        assert tests[0].variant_name == "v2"
        assert tests[0].description == "faster deploys"
        assert tests[0].active is True

    def test_get_test(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        test = store.get_test("repo:skill:deploy::v2")
        assert test is not None
        assert test.variant_name == "v2"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        assert store.get_test("nope") is None

    def test_deactivate(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        store.deactivate("repo:skill:deploy::v2")
        test = store.get_test("repo:skill:deploy::v2")
        assert test is not None
        assert test.active is False


class TestVariantRouting:
    def test_deterministic(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        test_id = "repo:skill:deploy::v2"

        result1 = store.route_session(test_id, "session-42")
        result2 = store.route_session(test_id, "session-42")
        assert result1 == result2

    def test_covers_both_routes(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        test_id = "repo:skill:deploy::v2"

        results = {store.route_session(test_id, f"session-{i}") for i in range(50)}
        assert "original" in results
        assert "variant" in results

    def test_inactive_returns_original(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        test_id = "repo:skill:deploy::v2"
        store.deactivate(test_id)
        assert store.route_session(test_id, "any") == "original"

    def test_missing_test_returns_original(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        assert store.route_session("nope", "any") == "original"


class TestCreateVariant:
    def test_creates_variant_file(self, tmp_path: Path) -> None:
        asset_file = tmp_path / "deploy" / "SKILL.md"
        asset_file.parent.mkdir(parents=True)
        asset_file.write_text("---\nname: deploy\n---\nDeploy to prod.\n")

        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="repo:skill:deploy",
                asset_type=AssetType.SKILL,
                name="deploy",
                repo_path=tmp_path,
                file_path=asset_file,
                content_hash="abc",
            )
        )

        ab_store = ABTestStore(tmp_path / "ab.jsonl")
        test = create_variant(
            "repo:skill:deploy", "fast", "faster deploy", catalog, ab_store
        )
        assert test.test_id == "repo:skill:deploy::fast"

        variant = Path(test.variant_path)
        assert variant.exists()
        assert variant.read_text() == asset_file.read_text()
        assert variant.name == "SKILL.variant-fast.md"

    def test_multiple_variants(self, tmp_path: Path) -> None:
        asset_file = tmp_path / "review.md"
        asset_file.write_text("original")

        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="repo:agent:review",
                asset_type=AssetType.AGENT,
                name="review",
                repo_path=tmp_path,
                file_path=asset_file,
                content_hash="abc",
            )
        )

        ab_store = ABTestStore(tmp_path / "ab.jsonl")
        t1 = create_variant("repo:agent:review", "v2", "", catalog, ab_store)
        t2 = create_variant("repo:agent:review", "v3", "", catalog, ab_store)
        assert t1.test_id != t2.test_id
        assert Path(t1.variant_path) != Path(t2.variant_path)


class TestPromoteVariant:
    def test_promote_overwrites_original(self, tmp_path: Path) -> None:
        original = tmp_path / "review.md"
        variant = tmp_path / "review.variant-v2.md"
        original.write_text("old version")
        variant.write_text("new version")

        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test(
            "repo:agent:review",
            "v2",
            original_path=str(original),
            variant_path=str(variant),
        )

        test_id = "repo:agent:review::v2"
        result = promote_variant(test_id, store)
        assert result == original
        assert original.read_text() == "new version"

        test = store.get_test(test_id)
        assert test is not None
        assert not test.active

    def test_promote_nonexistent_test(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        assert promote_variant("nope", store) is None

    def test_promote_missing_variant_file(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test(
            "repo:agent:review",
            "v2",
            original_path=str(tmp_path / "review.md"),
            variant_path=str(tmp_path / "missing.md"),
        )
        assert promote_variant("repo:agent:review::v2", store) is None


class TestGetTestsForAsset:
    def test_filters_by_asset(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        store.create_test("repo:agent:review", "v2")
        store.create_test("repo:skill:deploy", "v3")

        tests = store.get_tests_for_asset("repo:skill:deploy")
        assert len(tests) == 2

    def test_excludes_inactive(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("repo:skill:deploy", "v2")
        store.create_test("repo:skill:deploy", "v3")
        store.deactivate("repo:skill:deploy::v2")

        tests = store.get_tests_for_asset("repo:skill:deploy")
        assert len(tests) == 1
        assert tests[0].variant_name == "v3"
