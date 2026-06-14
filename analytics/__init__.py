"""
Automated Soccer Tracking and Drone Analytics Pipeline - Statistical Analysis Skills
analytics/__init__.py

This initialization file defines the registration interface that allows developers
and AI agents to write and register new downstream analytical skills dynamically
without altering the core codebase.
"""

import importlib
import logging
import pkgutil
from typing import Callable, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

# Global registry for analytics skills
SKILL_REGISTRY: Dict[str, Callable] = {}

def register_skill(name: str):
    """
    Decorator to dynamically register analytical skills.

    Args:
        name (str): The unique string key for the skill (e.g. 'possession', 'pass_network').
    """
    def decorator(func_or_class: Callable) -> Callable:
        SKILL_REGISTRY[name] = func_or_class
        logger.info(f"Successfully registered analytics skill: '{name}'")
        return func_or_class
    return decorator

def get_skill(name: str) -> Callable:
    """
    Retrieves a registered skill by its registered name.

    Args:
        name (str): Key of the skill.

    Returns:
        Callable: The registered function or class.
    """
    if name not in SKILL_REGISTRY:
        raise KeyError(
            f"Analytics skill '{name}' is not registered. "
            f"Currently registered skills: {list(SKILL_REGISTRY.keys())}"
        )
    return SKILL_REGISTRY[name]

# Autodiscovery implementation: Automatically scan the analytics directory and 
# import all submodules so that the @register_skill decorators execute.
def discover_skills(package_path: Any, package_name: str) -> None:
    """
    Walks package modules and imports them to trigger registrations.
    """
    for _, module_name, _ in pkgutil.walk_packages(package_path, package_name + "."):
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.error(f"Failed to dynamically load analytics module {module_name}: {e}")

# Run autodiscovery for this package
import sys
discover_skills(sys.modules[__name__].__path__, __name__)
