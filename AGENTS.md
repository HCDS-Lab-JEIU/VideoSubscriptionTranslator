# Python environment

Use the Miniconda environment `translator` for all Python execution, tests,
dependency checks, and package management in this project.

- Python interpreter: `D:\Miniconda3\envs\translator\python.exe`
- Do not use `.venv`, the Miniconda base environment, or an unqualified `python`
  or `pip` command that could resolve to another environment.
- Prefer explicit PowerShell commands:

  ```powershell
  & 'D:\Miniconda3\envs\translator\python.exe' __main__.py --help
  & 'D:\Miniconda3\envs\translator\python.exe' -m unittest discover -s tests -v
  & 'D:\Miniconda3\envs\translator\python.exe' -m pip --version
  ```

- If Conda activation is needed for native dependencies, use
  `conda run --no-capture-output -n translator python ...`.
- Keep README execution examples aligned with the `translator` environment.
- If this environment is unavailable, report that rather than silently using
  another interpreter or creating a new virtual environment.
