# Graph Report - .  (2026-07-20)

## Corpus Check
- 82 files · ~69,610 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2075 nodes · 6122 edges · 103 communities (95 shown, 8 thin omitted)
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 1704 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Capability Manifest & Models
- Legacy Collectors
- EC2 Contract & Adapter
- Profile Registry
- Assessment Profiles
- Execution Context & Orchestration
- AWS Assessment Core
- EC2 Contract Validation
- Orchestrator Planning
- Schema Processor
- Profile Interfaces
- Planner Target Pairs
- Orchestrator Tests
- Agentic Interfaces
- Schema Catalog
- Cost Optimization Collectors
- EC2 Collector Tests
- Legacy S3/VPC/Backup Collectors
- Foundation Contract Tests
- Evidence & Resource Records
- Orchestrator Profile Tests
- Bounded Executor
- Legacy Record Collector
- Compute Inventory (ALB/EC2)
- Core Models
- EC2 Integration Tests
- SemVer Model
- Property Schema Roundtrip
- EC2 Inventory Collector
- Structured Errors
- Run History
- Legacy Adapter
- Executor Aggregation
- HTML Report Generator
- Executor Status Aggregation
- Executor Execution
- Collection Window Model
- Legacy Migration Tests
- Capability Registry Tests
- EC2 Collector Instance
- EC2 Filter Translation
- Capability Summary
- Execution Plan & Deterministic Planning
- Guarded Session Identity
- Session Factory
- Schema Processor Tests A
- Capability Descriptor
- Collector Interfaces
- History Store Interface
- Execution Unit & Concurrency
- Schema Canonical Bytes
- EC2 Integration Fakes
- Schema Package Init
- Session Build & Name
- Report Template Scripts
- Profile Release Rules Tests A
- EC2 Reference Property Tests
- Schema Processor Tests B
- Interactive Utils
- Assessment Engine Core
- Schema Processor Tests C
- Assessment Run & Reports
- EC2 Reference Scenarios
- Legacy Contracts
- SemVer Parsing
- README Concepts
- Foundation Contract Tests B
- Orchestrator Profile Tests B
- Schema Processor Test Setup
- Session Factory Tests
- Evidence Store Interface
- Guarded Session Init
- Legacy Contracts Tests
- Planner Tests Rationale
- Profile Release Rules Tests B
- Profile Release Rules Tests C
- Schema Processor Tests D
- Schema Processor Tests E
- Session Factory Tests B
- Guard Violation Error
- Database Collectors
- Report Pipeline (Docs)
- EBS/NAT Legacy Collectors
- Registry Digest & Discovery
- Compute Collector Tests
- EC2 Integration Rationale
- Executor Exception Tests
- Registry Cycle Detection
- EC2 Collector Edge Cases
- Legacy Adapter Regression
- Schema Catalog Versions
- Readiness Handler
- Profile Publication Error
- Capability Registry Setup
- EC2 Predicate State Test
- EC2 Predicate VPC Test
- Hypothesis Dependency
- Pytest Dependency
- Python-dotenv Dependency

## God Nodes (most connected - your core abstractions)
1. `SemVer` - 200 edges
2. `StructuredError` - 191 edges
3. `CanonicalSchemaProcessor` - 185 edges
4. `CapabilityRegistryImpl` - 170 edges
5. `AccountTarget` - 169 edges
6. `CollectorOutcome` - 162 edges
7. `CapabilityRequest` - 117 edges
8. `CapabilityDescriptor` - 113 edges
9. `InvocationRequest` - 98 edges
10. `ExecutionContext` - 90 edges

## Surprising Connections (you probably didn't know these)
- `Cost Optimization Section` --semantically_similar_to--> `Cost Optimization Analysis`  [INFERRED] [semantically similar]
  templates/report_template.html → README.md
- `TestAWSErrorHandling` --uses--> `EC2InventoryCollector`  [INFERRED]
  tests/test_ec2_collector.py → agentic/ec2_collector.py
- `TestDeduplication` --uses--> `EC2InventoryCollector`  [INFERRED]
  tests/test_ec2_collector.py → agentic/ec2_collector.py
- `TestEmptyResult` --uses--> `EC2InventoryCollector`  [INFERRED]
  tests/test_ec2_collector.py → agentic/ec2_collector.py
- `TestEvidenceMetadata` --uses--> `EC2InventoryCollector`  [INFERRED]
  tests/test_ec2_collector.py → agentic/ec2_collector.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Assessment Report Generation Pipeline** — readme_aws_account_assessment_tool, templates_report_template, requirements_playwright, readme_cost_optimization [INFERRED 0.75]
- **Agentic Invocation Stack** — readme_agentic_mode, readme_capability_registry, readme_bounded_concurrent_executor, readme_guarded_session, readme_canonical_schema_processor [EXTRACTED 1.00]

## Communities (103 total, 8 thin omitted)

### Community 0 - "Capability Manifest & Models"
Cohesion: 0.05
Nodes (53): CapabilityManifest, LifecycleMetadata, Lifecycle metadata for deprecated/removed capabilities., Immutable snapshot of all registered capabilities with a content digest., DuplicateCapabilityError, Exception, Raised when capability registration fails validation., Raised when a duplicate (capability_id, major_version) is registered. (+45 more)

### Community 1 - "Legacy Collectors"
Cohesion: 0.05
Nodes (70): _build_evidence(), collect_amazonmq_inventory(), collect_billing_summary(), collect_cloudfront_inventory(), collect_cloudtrail_inventory(), collect_cloudwatch_inventory(), collect_config_inventory(), collect_cost_optimization_findings() (+62 more)

