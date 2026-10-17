#When you run a folder as a package with python -m, Python looks for __main__.py and runs it
from agentic_core.segmentation.cli import main

raise SystemExit(main())