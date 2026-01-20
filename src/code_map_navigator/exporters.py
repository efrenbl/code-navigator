#!/usr/bin/env python3
"""Export code map to different formats.

Provides exporters for converting code maps to Markdown, HTML, and GraphViz
formats for documentation and visualization purposes.

Example:
    Command line usage:
        $ codemap export -f markdown -o docs/codebase.md
        $ codemap export -f html -o docs/codebase.html
        $ codemap export -f graphviz -o docs/deps.dot

    Python API usage:
        >>> from code_map_navigator.exporters import MarkdownExporter
        >>> exporter = MarkdownExporter('.codemap.json')
        >>> markdown = exporter.export()
"""

import html
import json
import os
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .colors import get_colors

__version__ = "1.3.0"


class BaseExporter(ABC):
    """Base class for code map exporters.

    Attributes:
        code_map: Loaded code map data.
        map_path: Path to the code map file.
    """

    def __init__(self, map_path: str):
        """Initialize the exporter.

        Args:
            map_path: Path to the .codemap.json file.
        """
        self.map_path = map_path
        self.code_map = self._load_map()

    def _load_map(self) -> Dict[str, Any]:
        """Load the code map from file."""
        with open(self.map_path, encoding="utf-8") as f:
            return json.load(f)

    @abstractmethod
    def export(self) -> str:
        """Export the code map to the target format.

        Returns:
            Exported content as a string.
        """
        pass

    def export_to_file(self, output_path: str) -> None:
        """Export the code map to a file.

        Args:
            output_path: Path to the output file.
        """
        content = self.export()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)


class MarkdownExporter(BaseExporter):
    """Export code map to Markdown format.

    Generates a Markdown document with:
    - Overview statistics
    - File listing with symbols
    - Symbol index by type

    Example:
        >>> exporter = MarkdownExporter('.codemap.json')
        >>> print(exporter.export())
    """

    def export(self) -> str:
        """Export to Markdown format.

        Returns:
            Markdown document as a string.
        """
        lines = []

        # Header
        root = self.code_map.get("root", "Unknown")
        lines.append(f"# Code Map: {Path(root).name}")
        lines.append("")
        lines.append(f"Generated: {self.code_map.get('generated_at', 'Unknown')}")
        lines.append("")

        # Statistics
        stats = self.code_map.get("stats", {})
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Files:** {stats.get('files_processed', 0)}")
        lines.append(f"- **Symbols:** {stats.get('symbols_found', 0)}")
        lines.append("")

        # Symbol counts by type
        type_counts = defaultdict(int)
        for file_info in self.code_map.get("files", {}).values():
            for sym in file_info.get("symbols", []):
                type_counts[sym["type"]] += 1

        if type_counts:
            lines.append("### Symbols by Type")
            lines.append("")
            lines.append("| Type | Count |")
            lines.append("|------|-------|")
            for sym_type, count in sorted(type_counts.items()):
                lines.append(f"| {sym_type} | {count} |")
            lines.append("")

        # Files
        lines.append("## Files")
        lines.append("")

        files = self.code_map.get("files", {})
        for file_path in sorted(files.keys()):
            file_info = files[file_path]
            symbols = file_info.get("symbols", [])

            lines.append(f"### `{file_path}`")
            lines.append("")

            if symbols:
                lines.append("| Symbol | Type | Lines |")
                lines.append("|--------|------|-------|")
                for sym in sorted(symbols, key=lambda s: s["lines"][0]):
                    name = sym["name"]
                    sym_type = sym["type"]
                    line_range = f"{sym['lines'][0]}-{sym['lines'][1]}"
                    lines.append(f"| `{name}` | {sym_type} | {line_range} |")
                lines.append("")
            else:
                lines.append("*No symbols found*")
                lines.append("")

        # Symbol Index
        lines.append("## Symbol Index")
        lines.append("")

        index = self.code_map.get("index", {})
        for name in sorted(index.keys()):
            entries = index[name]
            lines.append(f"### `{name}`")
            lines.append("")
            for entry in entries:
                file_path = entry["file"]
                sym_type = entry["type"]
                line_range = f"{entry['lines'][0]}-{entry['lines'][1]}"
                lines.append(f"- **{sym_type}** in `{file_path}` (lines {line_range})")
            lines.append("")

        return "\n".join(lines)


