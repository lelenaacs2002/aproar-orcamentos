# APROAR Engenharia — Radar de Orçamentos

Primeiro MVP em **Python + Streamlit**, com leitura real do Trello e sem escrita no quadro.

## O que esta versão faz

- lê listas, cartões, membros, prazos, campos personalizados e atividades recentes do board;
- identifica os engenheiros/supervisores conhecidos;
- organiza as demandas em:
  - **Cobrar Engenharia**;
  - **Conferir retorno**;
  - **Pronto para elaborar**;
  - **Aguardar terceiros**;
  - **Em produção**;
- mantém o prazo original do Trello;
- calcula atraso e, quando há histórico de movimentação disponível, tempo na etapa atual;
- distingue espera de Engenharia de espera de cliente/fornecedor/especialista;
- usa uma única chamada de atividades do board, evitando consultar comentários cartão por cartão;
- não grava nada no Trello nesta fase.

## Regra mais importante

Por padrão, `TRUST_TRELLO_READY_LIST = false`.

Isso significa que um cartão em **Para Elaborar Orçamento** não é liberado automaticamente como "Pronto" apenas porque a automação do board o moveu para lá após `Informações preenchidas? = Sim`. Nesta primeira fase ele cai em **Conferir retorno**.

Se futuramente for criado no Trello um campo com nome semelhante a `Levantamento conferido`, `Conferido por Orçamentos` ou `Liberado para elaborar`, o código já consegue reconhecê-lo como gate manual.

## 1. Criar o repositório no GitHub

Crie um repositório novo, por exemplo:

`aproar-orcamentos`

Envie todos os arquivos desta pasta, **exceto qualquer arquivo real `secrets.toml`**. O `.gitignore` já protege esse nome.

## 2. Configurar o Trello

Você precisará de:

- API Key do Trello;
- Token do Trello com acesso ao board;
- board `TX8hGvmI`.

Use `.streamlit/secrets.toml.example` somente como modelo. As credenciais reais ficam nos **Secrets do Streamlit Community Cloud** e nunca no GitHub.

## 3. Rodar localmente

Crie localmente `.streamlit/secrets.toml` a partir do exemplo e preencha as credenciais.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

## 4. Publicar no Streamlit Community Cloud

1. New app.
2. Selecione o repositório GitHub.
3. Main file: `app.py`.
4. Em **Settings > Secrets**, cole as variáveis do `secrets.toml.example` com os valores reais.
5. Deploy.

## Como o Radar classifica nesta fase

### Cobrar Engenharia

Tende a receber cartões em `Solicitados` quando falta, por exemplo:

- responsável de Engenharia;
- registro da visita;
- confirmação de informações preenchidas;
- levantamento ainda pendente.

### Conferir retorno

Recebe de forma conservadora cartões que:

- estão em `Para Elaborar Orçamento` sem gate manual confiável;
- estão com `Informações preenchidas? = Sim`, mas ainda precisam de conferência;
- têm como último comentário reconhecido uma resposta de um dos engenheiros conhecidos.

### Pronto para elaborar

Só entra automaticamente aqui quando existir um campo manual no Trello semelhante a:

- `Conferido por Orçamentos`;
- `Levantamento conferido`;
- `Liberado para elaborar`.

Como alternativa temporária, `TRUST_TRELLO_READY_LIST = true` faz a lista `Para Elaborar Orçamento` ser considerada suficiente, **mas não é recomendado para o processo descrito pela equipe**.

### Aguardar terceiros

A lista `Solicitados – Pendências Cliente` não vira atraso da Engenharia. O painel também tenta reconhecer referências explícitas a fornecedor/prestador/especialista.

## Limitação consciente desta V1

Ainda não existe estado próprio persistente da plataforma para:

- última cobrança feita pela Laisa;
- data em que um retorno foi conferido;
- devolução de pendência pelo Orçamentos;
- aceite manual do levantamento;
- responsável atribuído pela plataforma.

Esses pontos serão a **V2**, com banco próprio (PostgreSQL/Supabase) e event log. Só depois disso a plataforma deve escrever comentários/movimentações no Trello, usando IDs de eventos para impedir duplicações e ciclos de sincronização.

## Próxima etapa recomendada

Adicionar duas tabelas próprias:

- `orcamento_review_state`: estado atual de conferência por cartão;
- `orcamento_event_log`: histórico de cobranças, respostas, devoluções e aceites.

Assim `Pronto para elaborar` passa a depender de uma ação humana dentro da plataforma, exatamente como o processo desejado.