### Community 2 - "EC2 Contract & Adapter"
Cohesion: 0.07
Nodes (44): EC2 Inventory Capability Contract — Request Validation and Registration.  Impl, Register the ec2.inventory@1.0.0 capability to the registry.      Creates the, register_ec2_inventory(), _get_registry(), Build (once) the same Capability Registry an Agent invocation uses., Legacy Capability Contracts — Allowlist and Schema Definitions.  Defines a Cap, Register a single legacy capability descriptor with its handler., Register every legacy capability spec using its migrated     GuardedSession-bac (+36 more)

### Community 3 - "Profile Registry"
Cohesion: 0.09
Nodes (29): Combination of capability, field set, target applicability,     required permis, RequiredProfileItem, AssessmentProfileRegistryImpl, ProfilePublicationError, Exception, Concrete implementation of the AssessmentProfileRegistry Protocol.      Publis, Raised when profile publication fails validation., _make_valid_profile() (+21 more)

### Community 4 - "Assessment Profiles"
Cohesion: 0.05
Nodes (30): Assessment Profiles — Pre-built profile artifacts.  Exports factory functions, create_monthly_standard_v1(), monthly-standard@1.0.0 Assessment Profile — Draft Baseline.  Enumerates ALL re, Create the monthly-standard@1.0.0 assessment profile in draft status.      Thi, Unit tests for monthly-standard@1.0.0 Assessment Profile.  Verifies the profil, Collection window period_type must be 'monthly'., Every item must have a non-empty capability_id., Every item must have a non-empty capability_version. (+22 more)

