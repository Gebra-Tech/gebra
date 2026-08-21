"""``python -m gebra.cli`` — the module-runner spelling of the ``gebra`` console script."""

import sys

from gebra.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
