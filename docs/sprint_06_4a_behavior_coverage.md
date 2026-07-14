# Sprint 06.4A material behavior coverage

| Behavior | Node | Material setup | Production mutation/assertion | Expected |
|---|---|---|---|---|
| 06.4A-CHUNK-IDEMPOTENT | `tests/test_sprint_06_4a_atomic_import_and_roundtrip.py::test_atomic_chunk_roundtrip_and_idempotent_reuse` | writes a real Parquet chunk into a temporary store | production writer validates manifest/readback and reuses identical chunk | identical manifest returned |
| 06.4A-MINUTE-GAPS | `tests/test_sprint_06_4a_coverage_resume_gap_repair.py::test_complete_and_gapped_minute_planning` | scans concrete minute timestamps with holes | production coverage planner emits bounded missing windows | exact missing windows |
| 06.4A-DUP-FUNDING | `tests/test_sprint_06_4a_coverage_resume_gap_repair.py::test_duplicate_and_pair_readiness_and_funding_observed_only` | supplies duplicate minute data and funding observations | production coverage/funding audits reject duplicates and do not claim global funding completeness | duplicate_timestamp and observed-only funding |
| 06.4A-SCHEMA | `tests/test_sprint_06_4a_parquet_store_contract.py::test_exact_arrow_schema_for_all_four_datasets` | asks production schema registry for all datasets | asserts exact Arrow fields and decimal types | schemas exact |
| 06.4A-DECIMAL | `tests/test_sprint_06_4a_parquet_store_contract.py::test_decimal_policy_and_canonical_negative_zero` | validates Decimal values including negative zero and overflow candidates | production Decimal/canonical code accepts exact values and rejects rounding/overflow | decimal_not_exact/overflow stable |
| 06.4A-PATHS | `tests/test_sprint_06_4a_parquet_store_contract.py::test_safe_paths` | derives real chunk paths from symbols/timestamps | production path grammar rejects unsafe symbols and cross-month ranges | safe paths only |
| 06.4A-SOURCE-TREE | `tests/test_sprint_06_4a_store_evidence_pack.py::test_source_tree_manifest_deterministic` | hashes a temporary source tree with deterministic files | production source-tree manifest is stable and ignores generated evidence | deterministic manifest |
| 06.4A-ZIP-SAFE | `tests/test_sprint_06_4a_store_evidence_pack.py::test_unsafe_zip_path_rejected` | passes unsafe ZIP member names to production seed checker helper | production path validator rejects traversal/absolute/backslash names | unsafe_zip_path |
