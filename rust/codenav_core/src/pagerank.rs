//! PageRank computation with parallel iteration.
//!
//! This module provides a high-performance PageRank implementation
//! using Rayon for parallel computation across multiple CPU cores.

use hashbrown::HashMap;
use rayon::prelude::*;

/// PageRank computer with configurable damping factor.
pub struct PageRankComputer {
    num_nodes: usize,
    adjacency: Vec<Vec<usize>>,  // outgoing edges per node
    in_edges: Vec<Vec<usize>>,   // incoming edges per node
    out_degree: Vec<usize>,
    damping: f64,
}

impl PageRankComputer {
    /// Create a new PageRank computer.
    ///
    /// # Arguments
    ///
    /// * `num_nodes` - Total number of nodes in the graph
    /// * `edges` - Slice of (source, target) directed edges
    /// * `damping` - Damping factor (typically 0.85)
    pub fn new(num_nodes: usize, edges: &[(usize, usize)], damping: f64) -> Self {
        let mut adjacency = vec![Vec::new(); num_nodes];
        let mut in_edges = vec![Vec::new(); num_nodes];
        let mut out_degree = vec![0usize; num_nodes];

        for &(src, tgt) in edges {
            if src < num_nodes && tgt < num_nodes {
                adjacency[src].push(tgt);
                in_edges[tgt].push(src);
                out_degree[src] += 1;
            }
        }

        Self {
            num_nodes,
            adjacency,
            in_edges,
            out_degree,
            damping,
        }
    }

    /// Compute PageRank scores using power iteration.
    ///
    /// Uses parallel iteration with Rayon for significant speedup
    /// on graphs with many nodes.
    ///
    /// # Arguments
    ///
    /// * `max_iterations` - Maximum number of iterations
    /// * `tolerance` - Convergence tolerance (L1 norm)
    ///
    /// # Returns
    ///
    /// Vector of PageRank scores indexed by node ID.
    pub fn compute(&self, max_iterations: usize, tolerance: f64) -> Vec<f64> {
        if self.num_nodes == 0 {
            return Vec::new();
        }

        let n = self.num_nodes as f64;
        let initial_score = 1.0 / n;
        let teleport = (1.0 - self.damping) / n;

        let mut scores: Vec<f64> = vec![initial_score; self.num_nodes];
        let mut new_scores: Vec<f64> = vec![0.0; self.num_nodes];

        // Handle dangling nodes (no outgoing edges)
        let dangling_nodes: Vec<usize> = (0..self.num_nodes)
            .filter(|&i| self.out_degree[i] == 0)
            .collect();

        for _iteration in 0..max_iterations {
            // Compute dangling sum (contribution from nodes with no outgoing edges)
            let dangling_sum: f64 = dangling_nodes
                .par_iter()
                .map(|&i| scores[i])
                .sum();
            let dangling_contrib = self.damping * dangling_sum / n;

            // Parallel computation of new scores
            new_scores
                .par_iter_mut()
                .enumerate()
                .for_each(|(i, new_score)| {
                    let incoming_contrib: f64 = self.in_edges[i]
                        .iter()
                        .map(|&j| scores[j] / self.out_degree[j] as f64)
                        .sum();

                    *new_score = teleport + dangling_contrib + self.damping * incoming_contrib;
                });

            // Check convergence (L1 norm)
            let diff: f64 = scores
                .par_iter()
                .zip(new_scores.par_iter())
                .map(|(old, new)| (old - new).abs())
                .sum();

            std::mem::swap(&mut scores, &mut new_scores);

            if diff < tolerance {
                break;
            }
        }

        // Normalize scores
        let total: f64 = scores.iter().sum();
        if total > 0.0 {
            scores.par_iter_mut().for_each(|s| *s /= total);
        }

        scores
    }

    /// Compute PageRank and return as HashMap.
    pub fn compute_as_map(&self, max_iterations: usize, tolerance: f64) -> HashMap<usize, f64> {
        let scores = self.compute(max_iterations, tolerance);
        scores.into_iter().enumerate().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_graph() {
        // Simple chain: 0 -> 1 -> 2 -> 3
        let edges = vec![(0, 1), (1, 2), (2, 3)];
        let computer = PageRankComputer::new(4, &edges, 0.85);
        let scores = computer.compute(100, 1e-6);

        assert_eq!(scores.len(), 4);
        // Node 3 should have highest score (sink node)
        assert!(scores[3] > scores[0]);
    }

    #[test]
    fn test_cyclic_graph() {
        // Cycle: 0 -> 1 -> 2 -> 0
        let edges = vec![(0, 1), (1, 2), (2, 0)];
        let computer = PageRankComputer::new(3, &edges, 0.85);
        let scores = computer.compute(100, 1e-6);

        // All nodes should have similar scores in a cycle
        let diff = (scores[0] - scores[1]).abs();
        assert!(diff < 0.01);
    }

    #[test]
    fn test_hub_node() {
        // Hub pattern: 0, 1, 2 all point to 3
        let edges = vec![(0, 3), (1, 3), (2, 3)];
        let computer = PageRankComputer::new(4, &edges, 0.85);
        let scores = computer.compute(100, 1e-6);

        // Node 3 should have highest score
        assert!(scores[3] > scores[0]);
        assert!(scores[3] > scores[1]);
        assert!(scores[3] > scores[2]);
    }

    #[test]
    fn test_empty_graph() {
        let edges: Vec<(usize, usize)> = vec![];
        let computer = PageRankComputer::new(0, &edges, 0.85);
        let scores = computer.compute(100, 1e-6);

        assert!(scores.is_empty());
    }

    #[test]
    fn test_isolated_nodes() {
        // No edges, just isolated nodes
        let edges: Vec<(usize, usize)> = vec![];
        let computer = PageRankComputer::new(3, &edges, 0.85);
        let scores = computer.compute(100, 1e-6);

        // All nodes should have equal scores
        let expected = 1.0 / 3.0;
        for score in &scores {
            assert!((score - expected).abs() < 0.01);
        }
    }
}