### Community 5 - "Execution Context & Orchestration"
Cohesion: 0.07
Nodes (33): ExecutionContext, InvocationRequest, Execution Context: caller identity, correlation ID, Idempotency Key,     purpos, Versioned Invocation Request payload. Exactly one of `capabilities` or     `pro, Validate the InvocationRequest before planning.      Checks:     - Exactly on, _validate_request(), FakeS3Collector, _make_invocation_request() (+25 more)

### Community 6 - "AWS Assessment Core"
Cohesion: 0.08
Nodes (42): inventory_ecr(), inventory_eks(), inventory_lambda(), Inventory ECR repositories, Inventory Lambda functions, Inventory EKS clusters, inventory_amazonmq(), inventory_cloudwatch() (+34 more)

### Community 7 - "EC2 Contract Validation"
Cohesion: 0.05
Nodes (30): Any, Validate ec2.inventory request parameters before collection.      Checks:, validate_ec2_parameters(), Valid parameters pass validation without error., Empty parameters are valid (no filters, no field selection)., Explicit resource_type='instance' is valid., Valid filter with states list., Valid filter with instance_ids list. (+22 more)

### Community 8 - "Orchestrator Planning"
Cohesion: 0.06
Nodes (44): _build_scope_map(), _compute_plan_digest(), _compute_request_digest(), _compute_unit_id(), _find_prerequisite_unit_ids(), _get_latest_major(), _get_parameters_for_capability(), invoke() (+36 more)

### Community 9 - "Schema Processor"
Cohesion: 0.10
Nodes (31): CapabilityRequest, A single capability selection within an Invocation Request., CanonicalSchemaProcessor, Check if transitioning between versions is compatible (same major).         Inc, Implements the SchemaProcessor protocol using checked-in JSON Schemas     and c, FakeCollector, FakeSessionFactory, _make_regional_only_registry() (+23 more)

### Community 10 - "Profile Interfaces"
Cohesion: 0.06
Nodes (26): Resolve an exact profile version. Returns immutable profile content., Resolve the latest profile compatible with the given major version.         Onl, Publish a profile version. Returns the content digest.         Rejects publicat, AssessmentProfile, Frozen Assessment Profile. Published versions are immutable and     content-add, Any, Assessment Profile Registry — Immutable Profile Publication and Resolution.  I, Resolve an exact profile version. Returns immutable profile content.         Re (+18 more)

### Community 11 - "Planner Target Pairs"
Cohesion: 0.08
Nodes (29): AccountTarget, An AWS Account target with an optional role reference., _make_registry_global_and_regional(), _make_request(), Tests for _normalize_targets (regional scope)., Single account x single region produces one pair., Duplicate account-region pairs are deduplicated., Result is sorted lexicographically by (account_id, region). (+21 more)

### Community 12 - "Orchestrator Tests"
Cohesion: 0.07
Nodes (28): FakeCollector, _make_registry_with_ec2(), _make_registry_with_prereqs(), _make_valid_request(), Create a valid InvocationRequest., Tests for unsupported capability/version handling., Unknown capability ID returns failed InvocationResult., Unsupported version returns failed InvocationResult. (+20 more)

### Community 13 - "Agentic Interfaces"
Cohesion: 0.12
Nodes (29): Agentic AWS Assessment — Contract Layer.  This package defines the versioned d, AssessmentProfileRegistry, CapabilityRegistry, Collector, GuardedSession, Agentic AWS Assessment — Protocol Interfaces.  These Protocol classes define t, Contract Collector that returns a typed CollectorOutcome.     A bare boolean is, Session boundary that intercepts every SDK operation and checks it     against (+21 more)

### Community 14 - "Schema Catalog"
Cohesion: 0.06
Nodes (22): Any, Loads checked-in JSON Schema documents and provides lookup by     (schema_id, v, Retrieve the JSON Schema for a given schema_id and version.          Raises Va, Return all supported schema IDs with their available versions., Check if a schema_id/version combination is registered., SchemaCatalog, Access the underlying schema catalog., catalog() (+14 more)

### Community 15 - "Cost Optimization Collectors"
Cohesion: 0.08
Nodes (37): _ebs_monthly_cost(), _get_instance_family(), Cost Optimization Collector ============================ Mendeteksi resource yan, Flag ALB/NLB tanpa target group atau tanpa target aktif., Extract family from instance type, e.g. 'c5.2xlarge' → 'c5'., Flag Linux x86_64 instances yang bisa migrasi ke Graviton., Flag instance yang punya Public IPv4 (charged sejak Feb 2024)., Flag S3 buckets yang tidak punya lifecycle rule. (+29 more)

### Community 16 - "EC2 Collector Tests"
Cohesion: 0.09
Nodes (24): default_params(), _make_mock_session(), _make_page(), _make_raw_instance(), Any, Wrap instances into a DescribeInstances page., Single page with one instance returns one record., Multiple pages all get collected. (+16 more)

### Community 17 - "Legacy S3/VPC/Backup Collectors"
Cohesion: 0.09
Nodes (26): build_legacy_collector(), collect_backup_inventory(), collect_s3_inventory(), collect_vpc_inventory(), CostOptimizationFindingsCollector, Structural `Collector` adapter for the derived `cost-optimization.findings`, Factory returning the migrated Collector adapter for one legacy     capability_, Migrated from `collectors/storage.py::inventory_s3()`. (+18 more)

### Community 18 - "Foundation Contract Tests"
Cohesion: 0.08
Nodes (25): collector(), FakeCollector, processor(), Foundation Contract / Snapshot Tests.  Verifies the agentic foundation as a wh, After a failed duplicate registration, original remains intact., Failed duplicate registration does not corrupt the original entry., Registry snapshot is unchanged after failed duplicate registration., Manifest does not change without new registrations. (+17 more)

### Community 19 - "Evidence & Resource Records"
Cohesion: 0.11
Nodes (34): Evidence, Collected resource record with stable identity, schema fields,     and provenan, Evidence linking a collected record to its source., Combination of one AWS Account and one AWS Region (or 'aws-global')., ResourceRecord, TargetPair, All domain models must be frozen (immutable)., test_model_is_frozen() (+26 more)

### Community 20 - "Orchestrator Profile Tests"
Cohesion: 0.10
Nodes (23): FakeCollector, _make_active_profile(), _make_capability_registry(), _make_profile_registry_with_active(), _make_profile_request(), Tests for Assessment Orchestrator — Profile Mode Integration.  Covers: - Prof, Create an active profile with ec2 and s3 items., Create a profile registry with an active monthly-standard profile. (+15 more)

### Community 21 - "Bounded Executor"
Cohesion: 0.14
Nodes (21): BoundedExecutor, Runs execution units with configurable global and per-account concurrency     b, FakeSessionFactory, _make_plan(), _make_unit(), Fake SessionFactory for testing — returns a MagicMock session., Basic execution tests., Verify at most global_concurrency units run concurrently. (+13 more)

### Community 22 - "Legacy Record Collector"
Cohesion: 0.12
Nodes (18): LegacyRecordsCollector, _map_client_error(), ClientError, Map a botocore ClientError to a StructuredError.      AccessDenied/Unauthorize, Structural `Collector` adapter for the 24 "simple" legacy capabilities     (eve, _client_error(), FakeGuardedSession, Any (+10 more)

### Community 23 - "Compute Inventory (ALB/EC2)"
Cohesion: 0.12
Nodes (22): inventory_alb(), inventory_ec2(), Inventory Application Load Balancers (ALB), Inventory EC2 instances, _make_assessment_data(), _make_mock_session(), Property-based tests for collectors/compute.py Feature: compute-collector-enhan, Unit tests for EC2 field extraction edge cases. (+14 more)

### Community 24 - "Core Models"
Cohesion: 0.16
Nodes (24): CompletenessDelta, CompletenessItem, CompletenessReport, PermissionResult, Agentic AWS Assessment — Immutable Domain Models.  All persisted models carry, One completeness row keyed by (account_id, region_scope, capability_id,     req, Machine-readable completeness report. Category totals equal the     applicable, One permission classification per (target scope, permission). (+16 more)

### Community 25 - "EC2 Integration Tests"
Cohesion: 0.11
Nodes (24): collector(), _make_mock_session(), _make_page(), _make_raw_instance(), Any, datetime, EC2 Integration Tests — End-to-End invoke() → plan → routing → collector flow., Wrap instances into a DescribeInstances page. (+16 more)

### Community 26 - "SemVer Model"
Cohesion: 0.08
Nodes (15): Semantic Version identifier (major.minor.patch)., SemVer, Exact version match returns the registered capability., resolve_compatible returns the entry for the given major version., Resolution works correctly with multiple registered capabilities., Verify contract constants are correctly defined., TestEC2ContractConstants, FakeCollector (+7 more)

### Community 27 - "Property Schema Roundtrip"
Cohesion: 0.11
Nodes (20): _assert_keys_sorted(), credential_payloads(), invalid_structured_error_payloads(), nan_infinity_payloads(), Any, DrawFn, Generate payloads missing required fields or with wrong types., Generate payloads that contain NaN or Infinity at random positions. (+12 more)

### Community 28 - "EC2 Inventory Collector"
Cohesion: 0.10
Nodes (19): _apply_field_projection(), _matches_local_predicate(), _normalize_instance(), _normalize_launch_time(), Any, Exception, EC2 Inventory Collector — Typed Adapter returning CollectorOutcome.  Implement, Apply normalized predicate locally as defensive check.     Re-checks filters on (+11 more)

### Community 29 - "Structured Errors"
Cohesion: 0.09
Nodes (15): Structured Error containing capability ID, Target Pair, error category,     ret, StructuredError, Resolve a registered capability by exact version match.         Returns Structu, Resolve the latest minor/patch within the same major version.         Returns S, Create a StructuredError for unsupported capability/version,         listing su, Convert to a StructuredError for external reporting (Req 1.2)., Schema Catalog — loads and manages versioned JSON Schemas.  Maps (schema_id, v, Non-matching version returns StructuredError. (+7 more)

### Community 30 - "Run History"
Cohesion: 0.08
Nodes (14): list_runs(), _matches_account_id(), Agentic AWS Assessment — Persisted Run Listing (Requirement 11.2).  One pure f, Recursively check whether any `account_id` field equals the target.      Invoc, List persisted run JSON files under `output/agentic/runs/`.      Returns an em, Path, Verify AssessmentProfile JSON Schema file exists at expected path., Verify schema_id and version match what the JSON schema declares. (+6 more)

### Community 31 - "Legacy Adapter"
Cohesion: 0.14
Nodes (19): _fake_legacy_collector(), _project_ec2_fields(), _project_records(), Any, Legacy Interactive Adapter (Task 8.2).  One small function that lets the inter, ec2.inventory field names differ slightly from the legacy shape., Rebuild the exact legacy `assessment_data['services'][code]` shape     (Req 13., Collect one wizard-selected service, routed through the Capability     Registry (+11 more)

### Community 32 - "Executor Aggregation"
Cohesion: 0.14
Nodes (17): aggregate_capability_status(), aggregate_region_status(), Agentic AWS Assessment — Bounded Executor and Aggregate Status Views.  Impleme, Derive aggregate status for a specific region scope from unit results.     Same, Derive aggregate status for a specific capability from unit results.     Same l, Per-unit execution state tracking., UnitExecutionState, Enum (+9 more)

### Community 33 - "HTML Report Generator"
Cohesion: 0.13
Nodes (16): generate_html_report(), HTML Report Generator Orchestrator yang merakit semua section menjadi satu file, Generate HTML report dari template dan kembalikan path file output., core/reporter — public API Import dari sini agar caller tidak perlu tahu struktu, generate_pdf_report(), PDF Report Generator Render HTML report ke PDF menggunakan Playwright headless C, Generate PDF dari file HTML. Return path PDF atau None jika gagal., generate_cost_optimization() (+8 more)

### Community 34 - "Executor Status Aggregation"
Cohesion: 0.19
Nodes (11): aggregate_account_status(), aggregate_run_status(), Derive aggregate run status from immutable unit results.      - "succeeded" if, Derive aggregate status for a specific account from unit results.     Same logi, Per-execution-unit outcome within an Invocation Result., UnitResult, Tests for aggregate_run_status., Status derivation does not depend on result order. (+3 more)

### Community 35 - "Executor Execution"
Cohesion: 0.10
Nodes (10): Execute all units in the plan to terminal state, respecting         prerequisit, CollectorOutcome, Typed outcome from a Collector execution. A successful empty result     is `suc, Any, Any, Any, Any, Any (+2 more)

