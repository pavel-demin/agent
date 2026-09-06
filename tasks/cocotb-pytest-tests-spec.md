# Planning the implementation of unit tests for Verilog modules

## Objective

Create a detailed implementation plan (task file) that will guide subsequent agents in developing a comprehensive set of verification tools for all Verilog modules found in `red-pitaya-notes/cores/` and `red-pitaya-notes/modules/`.

Note: The goal is to define instructions for the implementation process, not to perform the task itself.

## Environment & structure

Project directory structure:
- Verilog modules: `red-pitaya-notes/cores/` and `red-pitaya-notes/modules/`
- Reference models: `red-pitaya-notes/models/` (specifically for `dds` and `axis_iir_filter`)
- Test suite: `red-pitaya-notes/tests/`
- Project context: `red-pitaya-notes/projects/`

Dependencies can be found in the following directories and files:
- `/opt/Xilinx/2025.2/data/verilog/src/unisims`
- `/opt/Xilinx/2025.2/data/ip/xpm/xpm_fifo/hdl/xpm_fifo.sv`
- `/opt/Xilinx/2025.2/data/ip/xpm/xpm_memory/hdl/xpm_memory.sv`
- `/opt/Xilinx/2025.2/data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv`

Test organization:
- File naming: Each Verilog module must have a corresponding Python test file (`<module_name>.py`).
- Entry point: One central `test_modules.py` file must manage `pytest` discovery and execution.
- Execution command: `cd red-pitaya-notes/tests && pytest`

## Implementation requirements

Protocol compliance: Testbenches testing AXI4, AXI4-Lite and AXI4-Stream interfaces must use only protocol-compliant transactions.

Bug detection protocol: Tests must be designed to detect existing bugs and anomalies rather than adapting to them. All discovered issues must be documented in `red-pitaya-notes/tests/ISSUES.md` for subsequent resolution.

## Technical standards

- Testing framework: `cocotb` for testbench logic and `pytest` as the runner
- Formatting: Black (`--line-length 120`)
- Static analysis: Ruff (`--line-length 120 --fix`)

## Cocotb 2.0.1 technical notes

- Runner API: Use `from cocotb_tools.runner import get_runner`.
- Waveforms: Generate via `build(waves=True)` and `test(waves=True)`. Output is located at `sim_build/<top>.fst`.
