# E5 tokenizer (weights excluded)

`tokenizer.json` is copied from `intfloat/multilingual-e5-small`, revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, without modification:

https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/tokenizer.json

SHA-256: `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`.
Upstream model license: MIT. Only the 17 MB tokenizer is included; no embedding weights.

The corpus builder uses `tokenizers==0.21.4`, disables truncation and padding, and
counts `passage: ` plus `<s>` / `</s>` against the 512-token limit. Keeping this file
in the repository makes corpus generation and tests independent of network access.
