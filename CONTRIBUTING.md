# Contributing

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e .
.venv/bin/pytest
.venv/bin/mypy
```

`pytest` runs the webhook, client and spec suites, and checks that the generated files are current. `mypy` (strict) type-checks the package and the usage examples in `tests/typecheck/`.

## Generated files

- `openapi/openapi.yaml` is copied from the platform. Don't edit it here.
- `src/inboundr/_generated/api.py` is generated from it. Don't edit it either; `src/inboundr/_types.py` gives its shapes stable names.
- `src/inboundr/_client.py` is generated from `_async_client.py` by `scripts/unasync.py`. Change the async client, then regenerate.

When the API changes:

```bash
.venv/bin/python scripts/spec.py sync   # copies ../inbound-app/openapi/openapi.yaml, or $INBOUNDR_SPEC
.venv/bin/python scripts/unasync.py
.venv/bin/pytest && .venv/bin/mypy
```

`tests/test_spec.py` fails if an operation in the spec has no client method, so a new API route shows up as a failing test until the client covers it. The generator needs Python 3.11+.

## Webhook signatures

The signing scheme isn't part of the OpenAPI spec. It is written out at the top of `tests/test_webhooks.py`, and those tests sign independently of the SDK's code. Changing the scheme is a breaking change.

## Releasing

1. Bump `__version__` in `src/inboundr/_version.py`.
2. Merge to `main`.
3. Tag `v<version>` and push the tag.

CI runs the tests on Python 3.10 to 3.14, checks that the tag matches `_version.py`, builds the package and publishes it to PyPI through trusted publishing (repository `inboundr-net/inboundr-python`, workflow `ci.yml`), so there is no PyPI token.
