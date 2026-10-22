# Output Contracts

Output Contracts checks whether an output meets explicit structural requirements before someone uses it. A contract can require Markdown sections in order, ban particular patterns, or require precise JSON fields and values.

The demo validates a generated work handoff. One response omits “Unresolved questions,” puts “Evidence” after the closing section, and contains a forbidden completion claim. Another JSON response gives a boolean where an integer count is required. Reports locate each violation and identify the exact contract rule.

The first release is a small deterministic validator with declarative JSON contracts, JSON/Markdown reports, and useful fixture contracts. Markdown checks and JSON field checks are separate modes. There is no network call, model judge, or hidden repair step.

The boundary matters: structural conformance cannot establish truth, completeness of evidence, safety, or quality of reasoning. A clean result says the configured rules passed. It does not certify the output's content.

Validate the product by measuring recurring output-shape failures caught before downstream use, contract-writing effort, and false positives from overly rigid rules. Its initial value is a dependable small interface, not a universal output-quality score.
