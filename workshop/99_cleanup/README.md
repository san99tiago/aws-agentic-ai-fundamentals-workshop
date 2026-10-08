# Módulo 99 · 🧹 Limpieza

Elimina Runtime, Harness, Gateway (+targets), Knowledge Base y Guardrail creados en los notebooks.

```bash
DRY_RUN=true poetry run python workshop/99_cleanup/99_cleanup.py   # ver qué se borra
poetry run python workshop/99_cleanup/99_cleanup.py                # borrar
make destroy                                                       # + stacks CDK
```

# LICENSE

Copyright 2026 Santiago Garcia Arango
