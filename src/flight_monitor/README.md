# Código Python

`serpapi.py` contém cliente Google Flights sem dependências externas, validação de busca, orçamento central e normalização segura.

`monitor.py` carrega configuração, executa rotas de ida, volta e pacotes combinados, processa fixtures em `--dry-run`, persiste histórico/estado e publica `data/public/data.json`. `storage.py` usa lock exclusivo e `os.replace` com `fsync`.

`telegram.py` monta alertas agrupados, compara baseline persistente, escapa HTML e envia somente quando `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` existem. `--dry-run` e `--local` não enviam. Confirmação exige resposta Telegram válida.

Nenhum módulo faz chamada de rede durante importação. A chave vem de `SERPAPI_API_KEY` e nunca entra na resposta normalizada.
