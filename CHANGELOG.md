# Change log

## `v3.0.1` - 2023-08-22

- `NwchemParser`: Do not except for missing output [[242b40c]](https://github.com/aiidateam/aiida-nwchem/commit/242b40c0f420153c86409fefe6f6970c6fcf3795)
- `NwchemParser`: Fix output from `parse_freq` not being attached [[3421c51]](https://github.com/aiidateam/aiida-nwchem/commit/3421c516265eb35dc905fd4c7b0023fe605a8389)


## `v3.0.0` - 2022-11-03

First release to be officially and fully compatible with AiiDA v2.0.

### Dependencies:

- Add support for `aiida-core~=2.0` [[faa7c115]](https://github.com/aiidateam/aiida-nwchem/commit/faa7c1158bae3b819a0c028a86a8ed5b0a61157f)
- Drop support for `aiida-core<2.0` [[faa7c115]](https://github.com/aiidateam/aiida-nwchem/commit/faa7c1158bae3b819a0c028a86a8ed5b0a61157f)
- Add support for Python 3.9 and 3.10 [[faa7c115]](https://github.com/aiidateam/aiida-nwchem/commit/faa7c1158bae3b819a0c028a86a8ed5b0a61157f)
- Drop support for Python 3.6 and 3.7 [[faa7c115]](https://github.com/aiidateam/aiida-nwchem/commit/faa7c1158bae3b819a0c028a86a8ed5b0a61157f)


## `v2.1.1` - 2022-11-03

This is the last release compatible with AiiDA `v1.x`.
This patch adds a continuous-integration workflow on Github Actions that runs pre-commit and the unit test suite.
The package structure is updated to be comformant to modern standards, such as adopting PEP 621 and moving build specifications to the `pyproject.toml` file.
