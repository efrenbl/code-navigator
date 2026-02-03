//! Import path resolution with batch processing.
//!
//! Resolves import strings to actual file paths using various
//! strategies including exact match, suffix match, and extension inference.

use hashbrown::HashMap;
use rayon::prelude::*;

/// Import resolver with configurable extensions and file index.
pub struct ImportResolver {
    file_index: HashMap<String, String>,
    extensions: Vec<String>,
    /// Normalized paths for faster lookup (lowercase, no extension)
    normalized_index: HashMap<String, Vec<String>>,
}

impl ImportResolver {
    /// Create a new import resolver.
    ///
    /// # Arguments
    ///
    /// * `file_index` - Map of normalized path -> actual file path
    /// * `extensions` - List of extensions to try (e.g., [".py", ".js", ".ts"])
    pub fn new(file_index: HashMap<String, String>, extensions: Vec<String>) -> Self {
        // Build normalized index for fuzzy matching
        let mut normalized_index: HashMap<String, Vec<String>> = HashMap::new();

        for (norm_path, actual_path) in &file_index {
            // Add entry for path without extension
            let without_ext = remove_extension(norm_path);
            normalized_index
                .entry(without_ext.to_lowercase())
                .or_default()
                .push(actual_path.clone());

            // Add entry for basename
            if let Some(basename) = get_basename(norm_path) {
                let basename_no_ext = remove_extension(basename);
                normalized_index
                    .entry(basename_no_ext.to_lowercase())
                    .or_default()
                    .push(actual_path.clone());
            }
        }

        Self {
            file_index,
            extensions,
            normalized_index,
        }
    }

    /// Resolve a single import string to a file path.
    ///
    /// Tries multiple strategies in order:
    /// 1. Exact match
    /// 2. Match with extensions
    /// 3. Match as directory index (index.js, __init__.py, etc.)
    /// 4. Fuzzy suffix match
    pub fn resolve(&self, import_string: &str) -> Option<String> {
        let normalized = normalize_import(import_string);

        // Strategy 1: Exact match
        if let Some(path) = self.file_index.get(&normalized) {
            return Some(path.clone());
        }

        // Strategy 2: Try with extensions
        for ext in &self.extensions {
            let with_ext = format!("{}{}", normalized, ext);
            if let Some(path) = self.file_index.get(&with_ext) {
                return Some(path.clone());
            }
        }

        // Strategy 3: Directory index files
        for index_name in &["index", "__init__"] {
            for ext in &self.extensions {
                let index_path = format!("{}/{}{}", normalized, index_name, ext);
                if let Some(path) = self.file_index.get(&index_path) {
                    return Some(path.clone());
                }
            }
        }

        // Strategy 4: Fuzzy match on normalized path
        let normalized_lower = normalized.to_lowercase();
        if let Some(candidates) = self.normalized_index.get(&normalized_lower) {
            if candidates.len() == 1 {
                return Some(candidates[0].clone());
            }
            // If multiple matches, prefer shorter paths
            if !candidates.is_empty() {
                let mut sorted = candidates.clone();
                sorted.sort_by_key(|p| p.len());
                return Some(sorted[0].clone());
            }
        }

        // Strategy 5: Suffix match (for imports like "utils" matching "src/utils.py")
        let suffix_matches: Vec<_> = self.file_index
            .iter()
            .filter(|(k, _)| {
                k.ends_with(&normalized) ||
                k.ends_with(&format!("/{}", normalized))
            })
            .collect();

        if suffix_matches.len() == 1 {
            return Some(suffix_matches[0].1.clone());
        }

        None
    }

    /// Resolve multiple imports in batch using parallel processing.
    ///
    /// # Arguments
    ///
    /// * `imports` - Slice of import strings to resolve
    ///
    /// # Returns
    ///
    /// Vector of (import_string, Option<resolved_path>) tuples.
    pub fn resolve_batch(&self, imports: &[String]) -> Vec<(String, Option<String>)> {
        imports
            .par_iter()
            .map(|import| {
                let resolved = self.resolve(import);
                (import.clone(), resolved)
            })
            .collect()
    }

