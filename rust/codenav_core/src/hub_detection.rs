//! Hub detection algorithms for dependency graphs.
//!
//! Identifies architecturally important files based on their
//! position in the dependency graph (high in-degree nodes).

use hashbrown::HashMap;
use rayon::prelude::*;

/// Hub detector using in-degree analysis.
pub struct HubDetector {
    num_nodes: usize,
    in_degree: HashMap<usize, usize>,
    out_degree: HashMap<usize, usize>,
}

impl HubDetector {
    /// Create a new hub detector from edge list.
    ///
    /// # Arguments
    ///
    /// * `num_nodes` - Total number of nodes
    /// * `edges` - Slice of (source, target) directed edges
    pub fn new(num_nodes: usize, edges: &[(usize, usize)]) -> Self {
        let mut in_degree: HashMap<usize, usize> = HashMap::new();
        let mut out_degree: HashMap<usize, usize> = HashMap::new();

        for &(src, tgt) in edges {
            if src < num_nodes && tgt < num_nodes {
                *out_degree.entry(src).or_insert(0) += 1;
                *in_degree.entry(tgt).or_insert(0) += 1;
            }
        }

        Self {
            num_nodes,
            in_degree,
            out_degree,
        }
    }

    /// Find all hub nodes (nodes with in-degree >= threshold).
    ///
    /// # Arguments
    ///
    /// * `threshold` - Minimum in-degree to be considered a hub
    ///
    /// # Returns
    ///
    /// Vector of (node_index, in_degree) tuples, sorted by in-degree descending.
    pub fn find_hubs(&self, threshold: usize) -> Vec<(usize, usize)> {
        let mut hubs: Vec<(usize, usize)> = self
            .in_degree
            .iter()
            .filter(|(_, &deg)| deg >= threshold)
            .map(|(&idx, &deg)| (idx, deg))
            .collect();

        // Sort by in-degree descending
        hubs.sort_by(|a, b| b.1.cmp(&a.1));
        hubs
    }

    /// Get all in-degrees as a HashMap.
    pub fn get_in_degrees(&self) -> HashMap<usize, usize> {
        self.in_degree.clone()
    }

    /// Get all out-degrees as a HashMap.
    pub fn get_out_degrees(&self) -> HashMap<usize, usize> {
        self.out_degree.clone()
    }

    /// Compute hub scores combining in-degree and fan-out ratio.
    ///
    /// Hub score = in_degree * (1 + log(1 + out_degree))
    /// This rewards nodes that are both imported by many and import many.
    pub fn compute_hub_scores(&self) -> Vec<(usize, f64)> {
        let mut scores: Vec<(usize, f64)> = (0..self.num_nodes)
            .into_par_iter()
            .map(|i| {
                let in_deg = self.in_degree.get(&i).copied().unwrap_or(0) as f64;
                let out_deg = self.out_degree.get(&i).copied().unwrap_or(0) as f64;
                let score = in_deg * (1.0 + (1.0 + out_deg).ln());
                (i, score)
            })
            .filter(|(_, score)| *score > 0.0)
            .collect();

        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
        scores
    }

    /// Classify hub level based on in-degree.
    ///
    /// Returns a classification string:
    /// - "critical" for in-degree >= 8
    /// - "high" for in-degree >= 5
    /// - "medium" for in-degree >= 3
    /// - "low" for in-degree >= 2
    /// - "none" otherwise
    pub fn classify_hub(in_degree: usize) -> &'static str {
        match in_degree {
            d if d >= 8 => "critical",
            d if d >= 5 => "high",
            d if d >= 3 => "medium",
            d if d >= 2 => "low",
            _ => "none",
        }
    }

    /// Get detailed hub statistics.
    pub fn get_hub_stats(&self) -> HubStats {
        let in_degrees: Vec<usize> = self.in_degree.values().copied().collect();

        let total_hubs = in_degrees.iter().filter(|&&d| d >= 3).count();
        let critical_hubs = in_degrees.iter().filter(|&&d| d >= 8).count();
        let max_in_degree = in_degrees.iter().copied().max().unwrap_or(0);
        let avg_in_degree = if !in_degrees.is_empty() {
            in_degrees.iter().sum::<usize>() as f64 / in_degrees.len() as f64
        } else {
            0.0
        };

        HubStats {
            total_nodes: self.num_nodes,
            nodes_with_imports: self.in_degree.len(),
            total_hubs,
            critical_hubs,
            max_in_degree,
            avg_in_degree,
        }
    }
}

/// Statistics about hub distribution in the graph.
#[derive(Debug, Clone)]
pub struct HubStats {
    pub total_nodes: usize,
    pub nodes_with_imports: usize,
    pub total_hubs: usize,
    pub critical_hubs: usize,
    pub max_in_degree: usize,
    pub avg_in_degree: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_hubs() {
        // Node 3 is imported by 0, 1, 2 (in-degree = 3)
        let edges = vec![(0, 3), (1, 3), (2, 3), (0, 1)];
        let detector = HubDetector::new(4, &edges);

        let hubs = detector.find_hubs(3);
        assert_eq!(hubs.len(), 1);
        assert_eq!(hubs[0], (3, 3));
    }

    #[test]
    fn test_classify_hub() {
        assert_eq!(HubDetector::classify_hub(10), "critical");
        assert_eq!(HubDetector::classify_hub(8), "critical");
        assert_eq!(HubDetector::classify_hub(6), "high");
        assert_eq!(HubDetector::classify_hub(3), "medium");
        assert_eq!(HubDetector::classify_hub(2), "low");
        assert_eq!(HubDetector::classify_hub(1), "none");
    }

    #[test]
    fn test_in_out_degrees() {
        let edges = vec![(0, 1), (0, 2), (1, 2)];
        let detector = HubDetector::new(3, &edges);

        let in_deg = detector.get_in_degrees();
        let out_deg = detector.get_out_degrees();

        assert_eq!(out_deg.get(&0), Some(&2));  // 0 imports 1 and 2
        assert_eq!(in_deg.get(&2), Some(&2));   // 2 is imported by 0 and 1
    }

    #[test]
    fn test_hub_stats() {
        let edges = vec![
            (0, 5), (1, 5), (2, 5), (3, 5), (4, 5),  // 5 is critical hub (5 imports)
            (0, 6), (1, 6), (2, 6),                   // 6 is medium hub (3 imports)
        ];
        let detector = HubDetector::new(7, &edges);
        let stats = detector.get_hub_stats();

        assert_eq!(stats.total_nodes, 7);
        assert_eq!(stats.total_hubs, 2);  // nodes 5 and 6
        assert_eq!(stats.max_in_degree, 5);
    }

    #[test]
    fn test_hub_scores() {
        let edges = vec![(0, 2), (1, 2), (2, 3)];
        let detector = HubDetector::new(4, &edges);
        let scores = detector.compute_hub_scores();

        // Node 2 has in_degree=2 and out_degree=1, should have highest score
        assert!(!scores.is_empty());
        assert_eq!(scores[0].0, 2);
    }
}