### Community 36 - "Collection Window Model"
Cohesion: 0.20
Nodes (13): CollectionWindow, Region applicability rule for an Assessment Profile., Collection window definition (UTC-based)., RegionRule, Profile Release Rules — Additional unit tests complementing test_profile_registr, Tests that incompatible changes require a new major version., Create a base profile for incompatibility tests., Changing required capability list within same major → rejected. (+5 more)

### Community 37 - "Legacy Migration Tests"
Cohesion: 0.13
Nodes (17): MonkeyPatch, _client_error(), FakeGuardedSession, isolate_pricing_cache(), Any, ClientError, Systematic per-capability migration test matrix (Task 6.5).  For EVERY capabil, Sanity check on the data table itself before it drives the matrix below. (+9 more)

### Community 38 - "Capability Registry Tests"
Cohesion: 0.10
Nodes (11): Tests for manifest snapshot, canonical ordering, and digest., Empty registry returns manifest with no capabilities., Snapshot includes every registered capability., Capabilities are sorted by capability_id first., Same capability_id sorted by (major, minor, patch)., Canonical ordering is the same regardless of registration order., Same content always produces the same digest (Req 1.3)., Digest changes when registry content changes. (+3 more)

### Community 39 - "EC2 Collector Instance"
Cohesion: 0.11
Nodes (12): EC2InventoryCollector, Typed adapter for EC2 inventory collection.      Implements the Collector prot, collector(), No instances found returns succeeded with empty records tuple., Empty collection still produces evidence metadata., Generic exception produces failed outcome with StructuredError., Botocore ClientError produces StructuredError with correct code., Throttling errors are marked as retryable. (+4 more)

### Community 40 - "EC2 Filter Translation"
Cohesion: 0.11
Nodes (10): Translate capability-level filter parameters to DescribeInstances     server-si, _translate_filters(), instance_ids translates to instance-id filter., states translates to instance-state-name filter., vpc_ids translates to vpc-id filter., subnet_ids translates to subnet-id filter., availability_zones translates to availability-zone filter., tags translates to tag:<key> filters (AND across keys). (+2 more)