    /// Get resolution statistics for a batch of imports.
    pub fn get_resolution_stats(&self, imports: &[String]) -> ResolutionStats {
        let results = self.resolve_batch(imports);
        let resolved = results.iter().filter(|(_, r)| r.is_some()).count();
        let unresolved = results.len() - resolved;

        ResolutionStats {
            total: imports.len(),
            resolved,
            unresolved,
            resolution_rate: if imports.is_empty() {
                0.0
            } else {
                resolved as f64 / imports.len() as f64
            },
        }
    }
}

/// Statistics about import resolution.
#[derive(Debug, Clone)]
pub struct ResolutionStats {
    pub total: usize,
    pub resolved: usize,
    pub unresolved: usize,
    pub resolution_rate: f64,
}

/// Normalize an import string for matching.
fn normalize_import(import: &str) -> String {
    import
        .trim()
        .replace('\\', "/")
        .replace("./", "")
        .replace("../", "")
        .trim_start_matches('/')
        .to_string()
}

/// Remove file extension from a path.
fn remove_extension(path: &str) -> &str {
    if let Some(dot_pos) = path.rfind('.') {
        if let Some(slash_pos) = path.rfind('/') {
            if dot_pos > slash_pos {
                return &path[..dot_pos];
            }
        } else {
            return &path[..dot_pos];
        }
    }
    path
}

/// Get the basename (filename) from a path.
fn get_basename(path: &str) -> Option<&str> {
    path.rsplit('/').next()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_resolver() -> ImportResolver {
        let mut file_index = HashMap::new();
        file_index.insert("src/utils.py".to_string(), "src/utils.py".to_string());
        file_index.insert("src/api/client.py".to_string(), "src/api/client.py".to_string());
        file_index.insert("src/api/__init__.py".to_string(), "src/api/__init__.py".to_string());
        file_index.insert("lib/index.js".to_string(), "lib/index.js".to_string());
        file_index.insert("components/Button.tsx".to_string(), "components/Button.tsx".to_string());

        ImportResolver::new(
            file_index,
            vec![".py".to_string(), ".js".to_string(), ".ts".to_string(), ".tsx".to_string()],
        )
    }

    #[test]
    fn test_exact_match() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("src/utils.py");
        assert_eq!(result, Some("src/utils.py".to_string()));
    }

    #[test]
    fn test_with_extension() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("src/utils");
        assert_eq!(result, Some("src/utils.py".to_string()));
    }

    #[test]
    fn test_directory_index_python() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("src/api");
        assert_eq!(result, Some("src/api/__init__.py".to_string()));
    }

    #[test]
    fn test_directory_index_js() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("lib");
        assert_eq!(result, Some("lib/index.js".to_string()));
    }

    #[test]
    fn test_suffix_match() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("utils");
        assert_eq!(result, Some("src/utils.py".to_string()));
    }

    #[test]
    fn test_unresolved() {
        let resolver = create_test_resolver();
        let result = resolver.resolve("nonexistent/module");
        assert_eq!(result, None);
    }

    #[test]
    fn test_batch_resolve() {
        let resolver = create_test_resolver();
        let imports = vec![
            "src/utils".to_string(),
            "src/api".to_string(),
            "nonexistent".to_string(),
        ];

        let results = resolver.resolve_batch(&imports);
        assert_eq!(results.len(), 3);
        assert!(results[0].1.is_some());
        assert!(results[1].1.is_some());
        assert!(results[2].1.is_none());
    }

    #[test]
    fn test_resolution_stats() {
        let resolver = create_test_resolver();
        let imports = vec![
            "src/utils".to_string(),
            "src/api".to_string(),
            "nonexistent".to_string(),
            "also_missing".to_string(),
        ];

        let stats = resolver.get_resolution_stats(&imports);
        assert_eq!(stats.total, 4);
        assert_eq!(stats.resolved, 2);
        assert_eq!(stats.unresolved, 2);
        assert!((stats.resolution_rate - 0.5).abs() < 0.01);
    }

    #[test]
    fn test_normalize_import() {
        assert_eq!(normalize_import("./utils"), "utils");
        assert_eq!(normalize_import("../lib/utils"), "lib/utils");
        assert_eq!(normalize_import("src\\api\\client"), "src/api/client");
        assert_eq!(normalize_import("/absolute/path"), "absolute/path");
    }
}
