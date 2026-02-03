//! # Code Map Core
//!
//! High-performance core algorithms for Claude Code Navigator.
//!
//! This crate provides Rust implementations of performance-critical algorithms
//! that can be called from Python via PyO3 bindings.
//!
//! ## Features
//!
//! - **PageRank**: Parallel PageRank computation for dependency graphs
//! - **Hub Detection**: Fast identification of architecturally important files
//! - **Import Resolution**: SIMD-accelerated string matching for imports
//!
//! ## Python Usage
//!
//! ```python
//! from codenav._rust_core import (
//!     fast_pagerank,
//!     detect_hubs,
//!     resolve_imports_batch,
//! )
//!
//! # Compute PageRank scores
//! scores = fast_pagerank(
//!     num_nodes=1000,
//!     edges=[(0, 1), (1, 2), ...],
//!     damping=0.85,
//! )
//! ```

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

mod pagerank;
mod hub_detection;
mod import_resolver;

use pagerank::PageRankComputer;
use hub_detection::HubDetector;
use import_resolver::ImportResolver;

/// Compute PageRank scores for a directed graph.
///
/// This is the main entry point for fast PageRank computation from Python.
/// Uses parallel iteration with Rayon for significant speedup on large graphs.
///
/// # Arguments
///
/// * `num_nodes` - Total number of nodes in the graph
/// * `edges` - List of (source, target) tuples representing directed edges
/// * `damping` - Damping factor (default: 0.85)
/// * `max_iterations` - Maximum iterations (default: 100)
/// * `tolerance` - Convergence tolerance (default: 1e-6)
///
/// # Returns
///
/// Dictionary mapping node index to PageRank score.
///
/// # Example
///
/// ```python
/// scores = fast_pagerank(4, [(0,1), (0,2), (1,2), (2,3)], 0.85, 100, 1e-6)
/// print(scores)  # {0: 0.15, 1: 0.22, 2: 0.35, 3: 0.28}
/// ```
#[pyfunction]
#[pyo3(signature = (num_nodes, edges, damping=0.85, max_iterations=100, tolerance=1e-6))]
fn fast_pagerank(
    py: Python<'_>,
    num_nodes: usize,
    edges: Vec<(usize, usize)>,
    damping: f64,
    max_iterations: usize,
    tolerance: f64,
) -> PyResult<Py<PyDict>> {
    // Release GIL during computation
    let scores = py.allow_threads(|| {
        let computer = PageRankComputer::new(num_nodes, &edges, damping);
        computer.compute(max_iterations, tolerance)
    });

    // Convert to Python dict
    let dict = PyDict::new_bound(py);
    for (i, score) in scores.iter().enumerate() {
        dict.set_item(i, *score)?;
    }

    Ok(dict.into())
}

/// Detect hub files based on in-degree threshold.
///
/// Returns indices of nodes that have at least `threshold` incoming edges.
///
/// # Arguments
///
/// * `num_nodes` - Total number of nodes
/// * `edges` - List of (source, target) directed edges
/// * `threshold` - Minimum in-degree to be considered a hub (default: 3)
///
/// # Returns
///
/// List of (node_index, in_degree) tuples for all hubs.
#[pyfunction]
#[pyo3(signature = (num_nodes, edges, threshold=3))]
fn detect_hubs(
    py: Python<'_>,
    num_nodes: usize,
    edges: Vec<(usize, usize)>,
    threshold: usize,
) -> PyResult<Py<PyList>> {
    let hubs = py.allow_threads(|| {
        let detector = HubDetector::new(num_nodes, &edges);
        detector.find_hubs(threshold)
    });

    // Convert to Python list of tuples
    let list = PyList::new_bound(py, hubs.iter().map(|(idx, degree)| (*idx, *degree)));

    Ok(list.into())
}

