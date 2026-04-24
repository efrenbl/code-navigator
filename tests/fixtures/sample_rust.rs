use std::fmt;

/// A simple struct
pub struct User {
    pub name: String,
    email: String,
}

/// Generic struct
pub struct Container<T> {
    value: T,
}

/// Trait definition
pub trait Greetable {
    fn greet(&self) -> String;
    fn name(&self) -> &str;
}

/// Enum with variants
pub enum Status {
    Active,
    Inactive(String),
    Custom { code: i32 },
}

/// Impl block
impl User {
    pub fn new(name: String, email: String) -> Self {
        User { name, email }
    }

    fn validate(&self) -> bool {
        !self.email.is_empty()
    }
}

/// Trait impl
impl fmt::Display for User {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{} <{}>", self.name, self.email)
    }
}

/// Generic function
pub fn map_vec<T, U>(v: Vec<T>, f: impl Fn(T) -> U) -> Vec<U> {
    v.into_iter().map(f).collect()
}

/// Async function
pub async fn fetch_data(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    Ok(String::new())
}

/// Const
pub const MAX_SIZE: usize = 1024;

/// Type alias
pub type Result<T> = std::result::Result<T, Error>;

/// Test function
#[test]
fn test_user_new() {
    let u = User::new("a".into(), "b".into());
    assert!(!u.name.is_empty());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate() {
        let u = User::new("a".into(), "b".into());
        assert!(u.validate());
    }
}
