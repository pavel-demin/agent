# Planning the specification set for a test suite

## Objective

The objective of this task is to initiate the planning of a comprehensive test suite for all Verilog modules located in `red-pitaya-notes/cores/` and `red-pitaya-notes/modules/`.

This file is the planning input that guides the creation of a task file, which describes the work required to produce the specification set in `red-pitaya-notes/tasks/`: the work specifications and their corresponding V&V specifications (`tests-*-spec.md`), together with the common conventions document (`tests-common.md`).

The specification set follows the V-model described in `v-model.md` at the workspace root and establishes traceability between each work specification and its corresponding V&V specification. It is complete and unambiguous: a planning agent reading only the set can explicitly determine the deliverables, prerequisites, and completion conditions for every work plan, and the order in which the work is to be executed and the dependencies between the work plans.

The "System" level of the V-model corresponds to the test suite, and the "Architecture" level corresponds to the architecture of the test suite.

This file states only the essential requirements. Every detail not stated here - suite layout, per-file content beyond what this file requires, workflow, and governance - is defined by the planning agent in the task file and, where the task file deliberately leaves implementation choices open, by the executing agents.

## Deliverables

The deliverable of the initial planning task, performed by the planning agent that reads this file, is the task file.

## Inputs

- Project tree: `red-pitaya-notes/cores/` and `red-pitaya-notes/modules/` (Verilog modules under test), `red-pitaya-notes/projects/` (use cases describing expected behavior).
- Toolchain: cocotb 2.1 (pytest plugin), Icarus Verilog 12.0, Xilinx unisims and `glbl.v` under `/opt/Xilinx/2025.2/data/verilog/src/`, and the XPM sources (SystemVerilog, one consolidated file per package) under `/opt/Xilinx/2025.2/data/ip/xpm/` (`xpm_cdc/hdl/xpm_cdc.sv`, `xpm_fifo/hdl/xpm_fifo.sv`, `xpm_memory/hdl/xpm_memory.sv`).
- Facts: Icarus 12.0 does not parse the consolidated `xpm_cdc.sv` and `xpm_fifo.sv` as a whole; the concurrent assertions in all three files require `-gno-assertions`; the consolidated `xpm_memory.sv` parses as a whole with `-DOBSOLETE`.
- Verified: the XPM instances used by the in-scope RTL compile from extracted sources with `iverilog -g2012 -DOBSOLETE -gno-assertions`, each extracted with its file preamble and its module dependencies.
- Test runner: tests are ordinary pytest tests, and the cocotb 2.1 pytest plugin must be enabled by `addopts = -p cocotb_tools._pytest.plugin --cocotb-simulator icarus` in `red-pitaya-notes/pytest.ini`. The plugin is documented in `cocotb/docs/source/pytest_plugin.rst`; the cocotb source tree is checked out at the workspace root as `cocotb/`, a sibling of `red-pitaya-notes/`.
- Reference models: `red-pitaya-notes/models/` contains existing mathematical (non-cycle-accurate) models: `dds-model.py` for the `dds` module and `iir-model.c` for `axis_iir_filter`. They are complementary functional references for expected behavior, not cycle-accurate models.

## Essential requirements

