"""Run kitlint by path, like the other tools: python common/tools/kitlint.py KIT.3mf [options]."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kitlint.cli import main  # noqa: E402

sys.exit(main())
