# Decisões iniciais

## Sem servidor ou banco externo

GitHub Actions gera JSON sanitizado. GitHub Pages serve frontend estático. Isso mantém custo e operação baixos.

## Sem dependência Python no estágio 1

A estrutura inicial usa biblioteca padrão. Dependências entram somente quando integração real exigir.

## Segredos fora do repositório

Chave SerpApi e credenciais Telegram ficam em ambiente local ou GitHub Secrets. `.env.example` contém somente nomes de variáveis.

## Preço sem inferência

O sistema não multiplica nem estima preço para bebê, taxas ou grupo. O estágio 2 precisa validar o significado do preço retornado pela SerpApi.

## Execução desativada

O workflow diário não é ativo nesta etapa. Consultas e notificações só podem ser ligadas depois de validar integração, orçamento e dados.
