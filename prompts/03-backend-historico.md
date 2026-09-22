Implemente o processamento do monitor usando o cliente de API validado.

Crie um comando que carregue configuração, verifique orçamento, consulte GRU/VCP × MCO/FLL/MIA, normalize ofertas, persista histórico/estado em JSON e gere dados públicos para o frontend.

Priorize seis buscas básicas diárias, até 186 em mês de 31 dias. Chamadas extras têm limite explícito e devem parar quando o orçamento acabar.

Exija escritas atômicas, esquema versionado, identificador estável, preço/moeda/rota/passagem/segmentos/fonte/horário UTC, distinção entre oferta completa e pendente, comparação somente entre ofertas compatíveis, bagagem desconhecida não incluída, preservação do último resultado válido, estados de sucesso/falha/cota/dados antigos, fuso America/Sao_Paulo na apresentação e prevenção de concorrência/duplicatas.

Crie modos dry-run e fixtures sem chamadas externas. Teste limites, falhas parciais, persistência e interpretação do total. Documente comandos. Não ative agendamento.
