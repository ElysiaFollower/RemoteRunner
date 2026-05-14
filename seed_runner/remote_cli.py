"""Legacy compatibility wrapper for the target Remote Runner CLI."""

from remote_runner.cli import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