/// Get hub scores using PageRank.
///
/// Combines PageRank computation with hub detection to return files
/// sorted by architectural importance.
///
/// # Arguments
///
/// * `num_nodes` - Total number of nodes
/// * `edges` - List of (source, target) directed edges
/// * `top_n` - Number of top hubs to return (default: 10)
/// * `damping` - PageRank damping factor (default: 0.85)
///
/// # Returns
///
/// List of (node_index, pagerank_score, in_degree) tuples.
#[pyfunction]
#[pyo3(signature = (num_nodes, edges, top_n=10, damping=0.85))]
fn get_critical_nodes(
    py: Python<'_>,
    num_nodes: usize,
    edges: Vec<(usize, usize)>,
    top_n: usize,
    damping: f64,
) -> PyResult<Py<PyList>> {
    let results = py.allow_threads(|| {
        // Compute PageRank
        let pr_computer = PageRankComputer::new(num_nodes, &edges, damping);
        let scores = pr_computer.compute(100, 1e-6);

        // Get in-degrees
        let detector = HubDetector::new(num_nodes, &edges);
        let in_degrees = detector.get_in_degrees();

        // Combine and sort by PageRank score
        let mut combined: Vec<(usize, f64, usize)> = scores
            .iter()
            .enumerate()
            .map(|(i, &score)| (i, score, in_degrees.get(&i).copied().unwrap_or(0)))
            .collect();

        combined.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
        combined.truncate(top_n);
        combined
    });

    let list = PyList::new_bound(
        py,
        results.iter().map(|(idx, score, degree)| (*idx, *score, *degree)),
    );

    Ok(list.into())
}

/// Resolve multiple imports in batch using SIMD-accelerated matching.
///
/// # Arguments
///
/// * `imports` - List of import strings to resolve
/// * `file_index` - Dictionary mapping normalized paths to actual file paths
/// * `extensions` - List of extensions to try
///
/// # Returns
///
/// Dictionary mapping import string to resolved path (or None if unresolved).
#[pyfunction]
#[pyo3(signature = (imports, file_index, extensions))]
fn resolve_imports_batch(
    py: Python<'_>,
    imports: Vec<String>,
    file_index: &Bound<'_, PyDict>,
    extensions: Vec<String>,
) -> PyResult<Py<PyDict>> {
    // Convert Python dict to Rust HashMap
    let mut index: hashbrown::HashMap<String, String> = hashbrown::HashMap::new();
    for (key, value) in file_index.iter() {
        let k: String = key.extract()?;
        let v: String = value.extract()?;
        index.insert(k, v);
    }

    let results = py.allow_threads(|| {
        let resolver = ImportResolver::new(index, extensions);
        resolver.resolve_batch(&imports)
    });

    // Convert to Python dict
    let dict = PyDict::new_bound(py);
    for (import, resolved) in results {
        match resolved {
            Some(path) => dict.set_item(import, path)?,
            None => dict.set_item(import, py.None())?,
        }
    }

    Ok(dict.into())
}

/// Graph statistics computation.
#[pyfunction]
fn compute_graph_stats(
    py: Python<'_>,
    num_nodes: usize,
    edges: Vec<(usize, usize)>,
) -> PyResult<Py<PyDict>> {
    let stats = py.allow_threads(|| {
        let detector = HubDetector::new(num_nodes, &edges);
        let in_degrees = detector.get_in_degrees();
        let out_degrees = detector.get_out_degrees();

        let total_in: usize = in_degrees.values().sum();
        let total_out: usize = out_degrees.values().sum();
        let max_in = in_degrees.values().max().copied().unwrap_or(0);
        let max_out = out_degrees.values().max().copied().unwrap_or(0);
        let isolated = (0..num_nodes)
            .filter(|i| {
                in_degrees.get(i).copied().unwrap_or(0) == 0
                    && out_degrees.get(i).copied().unwrap_or(0) == 0
            })
            .count();

        (total_in, total_out, max_in, max_out, isolated, edges.len())
    });

    let dict = PyDict::new_bound(py);
    dict.set_item("total_edges", stats.5)?;
    dict.set_item("avg_in_degree", stats.0 as f64 / num_nodes as f64)?;
    dict.set_item("avg_out_degree", stats.1 as f64 / num_nodes as f64)?;
    dict.set_item("max_in_degree", stats.2)?;
    dict.set_item("max_out_degree", stats.3)?;
    dict.set_item("isolated_nodes", stats.4)?;

    Ok(dict.into())
}

/// Python module definition.
#[pymodule]
fn _rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fast_pagerank, m)?)?;
    m.add_function(wrap_pyfunction!(detect_hubs, m)?)?;
    m.add_function(wrap_pyfunction!(get_critical_nodes, m)?)?;
    m.add_function(wrap_pyfunction!(resolve_imports_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_graph_stats, m)?)?;

    // Version info
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    Ok(())
}
