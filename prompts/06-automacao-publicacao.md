Conclua implantação gratuita com GitHub Actions, GitHub Pages e Telegram.

Leia as etapas anteriores. Configure workflow diário fora da virada da hora e `workflow_dispatch`, runner Linux, timeout, permissões mínimas e concurrency. Use secrets SERPAPI_API_KEY, TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID. Publique frontend e JSON no Pages.

Resolva persistência: o runner é temporário; histórico, orçamento e estado de alertas devem sobreviver. Persista apenas dados sanitizados, evite loops de commits e não dependa somente de artifacts expiráveis.

Antes de ativar: fixtures locais; execução real com poucas chamadas; validação de passageiros/preço; painel; uma notificação sem duplicar; auditoria de segredos em arquivos/site/logs; consumo e parada ao atingir cota.

Está autorizado publicar o painel e ativar alertas no chat configurado, sem contratar serviços. Se faltar credencial, conclua o possível e informe pendências; não declare ativo sem dependências.

Documente pausa, execução manual, filtros, falhas, consumo, atrasos, desativação por inatividade e encerramento após a data da viagem. Entregue URL, estado real e validação separando testes locais de consultas reais.
