# Testes

`test_serpapi.py` cobre parâmetros da consulta, normalização, tokens, erros, chave ausente e limite de orçamento. `test_monitor.py` cobre rotas de ida e volta em fixtures, limite mensal, quota, falha parcial, preservação de dado antigo, duplicata diária, schema público, lock e alerta local. `test_telegram.py` cobre escape, deduplicação, queda, teto, persistência de falha, confirmação e resposta Telegram.

Execute com `PYTHONPATH=src python -m unittest discover -s tests -v`.

`tests/fixtures/google_flights_gru_mco.json` é sanitizada. Testes nunca chamam SerpApi ou Telegram durante importação ou execução padrão.
