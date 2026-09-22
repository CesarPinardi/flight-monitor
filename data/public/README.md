# Dados públicos

Histórico sanitizado para consumo pelo frontend e publicação no GitHub Pages.

Não colocar aqui credenciais, `chat_id`, dados pessoais ou respostas brutas com informação sensível.

O comando grava `data/public/data.json` com `schema_version`, estado da execução, fuso de apresentação `America/Sao_Paulo`, rotas, ofertas, comparações compatíveis e histórico diário sanitizado. O histórico representa menor preço comparável por rota em cada consulta; não representa uma oferta específica.

Preço, taxas, bebê de colo, bagagem e inventário seguem o contrato da fonte; o arquivo não promete disponibilidade de compra. O frontend consome somente este JSON.
