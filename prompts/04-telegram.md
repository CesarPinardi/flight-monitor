Implemente alertas Telegram no `flight-monitor`.

Use `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` por variáveis de ambiente. Nunca grave segredos em JSON, frontend, logs ou repositório. Documente BotFather, início da conversa e obtenção segura do chat_id.

Alerte na primeira execução válida; depois, queda de pelo menos 5% comparável; e teto opcional. Agrupe oportunidades, evite duplicatas e avise uma vez sobre falhas persistentes/cota esgotada e recuperação. Persista estado.

Inclua rota/datas, preço total confirmado para 2 adultos e bebê, escalas/duração, diferença, horário, link e incertezas. Use timeout, escape, confirmação após envio e modo local sem envio.

Está autorizado um único teste no chat configurado se as credenciais existirem. Não envie a outros destinatários. Se faltar configuração, conclua código e documente.
