# Decisões iniciais

## Sem servidor ou banco externo

GitHub Actions gera JSON sanitizado. GitHub Pages serve frontend estático. Isso mantém custo e operação baixos.

## Sem dependência Python no estágio 1

A estrutura inicial usa biblioteca padrão. Dependências entram somente quando integração real exigir.

## Segredos fora do repositório

Chave SerpApi e credenciais Telegram ficam em ambiente local ou GitHub Secrets. `.env.example` contém somente nomes de variáveis.

## Preço por passageiro

O sistema normaliza o preço para passageiro pagante. Não estima valor para bebê de colo, taxas ou total do grupo; o estágio 2 precisa validar o significado do preço retornado pela SerpApi.

## Contrato SerpApi explícito

O cliente envia adultos, bebê no colo, classe, moeda, datas e tipo de viagem conforme parâmetros oficiais. A resposta marca escopo do preço, inclusão de taxas, inclusão do bebê e inventário como desconhecidos quando a API não os prova. Segmento presente não equivale a disponibilidade para compra.

O itinerário ativo é multi-cidade/open-jaw: ida e volta têm aeroportos configuráveis e não exigem a mesma companhia. O limite permanece em seis buscas básicas por execução.

## Orçamento sem renovação paga

Todas as chamadas do cliente passam por `CallBudget`, com limite padrão de 250 por instância e sem retry automático. O código não habilita upgrade ou renovação. Renovação antecipada automática precisa ficar desativada na conta SerpApi.

## Execução e publicação

O workflow diário usa cron fora da virada da hora, `workflow_dispatch`, runner Linux, timeout, concorrência e permissões mínimas. Não dispara em `push`, para evitar loop quando persiste JSON. Histórico, orçamento e estado de alertas ficam em JSON sanitizado versionado; artifact Pages não é fonte de persistência. Sem secrets necessários, workflow não inventa consulta nem declara alerta ativo.

## Histórico e publicação JSON

O estágio 3 grava histórico, estado e dados públicos em JSON com `schema_version: 1`. Cada execução usa lock exclusivo e cada arquivo usa escrita temporária, `fsync` e `os.replace`. A chave da oferta usa campos canônicos da busca, rota, preço e segmentos; índice da resposta não participa do identificador.

O limite básico é seis consultas por execução e 186 por mês. Chamadas extras exigem limite explícito na configuração e ficam sob teto mensal de 250 chamadas. Execução repetida no mesmo dia local é ignorada. Falha ou quota não apaga a última oferta válida; painel marca dado antigo. Fixtures e `--dry-run` não consomem quota nem fazem rede.

## Alertas Telegram

Cliente usa biblioteca padrão, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, POST com timeout de 10 segundos e confirmação `ok=true` mais `message_id`. Token nunca entra em payload persistido, saída, frontend ou repositório.

Cada execução compara melhor oferta completa por rota. Primeira execução válida gera alerta; execuções seguintes exigem queda de pelo menos 5% comparável ou travessia de `alert_price_ceiling`. Alertas ficam agrupados em uma mensagem e têm chave persistente. Falha alerta após duas execuções consecutivas; quota alerta na primeira ocorrência. Recuperação exige execução posterior sem condição. Estado só marca envio após confirmação Telegram. `--dry-run` e `--local` atualizam baseline sem envio.

## Painel público

O frontend fica em HTML, CSS e JavaScript puro. Ele lê apenas `data/public/data.json` por caminho relativo, usa `textContent` e links HTTPS validados para inserir dados no DOM, e não contém credenciais, analytics, chamadas SerpApi ou Telegram.

O JSON público inclui `history.kind = daily_route_minimum`. Cada registro guarda menor preço confirmado e comparável por rota em uma execução. Isso deixa explícito que histórico não é oferta específica nem disponibilidade de compra. Falhas preservam ofertas anteriores com marcador `stale`.
