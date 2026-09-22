# Workflows

`monitor.yml` executa consulta diária fora da virada da hora e publicação Pages. Também aceita execução manual.

O workflow não é acionado por `push`; commits automáticos de estado não criam loop. Sem `SERPAPI_API_KEY`, não consulta nem inventa preço. Sem secrets Telegram, não declara alertas ativos.

Detalhes, pausa, cota, persistência e URL esperada: [`docs/deployment.md`](../../docs/deployment.md).
