# Flight Monitor

Monitor pessoal de passagens em dinheiro, com histórico público e alertas opcionais pelo Telegram.

## Estado atual

Estágio 6 concluído: workflow diário, execução manual, persistência sanitizada e publicação Pages ativas. Consulta real e alertas dependem de secrets.

- Consulta real: pendente quando `SERPAPI_API_KEY` não está disponível.
- Nenhum segredo, `chat_id` ou dado pessoal foi salvo.
- Workflow remoto ativo; execução manual confirmou publicação Pages.
- Nenhum secret GitHub está configurado; consulta real, alertas e dados atualizados estão pendentes.
- Nenhum preço é inventado ou apresentado como resultado real.

## Escopo fixo

| Campo | Valor |
| --- | --- |
| Ida | 05/03/2027 |
| Volta | 14/03/2027 |
| Origens | GRU, VCP |
| Destinos | MCO, FLL, MIA |
| Passageiros | 2 adultos e 1 bebê de 1 ano no colo |
| Cabine | Econômica |
| Moeda | BRL |
| Tipo | Só ida por trecho; `trip_leg` aceita `outbound`, `return` ou `both` |
| Custo | Zero |

## Estrutura

```text
config/                  Configuração pública da busca
data/public/             Dados seguros para publicação no Pages
docs/                    Decisões e roadmap
frontend/                Site estático HTML/CSS/JavaScript
src/flight_monitor/      Código Python
tests/                   Testes e fixtures sanitizadas
.github/workflows/       Workflow diário e publicação GitHub Pages
prompts/                 Instruções dos estágios do projeto
```

## Stack e limites

- Python e biblioteca padrão no estágio inicial.
- SerpApi Free / Google Flights, condicionado à validação da conta e da cota.
- JSON como formato de configuração e dados publicados.
- HTML, CSS e JavaScript puro no frontend.
- GitHub Actions e GitHub Pages nos estágios de automação e publicação.
- Telegram Bot API somente depois de configurar segredos no GitHub.
- Sem servidor HTTP, banco externo, login ou framework frontend.

## Configuração local

1. Copie `.env.example` para `.env`.
2. Preencha segredos somente localmente ou nos Secrets do GitHub.
3. Não faça commit de `.env`.

O cliente usa `SERPAPI_API_KEY`, timeout de 30 segundos e orçamento local padrão de 250 chamadas por instância. Testes usam fixture e nunca chamam rede.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Processamento

O comando consulta os seis itinerários configurados (`GRU/VCP` × `MCO/FLL/MIA`) como trechos únicos. `trip_leg` define `outbound` (ida), `return` (volta) ou `both` (os dois); cada consulta usa `type=2` e grava o preço daquele trecho. Chamadas extras exigem `extra_calls_limit` positivo na configuração e `--extra-route ORIGEM:DESTINO`. O comando não agenda execução.

```bash
# Sem chave: nunca faz chamada real. Consulta fixtures disponíveis.
PYTHONPATH=src python -m flight_monitor --dry-run

# Consulta real. Exige SERPAPI_API_KEY no ambiente.
SERPAPI_API_KEY=... PYTHONPATH=src python -m flight_monitor

# Consulta fixtures e nunca envia Telegram.
PYTHONPATH=src python -m flight_monitor --dry-run --local
```

Saídas atômicas: `data/history.json`, `data/state.json` e `data/public/data.json`. O lock `data/.monitor.lock` bloqueia concorrência. A segunda execução no mesmo dia local (`America/Sao_Paulo`) é ignorada; use `--force` somente para execução manual explícita.

Cada oferta tem identificador estável, rota, trecho, passageiros, preço por passageiro pagante, moeda, segmentos, fonte e `observed_at_utc`. Oferta pendente não entra em comparação. Bagagem desconhecida permanece não incluída. Falhas preservam último resultado válido e marcam dados antigos.

## Frontend local

O painel lê somente `data/public/data.json`, sem chamar SerpApi ou Telegram. Os caminhos são relativos para funcionar no repositório e em GitHub Pages. Sem esse arquivo, o painel mostra estado de dados indisponível e não exibe preço fictício.

```bash
python -m http.server 8000
```

Abra <http://127.0.0.1:8000/frontend/>. Gere dados sanitizados antes, se necessário, com `PYTHONPATH=src python -m flight_monitor --dry-run --local` usando fixtures. O histórico público é o menor preço comparável por rota em cada consulta diária; não é uma oferta específica nem confirmação de disponibilidade.

Contrato completo: [`docs/serpapi-contract.md`](docs/serpapi-contract.md).

## Próximos estágios

1. Criar estrutura e repositório — concluído.
2. Validar contrato e integração SerpApi — cliente e testes concluídos; consulta real pendente sem chave.
3. Implementar histórico e normalização — concluído; execução real segue pendente sem chave.
4. Implementar alertas Telegram — concluído; envio real depende de credenciais.
5. Implementar painel GitHub Pages — concluído; dados reais dependem de consulta válida.
6. Ativar execução diária e publicação — Pages ativa; secrets e consulta real pendentes.

## Custo

O projeto não habilita renovação paga. A conta SerpApi deve manter renovação antecipada automática desativada no painel. Cotas, limites e termos da SerpApi, GitHub e Telegram precisam ser confirmados antes de ativar automação.

## Alertas Telegram

Monitor lê `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` somente do ambiente. Nunca grave valores em JSON, frontend, logs ou Git. Sem credenciais, execução termina com `telegram.status=not_configured` e mantém alertas pendentes.

1. No Telegram, abra `@BotFather`, use `/newbot` e guarde token apenas em segredo local ou GitHub Secret.
2. Abra conversa privada com bot e envie `/start`. Bot não inicia conversa sozinho.
3. Obtenha `chat_id` por meio seguro, como `getUpdates` após `/start`, sem gravar resposta. Use somente chat configurado.
4. Exporte variáveis no ambiente de execução. Não coloque token em comando se shell history for persistente.

Alertas agrupam melhor oferta por rota. Primeira execução válida alerta; depois, só queda comparável de pelo menos 5%. `alert_price_ceiling` opcional limita alerta por teto na moeda configurada. Baseline, deduplicação, falha persistente, quota e recuperação ficam em `data/state.json`; não vão para `data/public/data.json`.

Mensagem usa HTML escapado, timeout de 10 segundos e só confirma alerta após resposta Telegram com `ok=true` e `message_id`. Preço só é chamado confirmado quando fonte prova total do grupo, taxas e bebê; caso contrário, alerta mostra incertezas. O alerta inclui rota, datas, preço informado, passageiros, escalas, duração, horários e link quando disponível.

## Automação e publicação

Workflow, persistência, auditoria, pausa e operação estão documentados em [`docs/deployment.md`](docs/deployment.md). O workflow grava somente histórico, estado e JSON público sanitizados; não depende apenas de artifacts.