class HTMLExporter(BaseExporter):
    """Export code map to HTML format.

    Generates an interactive HTML document with:
    - Collapsible file tree
    - Symbol search
    - Statistics dashboard

    Example:
        >>> exporter = HTMLExporter('.codemap.json')
        >>> print(exporter.export())
    """

    def export(self) -> str:
        """Export to HTML format.

        Returns:
            HTML document as a string.
        """
        root = self.code_map.get("root", "Unknown")
        stats = self.code_map.get("stats", {})

        # Symbol counts by type
        type_counts = defaultdict(int)
        for file_info in self.code_map.get("files", {}).values():
            for sym in file_info.get("symbols", []):
                type_counts[sym["type"]] += 1

        # Generate file tree HTML
        files_html = self._generate_files_html()

        # Generate type stats HTML
        type_stats_html = ""
        for sym_type, count in sorted(type_counts.items()):
            type_stats_html += f'<div class="stat-item"><span class="type">{html.escape(sym_type)}</span><span class="count">{count}</span></div>'

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Map: {html.escape(Path(root).name)}</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --bg-light: #16213e;
            --text: #eee;
            --text-dim: #888;
            --accent: #0f3460;
            --highlight: #e94560;
            --success: #4ecca3;
            --border: #333;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: var(--highlight); margin-bottom: 10px; }}
        h2 {{ color: var(--success); margin: 20px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 5px; }}
        .meta {{ color: var(--text-dim); font-size: 0.9em; margin-bottom: 20px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: var(--bg-light);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }}
        .stat-card .value {{ font-size: 2em; color: var(--success); font-weight: bold; }}
        .stat-card .label {{ color: var(--text-dim); font-size: 0.9em; }}
        .type-stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }}
        .stat-item {{
            background: var(--accent);
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.9em;
        }}
        .stat-item .type {{ margin-right: 8px; }}
        .stat-item .count {{ color: var(--success); font-weight: bold; }}
        .search-box {{
            width: 100%;
            padding: 10px 15px;
            font-size: 1em;
            border: 1px solid var(--border);
            border-radius: 5px;
            background: var(--bg-light);
            color: var(--text);
            margin-bottom: 20px;
        }}
        .search-box:focus {{ outline: none; border-color: var(--highlight); }}
        .file {{
            background: var(--bg-light);
            border: 1px solid var(--border);
            border-radius: 5px;
            margin-bottom: 10px;
        }}
        .file-header {{
            padding: 10px 15px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .file-header:hover {{ background: var(--accent); }}
        .file-path {{ font-family: monospace; color: var(--success); }}
        .file-count {{ color: var(--text-dim); font-size: 0.9em; }}
        .file-content {{ display: none; padding: 0 15px 15px; }}
        .file.open .file-content {{ display: block; }}
        .file.open .file-header {{ border-bottom: 1px solid var(--border); }}
        .symbol {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
        }}
        .symbol:last-child {{ border-bottom: none; }}
        .symbol-name {{ font-family: monospace; color: var(--text); }}
        .symbol-type {{
            background: var(--accent);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            color: var(--highlight);
        }}
        .symbol-lines {{ color: var(--text-dim); font-size: 0.9em; margin-left: 10px; }}
        .hidden {{ display: none !important; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Map: {html.escape(Path(root).name)}</h1>
        <p class="meta">Generated: {html.escape(self.code_map.get('generated_at', 'Unknown'))}</p>

        <div class="stats">
            <div class="stat-card">
                <div class="value">{stats.get('files_processed', 0)}</div>
                <div class="label">Files</div>
            </div>
            <div class="stat-card">
                <div class="value">{stats.get('symbols_found', 0)}</div>
                <div class="label">Symbols</div>
            </div>
        </div>

        <h2>Symbols by Type</h2>
        <div class="type-stats">{type_stats_html}</div>

        <h2>Files</h2>
        <input type="text" class="search-box" placeholder="Search symbols..." id="search">
        <div id="files">{files_html}</div>
    </div>

    <script>
        // Toggle file expansion
        document.querySelectorAll('.file-header').forEach(header => {{
            header.addEventListener('click', () => {{
                header.parentElement.classList.toggle('open');
            }});
        }});

        // Search functionality
        const searchBox = document.getElementById('search');
        const files = document.querySelectorAll('.file');

        searchBox.addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase();
            files.forEach(file => {{
                const symbols = file.querySelectorAll('.symbol');
                let hasMatch = false;
                symbols.forEach(symbol => {{
                    const name = symbol.querySelector('.symbol-name').textContent.toLowerCase();
                    if (name.includes(query)) {{
                        symbol.classList.remove('hidden');
                        hasMatch = true;
                    }} else {{
                        symbol.classList.add('hidden');
                    }}
                }});
                if (query && hasMatch) {{
                    file.classList.add('open');
                    file.classList.remove('hidden');
                }} else if (query && !hasMatch) {{
                    file.classList.add('hidden');
                }} else {{
                    file.classList.remove('hidden');
                    symbols.forEach(s => s.classList.remove('hidden'));
                }}
            }});
        }});
    </script>
