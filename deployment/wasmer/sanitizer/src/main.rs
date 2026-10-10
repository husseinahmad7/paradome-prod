//! Same narrow HTML5 allowlist as posts/sanitizers.py, using current Ammonia.
use std::collections::{HashMap, HashSet};
use std::io::{self, Read};

fn sanitize(input: &str) -> String {
    let tags: HashSet<&str> = ["a", "b", "blockquote", "br", "code", "em", "h2", "h3", "h4", "i", "li", "ol", "p", "pre", "s", "strong", "u", "ul"].into_iter().collect();
    let attributes: HashMap<&str, HashSet<&str>> = [("a", ["href", "title"].into_iter().collect())].into_iter().collect();
    let schemes: HashSet<&str> = ["http", "https", "mailto"].into_iter().collect();
    let clean_content: HashSet<&str> = ["embed", "iframe", "object", "script", "style", "template"].into_iter().collect();
    ammonia::Builder::default()
        .tags(tags)
        .tag_attributes(attributes)
        .generic_attributes(HashSet::new())
        .url_schemes(schemes)
        .clean_content_tags(clean_content)
        .link_rel(Some("noopener noreferrer nofollow ugc"))
        .strip_comments(true)
        .clean(input)
        .to_string()
}

fn main() {
    if std::env::args().nth(1).as_deref() == Some("--version") {
        println!("paradome-sanitizer 0.1.0; ammonia 4.1.4; policy prose-v1");
        return;
    }
    let mut input = String::new();
    if io::stdin().take(2_621_441).read_to_string(&mut input).is_err() || input.len() > 2_621_440 {
        eprintln!("Invalid or oversized UTF-8 input");
        std::process::exit(2);
    }
    print!("{}", sanitize(&input));
}

#[cfg(test)]
mod tests {
    use super::sanitize;
    #[test]
    fn active_content_and_urls_are_removed() {
        let cleaned = sanitize("<p>safe<script>alert(1)</script><a href='javascript:alert(2)' onclick='x()'>link</a></p>");
        assert!(!cleaned.contains("script"));
        assert!(!cleaned.contains("onclick"));
        assert!(!cleaned.contains("javascript:"));
        assert!(cleaned.contains("safe"));
    }
    #[test]
    fn rich_text_survives() {
        assert_eq!(sanitize("<h2>Title</h2><p><strong>safe</strong></p>"), "<h2>Title</h2><p><strong>safe</strong></p>");
    }
}
