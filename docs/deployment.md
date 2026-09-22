# Execução e publicação

`.github/workflows/monitor.yml` executa diariamente às 10:17 UTC (07:17 em São Paulo quando UTC−3) e aceita `workflow_dispatch`. Usa `ubuntu-latest`, timeout de 10 minutos, concorrência por ref e permissões mínimas para conteúdo, Pages e OIDC.

## Secrets

Configure no repositório, sem gravar valores em arquivos:

- `SERPAPI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Sem `SERPAPI_API_KEY`, workflow apenas valida e publica painel sem dados novos. Sem credenciais Telegram, consulta pode atualizar dados, mas alertas ficam `not_configured`; não são considerados ativos.

## Persistência

Após consulta, workflow audita e faz commit somente de:

- `data/history.json`
- `data/state.json`
- `data/public/data.json`

Esses arquivos não contêm segredos. O estado inclui orçamento, baselines e deduplicação de alertas. O workflow não dispara em `push`, usa `[skip ci]` e só persiste na branch padrão, evitando loop de commits. Artifacts servem apenas para a implantação; histórico não depende deles.

## Pages

O artifact contém `frontend/` e, quando existir, `data/public/data.json` em `data/public/data.json`. O painel usa caminho relativo e mostra indisponibilidade quando JSON não existe. URL publicada: <https://cesarpinardi.github.io/flight-monitor/>. Execução confirmada em 22/09/2026; painel está sem dados novos enquanto `SERPAPI_API_KEY` faltar.

## Operação

Execução manual:

1. Abra Actions, workflow `Flight Monitor`, `Run workflow`.
2. Para teste inicial, escolha `calibration`. Essa opção faz somente uma busca GRU–MCO e não envia Telegram.
3. Use `full` somente após validar preço, passageiros, taxas e escopo.
4. Use branch padrão.
5. Confira resumo, orçamento e `telegram.status` no resultado.

O comando ignora segunda execução no mesmo dia local. `--force` existe apenas para operação local explícita. Cota, falhas e dados antigos aparecem no estado; não há retry automático. Ao atingir limite, novas consultas param. Para pausar, desative workflow ou remova secrets; para encerrar após 14/03/2027, desative workflow e mantenha painel/histórico publicados.

## Validação local

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m flight_monitor --dry-run --local
PYTHONPATH=src python scripts/audit_sanitized_data.py \
  data/history.json data/state.json data/public/data.json
```

Fixtures não consomem SerpApi nem enviam Telegram. Consulta real e envio Telegram só ocorrem quando secrets existem no ambiente autorizado.