</body>
</html>'''

    def _generate_files_html(self) -> str:
        """Generate HTML for files section."""
        files_html = []
        files = self.code_map.get("files", {})

        for file_path in sorted(files.keys()):
            file_info = files[file_path]
            symbols = file_info.get("symbols", [])

            symbols_html = ""
            for sym in sorted(symbols, key=lambda s: s["lines"][0]):
                name = html.escape(sym["name"])
                sym_type = html.escape(sym["type"])
                lines = f"{sym['lines'][0]}-{sym['lines'][1]}"
                symbols_html += f'''
                <div class="symbol">
                    <span>
                        <span class="symbol-name">{name}</span>
                        <span class="symbol-lines">:{lines}</span>
                    </span>
                    <span class="symbol-type">{sym_type}</span>
                </div>'''

            file_html = f'''
            <div class="file">
                <div class="file-header">
                    <span class="file-path">{html.escape(file_path)}</span>
                    <span class="file-count">{len(symbols)} symbols</span>
                </div>
                <div class="file-content">{symbols_html}</div>
            </div>'''
            files_html.append(file_html)

        return "".join(files_html)


class GraphVizExporter(BaseExporter):
    """Export code map dependencies to GraphViz DOT format.

    Generates a DOT graph showing:
    - Symbols as nodes
    - Dependencies as edges
    - Files as clusters

    Example:
        >>> exporter = GraphVizExporter('.codemap.json')
        >>> print(exporter.export())
    """

    def export(self) -> str:
        """Export to GraphViz DOT format.

        Returns:
            DOT graph as a string.
        """
        lines = []
        lines.append("digraph CodeMap {")
        lines.append("    rankdir=LR;")
        lines.append("    node [shape=box, style=filled, fontname=Helvetica];")
        lines.append("    edge [color=gray60];")
        lines.append("")

        # Color scheme for symbol types
        type_colors = {
            "function": "#4ecca3",
            "class": "#e94560",
            "method": "#0f3460",
            "interface": "#ff6b6b",
            "struct": "#ffa502",
            "enum": "#a29bfe",
            "type": "#fd79a8",
        }

        # Group symbols by file
        files = self.code_map.get("files", {})
        node_ids = {}  # Map (file, name) to node id
        edges = []

        for file_idx, (file_path, file_info) in enumerate(sorted(files.items())):
            symbols = file_info.get("symbols", [])
            if not symbols:
                continue

            # Create subgraph (cluster) for file
            cluster_name = file_path.replace("/", "_").replace(".", "_").replace("-", "_")
            lines.append(f'    subgraph cluster_{cluster_name} {{')
            lines.append(f'        label="{self._escape_dot(file_path)}";')
            lines.append("        style=rounded;")
            lines.append("        bgcolor=gray95;")
            lines.append("")

            for sym_idx, sym in enumerate(symbols):
                node_id = f"node_{file_idx}_{sym_idx}"
                node_ids[(file_path, sym["name"])] = node_id

                color = type_colors.get(sym["type"], "#dfe6e9")
                label = f"{sym['name']}\\n[{sym['type']}]"

                lines.append(f'        {node_id} [label="{label}", fillcolor="{color}"];')

                # Collect dependencies for edges
                deps = sym.get("deps") or []
                for dep in deps:
                    edges.append((node_id, dep))

            lines.append("    }")
            lines.append("")

        # Add edges for dependencies
        if edges:
            lines.append("    // Dependencies")
            for source_id, dep_name in edges:
                # Try to find the target node
                target_id = None
                for (file_path, name), nid in node_ids.items():
                    if name == dep_name:
                        target_id = nid
                        break

                if target_id:
                    lines.append(f"    {source_id} -> {target_id};")

            lines.append("")

        lines.append("}")
        return "\n".join(lines)

    def _escape_dot(self, text: str) -> str:
        """Escape text for DOT format."""
        return text.replace('"', '\\"').replace("\n", "\\n")


def get_exporter(format_type: str, map_path: str) -> BaseExporter:
    """Get an exporter for the specified format.

    Args:
        format_type: Export format ('markdown', 'html', 'graphviz').
        map_path: Path to the .codemap.json file.

    Returns:
        Appropriate exporter instance.

    Raises:
        ValueError: If format is not supported.
    """
    exporters = {
        "markdown": MarkdownExporter,
        "md": MarkdownExporter,
        "html": HTMLExporter,
        "graphviz": GraphVizExporter,
        "dot": GraphVizExporter,
    }

    exporter_class = exporters.get(format_type.lower())
    if not exporter_class:
        raise ValueError(f"Unsupported format: {format_type}. Supported: markdown, html, graphviz")

    return exporter_class(map_path)


def run_export(args) -> None:
    """Run the export command.

    Args:
        args: Parsed command-line arguments.
    """
    c = get_colors(no_color=getattr(args, "no_color", False))

    map_path = getattr(args, "map", ".codemap.json")
    if not os.path.exists(map_path):
        print(c.error(f"Code map not found: {map_path}"), file=sys.stderr)
        sys.exit(1)

    format_type = getattr(args, "format", "markdown")
    output_path = getattr(args, "output", None)

    try:
        exporter = get_exporter(format_type, map_path)
        content = exporter.export()

        if output_path:
            exporter.export_to_file(output_path)
            print(c.success(f"✓ Exported to {output_path}"), file=sys.stderr)
        else:
            print(content)

    except Exception as e:
        print(c.error(f"Export error: {e}"), file=sys.stderr)
        sys.exit(1)
