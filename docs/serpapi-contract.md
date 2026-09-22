# Contrato SerpApi / Google Flights

## Consulta implementada

`SerpApiClient` usa somente biblioteca padrão Python e chama `GET https://serpapi.com/search.json` com:

| Campo | Valor da busca de validação |
| --- | --- |
| `engine` | `google_flights` |
| `departure_id` | `GRU` |
| `arrival_id` | `MCO` |
| `outbound_date` | `2027-03-05` |
| `return_date` | `2027-03-14` |
| `type` | `1` (ida e volta) |
| `travel_class` | `1` (econômica) |
| `adults` | `2` |
| `infants_on_lap` | `1` |
| `children` | `0` |
| `infants_in_seat` | `0` |
| `currency` | `BRL` |
| `gl` / `hl` | `br` / `pt-BR` |

Datas, passageiros, classe e moeda vêm de `config/search.json` via `SearchRequest.from_config`.

## Resposta normalizada

`SerpApiClient.search` retorna JSON seguro para histórico:

- `request`: parâmetros usados, sem `api_key`;
- `search_id` e links retornados pela API;
- `flights`: resultados de `best_flights` e `other_flights`;
- cada voo: preço, segmentos, duração, paradas e presença de tokens;
- `price_contract`: campos de escopo do preço;
- `availability_contract`: campos de presença de segmentos e verificação de inventário;
- `warnings`: incertezas que não podem ser inferidas.

O cliente não grava nem retorna a chave da API. Tokens de retorno e reserva só são expostos como presença booleana na resposta normalizada. Métodos separados aceitam tokens para chamadas explícitas.

## Preço e disponibilidade

A documentação oficial define `price` como inteiro na moeda selecionada. Ela não confirma, no campo retornado, se o valor é total do grupo, inclui bebê de colo ou inclui todas as taxas. Por isso o contrato usa:

- `scope: "unknown"`;
- `includes_taxes: null`;
- `includes_infants_on_lap: null`;
- `group_total_verified: false`.

O preço persistido pelo monitor é normalizado por passageiro pagante. Bebê de colo não entra no divisor porque a fonte não confirma sua inclusão; escopo original, taxas e total do grupo continuam desconhecidos.

`segments_available` significa somente que cada segmento retornado tem dados de aeroporto de partida e chegada. Não significa assento, inventário, tarifa ainda vendável ou reserva confirmada. A reserva não é executada.

## Retorno e reserva

A documentação oficial informa:

- `departure_token` seleciona um voo de ida para buscar opções de retorno;
- `booking_token` busca opções de emissão para voos selecionados;
- tokens não são usados juntos;
- cada chamada consome o orçamento local;
- nenhuma chamada de reserva é automática.

O fluxo completo de ida e volta pode exigir uma segunda busca explícita com `returning_flights`. A API de booking retorna resposta bruta porque opções de emissão exigem validação posterior e não fazem parte do histórico de preços.

## Cota e custo

Na data deste estágio, a página oficial de preços informa plano Free de 250 buscas por mês e throughput de 50 por hora. A API de conta é gratuita e não conta na cota, mas ainda não é usada pelo projeto.

`CallBudget` limita todas as chamadas do cliente. Padrão: 250 chamadas por instância. O contador é conservador: incrementa antes da rede, incluindo falha de transporte. Não há retry automático, renovação automática, compra ou upgrade pago no código.

O plano da conta pode ter configuração de renovação antecipada automática. Ela deve permanecer desativada no painel SerpApi; o código não consegue alterar essa configuração.

## Fontes oficiais consultadas

- [Google Flights API](https://serpapi.com/google-flights-api)
- [SerpApi pricing](https://serpapi.com/pricing)
- [SerpApi Account API](https://serpapi.com/account-api)

## Viabilidade atual

Viável tecnicamente com `SERPAPI_API_KEY` local ou em Secret. Custo e cota dependem da conta. A validação real GRU-MCO permanece pendente quando a variável não está presente.