- Scope: `.v`/`.sv` files under `red-pitaya-notes/cores/` and `red-pitaya-notes/modules/`.
- Reuse: modules with similar interfaces or subsystems must be tested with maximum reuse of shared Python helpers (helper modules, helper classes, helper functions), pytest fixtures, and the other useful features of cocotb and pytest.
- Structure: the overall structure of the test suite must comply with established best practices for software structuring.
- Efficiency: the test suite must maximize the ratio of functional coverage achieved to suite complexity (the Icarus toolchain provides no RTL code coverage, so coverage here means verified functional behavior).
- Models: a cycle-accurate Python model must be developed for each Verilog module defined in an in-scope file, and the RTL must be verified against it cycle by cycle. The mathematical (non-cycle-accurate) models in `red-pitaya-notes/models/` must be ported to the test suite and used for additional tests of the corresponding modules.
- XPM: the XPM instances of the in-scope modules that use them must be simulated against the shipped XPM sources per the toolchain note, not against hand-written substitutes; any XPM instance that cannot be simulated that way is an open problem to be documented per the defect-detection rule.
- Protocol compliance: unit tests targeting AXI4, AXI4-Lite, and AXI4-Stream interfaces must use only protocol-compliant transactions.
- Concurrent stimulation: unit tests must simulate simultaneous read and write transactions, both within individual AXI4 interfaces and across multiple interfaces, to verify that the module handles concurrent channel activity without deadlock or data corruption.
- Python code: the Python code produced by the agents must not include local imports, type annotations, docstrings, or comments.
- Code style consistency: consistent naming conventions and structural patterns across all Python files, classes, functions, tests, and variables must be maintained.
- Text verification: all text deliverables (excluding source code) must be independently, meticulously, and critically reviewed by an agent who authored none of the content. Any logical or stylistic inconsistencies, ambiguities, contradictions, or omissions relative to the specifications and this file must be corrected and reviewed again until none remain.
- Command execution: all commands must be executed from the workspace root in the form `cd red-pitaya-notes && <command>`.
- Defect detection: the tests must be designed to detect existing bugs and anomalies in the RTL, not to adapt to them - buggy behavior must never be encoded as an expected value. Every problem discovered must be documented with the evidence needed to triage it (expected versus observed, log or waveform path).
- Schedulability: the set must be the planning input for a planning agent that plans the work the set specifies. Each specification file must state explicitly, rather than merely make derivable, the deliverables, prerequisites, and completion conditions of the work it specifies. The set must also state explicitly the order in which the work is to be executed and the dependencies between the works (which work consumes which deliverables of which other work), so that an orchestrator can derive from the set alone a dispatch sequence in which every work's prerequisites are satisfied before that work starts; the prerequisites of each specification file must cover every deliverable of another work that the work it specifies consumes.
- Verification of claims: every environment-dependent claim of the set (in-scope inventory, per-module XPM and unisim usage, source extraction ranges and their line boundaries, toolchain versions and paths, and compile facts) must be verified dynamically in this workspace by the planning agent before the set is complete, and the verifying command and its exact summary line must be recorded in the session notes.

## Completion

- The task file is complete when it fully specifies the work required to produce the specification set, including the acceptance criteria by which that work is judged complete.
- The work is complete when the specification set exists in the `red-pitaya-notes/tasks/` directory, its specification files follow the V-model, with each work specification paired with its corresponding V&V specification and the pairs arranged in the appropriate sequence, and when the set satisfies all essential requirements, including that each specification file states its deliverables explicitly, that the conventions document carries the deliverables-to-ownership mapping, that every environment-dependent claim is verified as required, that all text deliverables have been independently reviewed, and that the final set is fully schedulable (it states the work execution order and the dependencies between the works, and the prerequisites of every work cover the deliverables of the other works it consumes).

## Requirements for specification files and the common conventions document

The specification set must meet the following requirements:
- There must be at least one work specification file and one V&V specification file at each level of the V-model.
- Each specification file must state that its task is to develop a detailed implementation plan, provided as a task file, to guide subsequent agents.
- Each specification file must state that the subsequent planning agent that reads it is responsible for defining instructions for the implementation process, not for carrying out the implementation itself.
- The primary deliverable defined by each specification file must be the task file produced by the subsequent planning agent that reads that specification file. The task file is intended to guide subsequent executing agents. Its name must not be specified; the agent harness automatically adds the task file name to the specification file.
- All other deliverables defined by each specification file must be produced by subsequent executing agents that read the task file produced by the subsequent planning agent. These deliverables must be located either in the `red-pitaya-notes/pytest.ini` file or in the `red-pitaya-notes/tests/` directory and its subdirectories.
- Each specification file must contain a dedicated deliverables section that enumerates every deliverable of the work it specifies other than its task file. For each deliverable, the section must state its name (where the name is a deliberately open choice, the section marks it open, and the committed location identifies the deliverable), its location, the requirement of that specification that defines it, and whether it is a deliverable or a transient run-time artifact that is exempt from the location constraint of the previous item.
- The common conventions document must contain a consolidated ownership mapping. For every deliverable committed by the specification set (including task files and all enumerated deliverables), the map must specify the owning specification file, the defining requirement, and the location. Similarly, all exempted transient artifacts must be recorded alongside the specification and requirement that exempt them.
- Neither the specification files nor the common conventions document may include information from the "Task file specifications" section below. That section is automatically added to the specification files by the agent harness.
