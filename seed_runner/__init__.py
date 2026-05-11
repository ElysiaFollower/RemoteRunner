"""
Remote Runner prototype package initialization.

The Python package is still named ``seed_runner`` while the project migrates from
the SEEDRunner prototype toward the broader Remote Runner product boundary.
"""

__version__ = "0.1.0"
__author__ = "Remote Runner Team"

from seed_runner.config import ConfigManager, get_config_manager, get_machine_config

__all__ = [
    "ConfigManager",
    "get_config_manager",
    "get_machine_config",
]
