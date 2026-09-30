"""Provider adapters and the routing logic that picks them (doc 06 §2–3, §6).

This package currently holds the pure routing layer: catalog, per-plan routing, circuit breakers and cost
controls. Concrete adapters (parse/, ocr/, stt/, embed/, llm/) are added in M4 and register under the ids used in
``catalog.CATALOG``.
"""
