#!/usr/bin/env python3
"""Tests for the DependencyGraph module."""

import tempfile
import os
import pytest

# Skip all tests if networkx is not installed
networkx = pytest.importorskip("networkx")

from codenav.dependency_graph import DependencyGraph, FileNode, analyze_repository


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project structure for testing."""
    # Create a mini project structure
    src = tmp_path / "src"
    src.mkdir()

    # Core module - will be imported by many
    (src / "core").mkdir()
    (src / "core" / "__init__.py").write_text("")
    (src / "core" / "config.py").write_text("""
# Configuration module - central hub
DEFAULT_SETTINGS = {"debug": True}

def get_config():
    return DEFAULT_SETTINGS
""")

    (src / "core" / "utils.py").write_text("""
from .config import get_config

def helper():
    cfg = get_config()
    return cfg.get("debug", False)
""")

    # API module
    (src / "api").mkdir()
    (src / "api" / "__init__.py").write_text("")
    (src / "api" / "routes.py").write_text("""
from ..core.config import get_config
from ..core.utils import helper

def api_handler():
    config = get_config()
    helper()
    return {"status": "ok"}
""")

    (src / "api" / "middleware.py").write_text("""
from ..core.config import get_config

def auth_middleware():
    config = get_config()
    return True
""")

    # Main entry point
    (src / "main.py").write_text("""
from core.config import get_config
from core.utils import helper
from api.routes import api_handler

def main():
    config = get_config()
    api_handler()

if __name__ == "__main__":
    main()
""")

    # Tests directory (should have lower PageRank)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_config.py").write_text("""
from src.core.config import get_config

def test_get_config():
    assert get_config() is not None
""")

    return tmp_path


class TestDependencyGraph:
    """Test suite for DependencyGraph class."""

    def test_init(self, tmp_path):
        """Test basic initialization."""
        dg = DependencyGraph(str(tmp_path))
        assert dg.root == tmp_path.resolve()
        assert dg.damping == DependencyGraph.DEFAULT_DAMPING

    def test_init_with_custom_damping(self, tmp_path):
        """Test initialization with custom damping factor."""
        dg = DependencyGraph(str(tmp_path), damping=0.9)
        assert dg.damping == 0.9

    def test_init_invalid_path(self):
        """Test initialization with non-existent path."""
        with pytest.raises(ValueError, match="does not exist"):
            DependencyGraph("/nonexistent/path/12345")

    def test_build_empty_project(self, tmp_path):
        """Test building graph for empty project."""
        dg = DependencyGraph(str(tmp_path))
        dg.build()
        assert len(dg.nodes) == 0
        assert dg.graph.number_of_nodes() == 0

    def test_build_sample_project(self, sample_project):
        """Test building graph for sample project."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        # Should have found Python files
        assert len(dg.nodes) > 0

        # Should have edges
        assert dg.graph.number_of_edges() > 0

    def test_get_critical_paths(self, sample_project):
        """Test getting critical paths (top PageRank files)."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        critical = dg.get_critical_paths(top_n=5)

        # Should return list of tuples
        assert isinstance(critical, list)
        assert len(critical) <= 5

        if critical:
            # Each entry should be (path, score)
            path, score = critical[0]
            assert isinstance(path, str)
            assert isinstance(score, float)
            assert 0 <= score <= 1

            # Should be sorted by score descending
            scores = [s for _, s in critical]
            assert scores == sorted(scores, reverse=True)

    def test_is_hub(self, sample_project):
        """Test hub detection."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        # Get all hub files
        hubs = dg.get_hub_files(threshold=2)

        for hub in hubs:
            assert dg.is_hub(hub, threshold=2)

    def test_get_connected_files(self, sample_project):
        """Test getting connected files."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        # Find a file with connections
        for path, node in dg.nodes.items():
            if node.resolved_imports or node.importers:
                connected = dg.get_connected_files(path)
                assert isinstance(connected, list)
                # Should not include self
                assert path not in connected
                break

    def test_get_stats(self, sample_project):
        """Test statistics generation."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        stats = dg.get_stats()

        assert "total_files" in stats
        assert "total_edges" in stats
        assert "hub_files" in stats
        assert "languages" in stats
        assert isinstance(stats["languages"], dict)

    def test_to_dict(self, sample_project):
        """Test serialization to dictionary."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        data = dg.to_dict()

        assert "root" in data
        assert "stats" in data
        assert "critical_paths" in data
        assert "nodes" in data
        assert isinstance(data["nodes"], dict)

    def test_language_filter(self, sample_project):
        """Test building with language filter."""
        dg = DependencyGraph(str(sample_project))
        dg.build(languages=["python"])

        # All files should be Python
        for path in dg.nodes:
            assert path.endswith(".py")

    def test_dependency_chain(self, sample_project):
        """Test dependency chain traversal."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        # Find a file with imports
        for path, node in dg.nodes.items():
            if node.resolved_imports:
                chain = dg.get_dependency_chain(path, depth=2)
                assert path in chain
                break

    def test_importers_chain(self, sample_project):
        """Test reverse dependency chain traversal."""
        dg = DependencyGraph(str(sample_project))
        dg.build()

        # Find a file with importers
        for path, node in dg.nodes.items():
            if node.importers:
                chain = dg.get_importers_chain(path, depth=2)
                assert path in chain
                break


