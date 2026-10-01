"""Portable skill collections from installed Python package resources."""

import asyncio
import re
from importlib.metadata import entry_points
from importlib.resources import files
from pathlib import Path, PurePosixPath

from psmcp_router_developer_tools.models import Skill
from psmcp_router_developer_tools.parsing import parse_skill_file


class PackageSkillSource:
    """Read packaged Markdown without depending on an editable checkout."""

    def __init__(self, package: str, path: str):
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", package):
            raise ValueError("Invalid skill package name")
        self.package = package
        self.router_package = next(
            (
                ep.value.split(":")[0].split(".")[0]
                for ep in entry_points(group="psmcp.routers")
                if package == ep.value.split(":")[0].split(".")[0]
                or package.startswith(ep.value.split(":")[0].split(".")[0] + ".")
            ),
            None,
        )
        self._parts(path)
        self._root = files(package).joinpath(*PurePosixPath(path).parts)
        if not self._root.is_dir():
            raise FileNotFoundError(f"Skill package directory does not exist: {package}:{path}")
        self._source_id = f"package:{package}/{path}"
        if isinstance(self._root, Path):
            package_root = files(package)
            if not self._root.resolve().is_relative_to(package_root.resolve()):
                raise ValueError("Skill package directory escapes its package")

    @staticmethod
    def _parts(path: str) -> tuple[str, ...]:
        if (
            not path
            or any(char in path for char in ("\\", ":", "%"))
            or PurePosixPath(path).is_absolute()
            or any(part.startswith(".") for part in path.split("/"))
        ):
            raise ValueError("Unsafe package resource path")
        return PurePosixPath(path).parts

    @property
    def source_id(self) -> str:
        """Return the stable package source identity."""
        return self._source_id

    async def load_skills(self) -> list[Skill]:
        """Discover packaged skills recursively, excluding hidden directories."""
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> list[Skill]:
        skills = []

        def visit(directory, prefix: str = "") -> None:
            for item in sorted(directory.iterdir(), key=lambda item: item.name):
                if item.name.startswith("."):
                    continue
                relative = f"{prefix}{item.name}"
                if isinstance(item, Path) and not item.resolve().is_relative_to(
                    self._root.resolve()
                ):
                    raise ValueError(f"Package skill resource escapes source: {relative}")
                if item.is_dir():
                    visit(item, f"{relative}/")
                elif item.name.endswith(".md"):
                    skill = parse_skill_file(
                        item.read_text(encoding="utf-8"), relative, self.source_id
                    )
                    if skill is not None:
                        skills.append(skill)

        visit(self._root)
        return skills

    async def read_file(self, relative_path: str) -> str | None:
        """Read a contained text resource, returning None for a missing file."""
        target = self._root.joinpath(*self._parts(relative_path))
        if isinstance(target, Path) and not target.resolve().is_relative_to(self._root.resolve()):
            raise ValueError("Package skill reference escapes source")
        if not target.is_file():
            return None
        return await asyncio.to_thread(target.read_text, encoding="utf-8")

    def validate_reference(self, skill_file_path: str, reference_path: str) -> None:
        """Enforce per-document containment for filesystem-backed package resources."""
        if isinstance(self._root, Path):
            directory = (self._root / skill_file_path).parent.resolve()
            if not (self._root / reference_path).resolve().is_relative_to(directory):
                raise ValueError("Package skill reference escapes its document directory")
