# Flight Monitor

Monitor pessoal de passagens em dinheiro, com histórico público e alertas opcionais pelo Telegram.

## Estado atual

Estágio 1 concluído: repositório e estrutura inicial criados.

- Nenhuma consulta à SerpApi foi executada.
- Nenhuma mensagem Telegram foi enviada.
- Nenhum segredo, `chat_id` ou dado pessoal foi salvo.
- Nenhum workflow ativo foi publicado.
- Nenhum preço foi inventado ou apresentado como resultado real.

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
| Tipo | Ida e volta, somente dinheiro |
| Custo | Zero |

## Estrutura

```text
config/                  Configuração pública da busca
data/public/             Dados seguros para publicação no Pages
docs/                    Decisões e roadmap
frontend/                Site estático HTML/CSS/JavaScript
src/flight_monitor/      Código Python
tests/                   Testes e fixtures sanitizadas
.github/workflows/       Templates de automação; nenhum ativo nesta etapa
prompts/                 Instruções dos estágios do projeto
```

## Stack e limites

- Python e biblioteca padrão no estágio inicial.
- SerpApi Free / Google Flights no próximo estágio, condicionado à validação da conta e da cota.
- JSON como formato de configuração e dados publicados.
- HTML, CSS e JavaScript puro no frontend.
- GitHub Actions e GitHub Pages nos estágios de automação e publicação.
- Telegram Bot API somente depois de configurar segredos no GitHub.
- Sem servidor HTTP, banco externo, login ou framework frontend.

## Configuração local

1. Copie `.env.example` para `.env`.
2. Preencha segredos somente localmente ou nos Secrets do GitHub.
3. Não faça commit de `.env`.

Nesta etapa, preencher variáveis não habilita consultas nem notificações. O cliente e os limites de orçamento serão implementados no estágio 2.

## Próximos estágios

1. Criar estrutura e repositório — concluído.
2. Validar contrato e integração SerpApi — pendente.
3. Implementar histórico e normalização — pendente.
4. Implementar alertas Telegram — pendente.
5. Implementar painel GitHub Pages — placeholder criado; dados reais pendentes.
6. Ativar execução diária e publicação — pendente, após validação.

## Custo

O projeto assume somente recursos gratuitos. Cotas, limites e termos da SerpApi, GitHub e Telegram precisam ser confirmados antes de ativar automação.
