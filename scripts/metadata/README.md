# Provider metadata overrides

The JSON files in this directory contain provider-specific fallback metadata
that cannot be reliably discovered from the provider's public catalog endpoint
at update time.

Rules:

- Provider update scripts and postprocessors load these files; model values are
  not embedded in Python dictionaries.
- Every provider-specific override must include a source URL in the record when
  it describes a documented capability or price.
- Values obtained from live provider catalogs take precedence over these
  fallbacks.
- Legacy values are compatibility fallbacks and must not be presented as a
  fresh live discovery.
- Do not use OpenRouter data to replace native provider catalogs.