### Community 41 - "Capability Summary"
Cohesion: 0.16
Nodes (11): CapabilitySummary, Per-capability, per-target outcome count (Requirement 12.1). A     succeeded ca, Agentic AWS Assessment — Per-Capability Result Summary (Requirement 12).  One, Build one CapabilitySummary per (capability_id, account_id, region_scope)., summarize(), Tests for agentic.summary.summarize (Requirement 12.1, 12.2).  Covers: - Mixe, Status classification per (capability, account, region) row., A failed unit with no error attached still maps to 'failed'. (+3 more)

### Community 42 - "Execution Plan & Deterministic Planning"
Cohesion: 0.17
Nodes (16): ExecutionPlan, Immutable ordered Execution Plan. Contains no session, secret,     timestamp, o, _build_registry(), _compute_transitive_closure(), deterministic_planning_inputs(), FakeCollector, _generate_valid_registration_order(), Any (+8 more)

### Community 43 - "Guarded Session Identity"
Cohesion: 0.15
Nodes (11): Identity metadata for Evidence and security audit.      Contains account conte, Return identity metadata for Evidence and audit., SessionIdentity, Tests for GuardedSessionImpl operation allowlist enforcement., Operations in the allowlist are dispatched through boto3., Operations NOT in the allowlist raise GuardViolationError., With an empty allowlist, ALL operations are blocked (fail closed)., GuardViolationError wraps a StructuredError with correct fields. (+3 more)

### Community 44 - "Session Factory"
Cohesion: 0.16
Nodes (11): Creates guarded sessions per account. Uses ambient SDK credential     resolutio, SessionFactoryImpl, Tests for SessionFactoryImpl credential handling and session creation., Ambient credential session uses default boto3 session (no role_ref)., Cross-account targets use STS AssumeRole with deterministic session name., External ID presence is recorded as boolean, value is NOT stored., When no external_id_supplier is provided, flag is False., SessionFactoryImpl does not store raw credentials in any attribute. (+3 more)

### Community 45 - "Schema Processor Tests A"
Cohesion: 0.11
Nodes (10): Tests for canonical JSON serialization., Req 3.4: Sorted object keys., Req 3.4: Compact separators (no spaces)., Req 3.4: No trailing newline., NaN rejected during serialization., Infinity rejected during serialization., Req 11.4: Credential fields raise during serialization., Req 3.4: UTC timestamps normalized. (+2 more)

### Community 46 - "Capability Descriptor"
Cohesion: 0.18
Nodes (12): CapabilityDescriptor, Frozen capability descriptor within the registry.     Registration is startup-t, FakeCollector, Tests for region discovery snapshot persistence (Req 6.2)., Region discovery snapshot is stored in the plan., Snapshot keys and values are sorted., Without discovered_regions, snapshot is empty., A minimal Collector implementation for testing. (+4 more)

### Community 47 - "Collector Interfaces"
Cohesion: 0.14
Nodes (9): Any, Execute collection for one capability against one target.         Returns struc, Execute an AWS SDK operation only if it appears in the allowlist.         Unkno, Validates, parses, serializes, and canonicalizes payloads against     versioned, Validate payload against the declared schema version., Serialize a valid payload as deterministic Canonical JSON bytes., Parse serialized Canonical JSON back into a mapping., Resolve a registered capability by ID and version.         Returns the register (+1 more)