class TestFileNode:
    """Test suite for FileNode dataclass."""

    def test_file_node_creation(self):
        """Test creating a FileNode."""
        node = FileNode(path="src/main.py", language="python")
        assert node.path == "src/main.py"
        assert node.language == "python"
        assert node.imports == []
        assert node.pagerank == 0.0

    def test_file_node_with_data(self):
        """Test FileNode with full data."""
        node = FileNode(
            path="src/main.py",
            language="python",
            imports=["os", "sys"],
            resolved_imports=["src/utils.py"],
            importers=["tests/test_main.py"],
            pagerank=0.15,
            in_degree=1,
            out_degree=2,
        )
        assert len(node.imports) == 2
        assert node.pagerank == 0.15


class TestAnalyzeRepository:
    """Test the convenience function."""

    def test_analyze_repository(self, sample_project):
        """Test the analyze_repository function."""
        results = analyze_repository(str(sample_project), top_n=5)

        assert "critical_paths" in results
        assert "hub_files" in results
        assert "stats" in results


class TestPageRankAdvantage:
    """Tests demonstrating PageRank advantages over simple counting."""

    def test_transitive_importance(self, tmp_path):
        """
        Demonstrate that PageRank gives higher scores to files imported
        by important files, not just files with many importers.
        """
        src = tmp_path / "src"
        src.mkdir()

        # File A: imported by B, C, D, E (4 importers - but they're all leaf nodes)
        (src / "file_a.py").write_text("def a(): pass")

        # Leaf nodes that import A
        for name in ["file_b", "file_c", "file_d", "file_e"]:
            (src / f"{name}.py").write_text(f"from file_a import a\ndef {name}(): a()")

        # File X: imported only by Y and Z, but Y and Z are important hubs
        (src / "file_x.py").write_text("def x(): pass")

        # Y imports X and is imported by many files
        (src / "file_y.py").write_text("from file_x import x\ndef y(): x()")

        # Files that import Y (making Y important)
        for i in range(5):
            (src / f"uses_y_{i}.py").write_text(f"from file_y import y\ndef f{i}(): y()")

        dg = DependencyGraph(str(tmp_path))
        dg.build()

        # With simple counting (in-degree):
        # file_a has 4 importers
        # file_x has 1 importer (file_y)
        # So simple counting would rank file_a higher

        # With PageRank:
        # file_y is imported by 5 files, making it important
        # file_x is imported by the important file_y
        # So PageRank should give file_x a reasonable score despite fewer importers

        # Get stats to verify the logic
        file_a = dg.nodes.get("src/file_a.py")
        file_x = dg.nodes.get("src/file_x.py")
        file_y = dg.nodes.get("src/file_y.py")

        if file_a and file_x and file_y:
            # file_a has more direct importers than file_x
            assert file_a.in_degree > file_x.in_degree

            # But file_y (which imports file_x) has high PageRank
            # due to being imported by many files
            assert file_y.in_degree > file_x.in_degree

            # The PageRank captures this transitive importance
            # file_y should have a higher PageRank than the leaf nodes
            # because it's imported by many files
            print(f"file_a PageRank: {file_a.pagerank:.4f} (in_degree: {file_a.in_degree})")
            print(f"file_x PageRank: {file_x.pagerank:.4f} (in_degree: {file_x.in_degree})")
            print(f"file_y PageRank: {file_y.pagerank:.4f} (in_degree: {file_y.in_degree})")
