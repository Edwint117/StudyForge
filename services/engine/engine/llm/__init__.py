"""LLM task contracts: structured-output models, API JSON schemas and versioned prompt templates (doc 06 §2/§5).

The gateway (``packages/llm-gateway`` / engine adapters) sends ``schemas/<task>.v<N>.json`` as
``output_config.format`` and validates the reply again with the pydantic model named in the prompt's front matter.
"""
