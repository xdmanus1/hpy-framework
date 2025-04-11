#!/usr/bin/env python3
"""HPY Tool entry point."""

import sys

# Import the main function from the package's cli module
from hpy_core.cli import main

if __name__ == "__main__":
    # Execute the main function, allowing it to handle sys.exit
    main()