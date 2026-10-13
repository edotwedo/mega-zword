"""`python -m megazword` runs the same CLI as `megazword`."""

import sys

from .cli import main

sys.exit(main())
