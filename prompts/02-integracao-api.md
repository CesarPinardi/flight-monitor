Implemente e valide a integração com a SerpApi para o projeto `flight-monitor`.

Leia README, instruções e configuração. Consulte a documentação oficial atual para confirmar cota gratuita, parâmetros do Google Flights, adultos/bebê no colo, moeda BRL, ida e volta, significado do preço e eventuais chamadas de retorno/reserva.

Use `SERPAPI_API_KEY` por variável de ambiente. Não peça a chave no chat. Implemente cliente Python com timeout, erros e respostas normalizadas.

Comece com uma consulta real GRU–MCO, ida 05/03/2027 e volta 14/03/2027, 2 adultos e 1 bebê no colo. Valide se o preço é do grupo completo, inclui bebê/taxas e se os segmentos estão disponíveis. Não multiplique preços por suposição; marque incertezas.

Crie controle central de orçamento para todas as chamadas e interrompa ao atingir o limite. Não habilite renovação paga. Não faça chamadas em imports/testes; use fixtures sanitizadas nos testes.

Se faltar chave, implemente tudo possível e informe a validação real pendente. Documente o contrato de dados e viabilidade antes de avançar.