### Community 48 - "History Store Interface"
Cohesion: 0.17
Nodes (10): HistoryStore, Durable assessment history with indexed querying and retention., Persist a terminal run as one indexed history entry., Query history entries with AND-combined filters.         Order by (collection_t, Retrieve a persisted result whose digest matches the stored digest., HistoryEntry, InvocationResult, Versioned Invocation Result payload containing status, data,     error, Evidenc (+2 more)

### Community 49 - "Execution Unit & Concurrency"
Cohesion: 0.17
Nodes (14): ExecutionUnit, One identifiable work item: one Capability against one Target Pair., FakeSessionFactory, finite_plan_and_limits(), _make_plan(), _make_unit(), Any, DrawFn (+6 more)

### Community 50 - "Schema Canonical Bytes"
Cohesion: 0.19
Nodes (9): Any, Serialize a valid payload as Canonical JSON bytes (Req 3.4).          Canonica, Parse Canonical JSON bytes back into a mapping (Req 3.5).         Verifies sche, Compute SHA-256 hex digest over canonical bytes., Recursively check for raw credential field names., Recursively check for NaN/Infinity float values., Create a safe error message from a jsonschema ValidationError.     Avoids expos, Validate payload against the declared schema version.         Accumulates ALL v (+1 more)

### Community 51 - "EC2 Integration Fakes"
Cohesion: 0.16
Nodes (9): Zero instances = succeeded, not failed., Empty paginator result returns CollectorOutcome(status='succeeded')., Evidence metadata is created even for empty results., Invalid input stops before paginator — session/client never called., Unsupported filter key causes failure before SDK call., Unsupported field name causes failure before SDK call., Unsupported resource_type causes failure before SDK call., TestSuccessfulEmptyOutcomeIntegration (+1 more)

### Community 52 - "Schema Package Init"
Cohesion: 0.21
Nodes (12): Agentic AWS Assessment — Schema Catalog and Canonical JSON Processor.  Provide, _normalize_decimal(), _normalize_timestamp(), _normalize_timestamp_str(), _normalize_value(), datetime, Decimal, Canonical Schema Processor — validates, serializes, parses payloads.  Implemen (+4 more)

### Community 53 - "Session Build & Name"
Cohesion: 0.19
Nodes (9): _build_session_name(), Generate a deterministic, bounded session name for STS AssumeRole.      Format, Tests for deterministic, bounded session name generation., Same run_id and account_id always produce the same session name., Session name follows agentic-{run_id[:8]}-{account_id[:8]} format., Session name never exceeds 64 characters (STS limit)., Short run_id and account_id still produce valid names., Session name uses exactly first 8 chars of each input. (+1 more)

### Community 54 - "Report Template Scripts"
Cohesion: 0.27
Nodes (13): buildDynamicMenu(), createDots(), filterByCategory(), getServiceCategory(), makeSortable(), paginationStates, renderPaginationLinks(), resetFilters() (+5 more)

### Community 55 - "Profile Release Rules Tests A"
Cohesion: 0.22
Nodes (8): Tests that draft profiles cannot be used for monthly-assessment., Create a simple draft profile for activation tests., Create an InvocationRequest in profile mode., Create a capability registry with the ec2.inventory capability registered., Draft profile with purpose=monthly-assessment returns failed status., Draft profile with purpose='' succeeds if all capabilities registered., The actual monthly-standard@1.0.0 draft profile fails for monthly-assessment., TestDraftProfileActivation

### Community 56 - "EC2 Reference Property Tests"
Cohesion: 0.24
Nodes (13): _make_mock_session(), Any, Simple reference normalization matching the collector's logic., Simple reference filter predicate.     AND across categories, OR within lists,, Simple reference field projection.     If requested_fields is None/empty, inclu, Reference model implementation:     1. Collect all instances from all pages, Create a mock boto3 session that returns the generated pages., Property 5: EC2 inventory matches the reference model.      **Validates: Requi (+5 more)

### Community 57 - "Schema Processor Tests B"
Cohesion: 0.14
Nodes (8): Tests for payload validation against schema., Req 3.2: Valid payload passes validation., Req 3.3: Return EVERY detected violation., Req 3.3: Each violation has json_path, constraint, safe_message., Req 2.5: Unknown version returns violation., NaN values are rejected during validation., Infinity values are rejected during validation., TestValidation

### Community 58 - "Interactive Utils"
Cohesion: 0.20
Nodes (13): _build_service_table(), _confirm(), _mask(), _print_service_table(), _prompt(), Interactive setup wizard untuk AWS Assessment Tool. Menggunakan input() standar, Cetak tabel service dengan marker [x]/[ ]., Jalankan interactive setup wizard di terminal.      Return dict:         { (+5 more)

### Community 59 - "Assessment Engine Core"
Cohesion: 0.21
Nodes (6): AssessmentEngine, Initialize AWS Assessment.          Nilai bisa datang dari 2 sumber (prioritas a, Validasi AWS credentials dan permissions, Save assessment data ke JSON file, DecimalEncoder, Helper untuk encode Decimal ke JSON

### Community 60 - "Schema Processor Tests C"
Cohesion: 0.17
Nodes (7): Tests for raw credential field rejection., Req 11.4: Raw access_key is rejected., Req 11.4: Raw secret_key is rejected., Req 11.4: Raw password is rejected., Null credential references are acceptable (Req 11.4)., Req 11.4: Nested credential fields are also rejected., TestCredentialRejection

### Community 61 - "Assessment Run & Reports"
Cohesion: 0.22
Nodes (8): AWSAssessment, main(), Mendelegasikan pembuatan laporan ke modul reporter, Main Entry Point.     Pemilihan services wajib lewat interactive terminal — tid, Orchestrator untuk AWS Assessment.     Mewarisi AssessmentEngine untuk manajeme, Jalankan alur kerja assessment secara lengkap.         selected_services: list, get_billing_data(), Ambil data billing satu bulan terakhir dari Cost Explorer

### Community 62 - "EC2 Reference Scenarios"
Cohesion: 0.25
Nodes (11): ec2_instance(), ec2_test_scenario(), field_projection(), filter_combination(), paginated_responses(), DrawFn, Generate 1-5 pages, each with 0-10 instances., Generate a random subset of supported filters derived from instance data. (+3 more)

### Community 63 - "Legacy Contracts"
Cohesion: 0.24
Nodes (7): build_legacy_descriptor(), LegacyCapabilitySpec, Build the CapabilityDescriptor for one legacy capability spec.      permission, One legacy capability's identity, scope, and read-only allowlist., NamedTuple, Checks on the CapabilityDescriptor built from a spec., TestLegacyDescriptor

### Community 64 - "SemVer Parsing"
Cohesion: 0.20
Nodes (3): Parse a 'major.minor.patch' string into a SemVer instance., Check if two versions are major-compatible.         Returns True if they share, Discover and load all schema files under the schemas directory.

### Community 65 - "README Concepts"
Cohesion: 0.22
Nodes (10): Agentic Mode (AI Agent), AWS Account Assessment Tool, Bounded Concurrent Executor, Canonical Schema Processor, Capability Registry, GuardedSession (Read-Only Guard), Interactive Mode (Wizard), Multi-Account Multi-Region Support (+2 more)

### Community 66 - "Foundation Contract Tests B"
Cohesion: 0.20
Nodes (6): Schema version compatibility checks via the processor., Same major version (1.0.0 -> 1.2.0) is compatible., Different major version (1.0.0 -> 2.0.0) is incompatible., Same exact version (1.0.0 -> 1.0.0) is compatible., Minor and patch changes within same major are compatible., TestSchemaVersionCompatibility

### Community 67 - "Orchestrator Profile Tests B"
Cohesion: 0.22
Nodes (7): _make_explicit_capability_request(), Create a valid explicit capability mode request., Ensure explicit capability mode still works correctly., Explicit capability mode still works with profile_registry param., Explicit mode works even when no profile_registry is provided., Explicit mode still rejects unsupported capabilities., TestExplicitModeNoRegression

### Community 68 - "Schema Processor Test Setup"
Cohesion: 0.20
Nodes (7): catalog(), processor(), Tests for Schema Catalog and Canonical JSON Processor.  Validates Requirements, Tests for version compatibility checking., Req 3.6: Same major version is compatible., Req 3.6: Different major version is incompatible., TestVersionCompatibility

### Community 69 - "Session Factory Tests"
Cohesion: 0.20
Nodes (9): allowed_ops(), cross_account_identity(), mock_boto3_session(), Tests for SessionFactoryImpl and GuardedSessionImpl.  Covers: - Ambient crede, Standard set of allowed operations for tests., A mock boto3 session for testing without AWS access., A sample identity for ambient session tests., A sample identity for cross-account session tests. (+1 more)

### Community 70 - "Evidence Store Interface"
Cohesion: 0.22
Nodes (5): EvidenceStore, Persists and retrieves Evidence with integrity verification., Store evidence records for a unit within a run., Retrieve evidence for a unit. Returns content with verifiable digest., Verify content digests match stored evidence for a run.

### Community 71 - "Guarded Session Init"
Cohesion: 0.29
Nodes (4): Create a guarded session for the specified account target.         Uses ambient, Create a session using ambient SDK credentials (no AssumeRole)., Create a session using STS AssumeRole for cross-account access.          The r, Session

### Community 72 - "Legacy Contracts Tests"
Cohesion: 0.25
Nodes (3): allowed_operations must exactly match what collectors/*.py calls today., Structural checks on the spec table itself., TestLegacyCapabilitySpecs

### Community 73 - "Planner Tests Rationale"
Cohesion: 0.25
Nodes (5): Tests for _normalize_global_targets., Each unique account gets exactly one 'aws-global' entry., Duplicate accounts produce only one 'aws-global' entry., Output is sorted by account_id., TestNormalizeGlobalTargets

### Community 74 - "Profile Release Rules Tests B"
Cohesion: 0.25
Nodes (5): Verify resolving the published profile returns equivalent content., Verify the profile content digest is stable across multiple calls., Tests that profile publication is deterministic., Publish the same profile to two independent registries and verify same digest., TestDeterministicArtifact

### Community 75 - "Profile Release Rules Tests C"
Cohesion: 0.25
Nodes (5): Tests for schema version metadata requirements., Verify that published profile has schema_id set., Verify that published profile has schema_version set., Verify schema_id and schema_version are both non-empty strings., TestProfileSchemaRequirements

### Community 76 - "Schema Processor Tests D"
Cohesion: 0.25
Nodes (5): Tests for parsing and round-trip byte equivalence., Parse returns a valid mapping., Req 3.5: parse(canonical_bytes(x)) -> re-serialize produces same bytes., Parse rejects unknown schema., TestParseAndRoundTrip

### Community 77 - "Schema Processor Tests E"
Cohesion: 0.25
Nodes (5): Tests for SHA-256 digest computation., Digest returns a hex string., Same payload always produces same digest., Different payloads produce different digests., TestDigest

### Community 78 - "Session Factory Tests B"
Cohesion: 0.25
Nodes (5): Tests for the SessionIdentity dataclass., SessionIdentity is immutable., SessionIdentity defaults match the no-cross-account case., SessionIdentity can hold cross-account metadata., TestSessionIdentity

### Community 79 - "Guard Violation Error"
Cohesion: 0.29
Nodes (4): Any, Execute an AWS SDK operation only if it appears in the allowlist.         Unkno, Initialize SessionFactory.          Args:             run_id: The assessment, _xform_operation_name()

### Community 80 - "Database Collectors"
Cohesion: 0.29
Nodes (6): inventory_dynamodb(), inventory_elasticache(), inventory_rds(), Inventory RDS instances, Inventory DynamoDB tables, Inventory ElastiCache clusters

### Community 81 - "Report Pipeline (Docs)"
Cohesion: 0.29
Nodes (7): Cost Optimization Analysis, playwright Dependency, Report Template HTML, Chart.js Integration, Cost Optimization Section, Executive Summary Section, Services Inventory Section

### Community 82 - "EBS/NAT Legacy Collectors"
Cohesion: 0.33
Nodes (6): collect_ebs_inventory(), collect_nat_inventory(), _paginate_next_token(), Migrated from `collectors/storage.py::inventory_ebs()`., Migrated from `collectors/network.py::inventory_nat_gateway()`., Flat NextToken-style pagination (ec2 describe_* operations).

### Community 83 - "Registry Digest & Discovery"
Cohesion: 0.33
Nodes (3): Return the current immutable manifest snapshot with digest.         Canonical o, Return the machine-readable manifest without creating AWS sessions.         Ide, Compute SHA-256 digest over canonical JSON representation of the manifest.

### Community 84 - "Compute Collector Tests"
Cohesion: 0.33
Nodes (6): ec2_instance_strategy(), Generate a single AWS tag {Key: ..., Value: ...}, Generate tag lists specifically designed to test environment priority logic., Generate random EC2 instance dicts with varying optional fields., tag_combination_strategy(), tag_entry_strategy()

### Community 85 - "EC2 Integration Rationale"
Cohesion: 0.33
Nodes (4): Verify combined filters reach paginator correctly., states + vpc_ids + tags all reach the paginator as proper Filters., Multiple tag keys each become separate Filter entries (AND semantics)., TestFilterTranslationIntegration

### Community 86 - "Executor Exception Tests"
Cohesion: 0.33
Nodes (5): _exception_collector(), _failure_collector(), Any, Collector that always raises an exception., Collector that always returns failed status.

### Community 87 - "Registry Cycle Detection"
Cohesion: 0.40
Nodes (3): Any, Check if adding new_cap_id with the given prerequisites would         create a, Register a capability with its handler.          Validates:         - Handler

### Community 88 - "EC2 Collector Edge Cases"
Cohesion: 0.40
Nodes (3): datetime, UTC datetime converts to RFC 3339 with Z., Naive datetime (no tzinfo) is treated as UTC.

### Community 89 - "Legacy Adapter Regression"
Cohesion: 0.50
Nodes (3): _FakeBotoSession, Any, Minimal boto3.session.Session stand-in: `.client()` always returns the     same

### Community 91 - "Readiness Handler"
Cohesion: 0.67
Nodes (3): _handler_is_interactive(), Any, Scan the handler's `collect` source for a literal `input(` call.

## Knowledge Gaps
- **14 isolated node(s):** `paginationStates`, `Interactive Mode (Wizard)`, `Capability Registry`, `Bounded Concurrent Executor`, `Multi-Account Multi-Region Support` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StructuredError` connect `Structured Errors` to `Capability Manifest & Models`, `Legacy Collectors`, `EC2 Contract & Adapter`, `Profile Registry`, `Assessment Profiles`, `Execution Context & Orchestration`, `EC2 Contract Validation`, `Orchestrator Planning`, `Profile Interfaces`, `Orchestrator Tests`, `Agentic Interfaces`, `Schema Catalog`, `Legacy S3/VPC/Backup Collectors`, `Foundation Contract Tests`, `Evidence & Resource Records`, `Orchestrator Profile Tests`, `Bounded Executor`, `Legacy Record Collector`, `Core Models`, `EC2 Integration Tests`, `SemVer Model`, `EC2 Inventory Collector`, `Legacy Adapter`, `Executor Aggregation`, `Executor Status Aggregation`, `Executor Execution`, `Collection Window Model`, `Legacy Migration Tests`, `Capability Registry Tests`, `EC2 Collector Instance`, `Capability Summary`, `Guarded Session Identity`, `Session Factory`, `History Store Interface`, `EC2 Integration Fakes`, `Session Build & Name`, `Profile Release Rules Tests A`, `Foundation Contract Tests B`, `Orchestrator Profile Tests B`, `Session Factory Tests`, `Profile Release Rules Tests B`, `Profile Release Rules Tests C`, `Session Factory Tests B`, `Guard Violation Error`, `EC2 Integration Rationale`, `Executor Exception Tests`, `Schema Catalog Versions`, `Profile Publication Error`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Why does `CanonicalSchemaProcessor` connect `Schema Processor` to `Assessment Profiles`, `Execution Context & Orchestration`, `Orchestrator Planning`, `Planner Target Pairs`, `Orchestrator Tests`, `Schema Catalog`, `Foundation Contract Tests`, `Orchestrator Profile Tests`, `Core Models`, `EC2 Integration Tests`, `SemVer Model`, `Property Schema Roundtrip`, `Structured Errors`, `Legacy Adapter`, `Collection Window Model`, `Execution Plan & Deterministic Planning`, `Schema Processor Tests A`, `Capability Descriptor`, `Schema Canonical Bytes`, `EC2 Integration Fakes`, `Schema Package Init`, `Profile Release Rules Tests A`, `Schema Processor Tests B`, `Schema Processor Tests C`, `Foundation Contract Tests B`, `Orchestrator Profile Tests B`, `Schema Processor Test Setup`, `Planner Tests Rationale`, `Profile Release Rules Tests B`, `Profile Release Rules Tests C`, `Schema Processor Tests D`, `Schema Processor Tests E`, `EC2 Integration Rationale`, `Legacy Adapter Regression`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `EC2InventoryCollector` connect `EC2 Collector Instance` to `EC2 Contract & Adapter`, `Executor Execution`, `Execution Context & Orchestration`, `EC2 Collector Tests`, `Evidence & Resource Records`, `EC2 Integration Fakes`, `EC2 Integration Rationale`, `EC2 Reference Property Tests`, `EC2 Integration Tests`, `EC2 Inventory Collector`, `Structured Errors`, `Legacy Adapter`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Are the 104 inferred relationships involving `SemVer` (e.g. with `AssessmentProfileRegistry` and `CapabilityRegistry`) actually correct?**
  _`SemVer` has 104 INFERRED edges - model-reasoned connections that need verification._
- **Are the 136 inferred relationships involving `StructuredError` (e.g. with `EC2InventoryCollector` and `BoundedExecutor`) actually correct?**
  _`StructuredError` has 136 INFERRED edges - model-reasoned connections that need verification._
- **Are the 60 inferred relationships involving `CanonicalSchemaProcessor` (e.g. with `_ResolvedProfile` and `SchemaViolation`) actually correct?**
  _`CanonicalSchemaProcessor` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 75 inferred relationships involving `CapabilityRegistryImpl` (e.g. with `LegacyCapabilitySpec` and `_ResolvedProfile`) actually correct?**
  _`CapabilityRegistryImpl` has 75 INFERRED edges - model-reasoned connections that need verification._