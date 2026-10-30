# Arquivo Louquinha

> **🌐 Versão de teste no ar:** <https://arquivolouquinha.netlify.app>
>
> Este é um endereço **provisório**: a Netlify repassa as visitas para o site, que roda num PC pelo Tailscale Funnel (<https://desktop-saqgca0.tail463929.ts.net> também funciona). O domínio gratuito **`arquivolouquinha.eu.org`** já foi pedido e está **aguardando aprovação** do eu.org; quando for aprovado, o site muda para ele. Por enquanto, as contas novas são **aprovadas automaticamente**.

*Um arquivo de histórias.* Plataforma independente de publicação, organização e leitura de fanfics, inspirada no AO3. Nasceu do fandom Louquinha (Três Graças) e é aberta a outros fandoms. Feita para rodar leve num computador caseiro.

- **Visual:** tema azul-marinho, com cabeçalho, barra lateral e rodapé. Os títulos usam a fonte Lora e o texto usa Inter, ambas hospedadas no próprio site (`static/fonts/`). Os ícones são SVG embutidos (`core/templatetags/ui.py`). Não há capas: os cards são só texto.
- **Páginas Sobre, Termos de Uso e Contato:** são editadas pelo admin, em **Páginas planas** (Flat pages).

- **Stack:** Python 3.12, Django 5.2 com templates e HTMX (sem SPA), PostgreSQL (busca full-text), Redis + Celery e Docker Compose.
- **Idioma:** a interface é em português por padrão. Inglês aparece só se a pessoa escolher, no seletor do topo ou em Preferências.

## Situação das fases

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 | Docker (dev/prod), modelos, autenticação, admin, seed | ✅ |
| 2 | Publicar/ler obras e capítulos, imagens, pseudônimos, exclusão/exportação de conta | ✅ |
| 3 | Sistema de tags e wrangling | ✅ |
| 4 | Listagens, filtros e busca | ✅ |
| 5 | Kudos, hits, comentários, bookmarks, séries, coleções, mensagens privadas | ✅ |
| 6 | Produção: proxy, túnel, backups, scripts | ✅ |
| 7 | Teste de carga e ajustes | ✅ neste PC (repetir na máquina dedicada) |

## Pré-requisitos

- Docker Desktop (no Windows, com WSL2)
- Nada mais: Python, Postgres e Redis rodam dentro dos containers

## Primeiro uso (desenvolvimento)

Todos os comandos são rodados na pasta do projeto.

1. **(Opcional) Crie o `.env`.** Em desenvolvimento tudo funciona sem ele.
   ```sh
   cp .env.example .env
   ```
2. **Monte as imagens.** Isso baixa o Python, instala as dependências e leva alguns minutos na primeira vez.
   ```sh
   docker compose --profile dev build
   ```
3. **Suba o site.** As migrations rodam sozinhas ao subir o `web-dev`.
   ```sh
   docker compose --profile dev up
   ```
   Acesse <http://localhost:8000>. Para parar, use `Ctrl+C`, ou `docker compose --profile dev down` em outro terminal.
4. **Crie sua conta de admin**, em outro terminal:
   ```sh
   docker compose --profile dev exec web-dev python manage.py createsuperuser
   ```
   O admin fica em <http://localhost:8000/admin/>. Para entrar pelo site em `/conta/login/`, confirme o e-mail primeiro: o link aparece no terminal do `web-dev`, porque em desenvolvimento os e-mails não são enviados de verdade.
5. **(Opcional) Popule com dados falsos:**
   ```sh
   docker compose --profile dev exec web-dev python manage.py seed
   ```

## Comandos do dia a dia

| O que fazer | Comando |
|---|---|
| Rodar os testes | `docker compose --profile dev run --rm web-dev pytest` |
| Criar migrations depois de mudar um modelo | `docker compose --profile dev run --rm web-dev python manage.py makemigrations` |
| Abrir o shell do Django | `docker compose --profile dev exec web-dev python manage.py shell` |
| Ver os logs do worker (Celery) | `docker compose --profile dev logs -f worker-dev` |
| Apagar tudo, inclusive o banco | `docker compose --profile dev down -v` ⚠️ |

### Seed (dados falsos)

`python manage.py seed` cria usuários aprovados, fandoms, personagens, relacionamentos, tags livres (com sinônimos e metatags), obras com capítulos, séries, kudos, bookmarks e comentários. Ele serve para testar o desempenho com volume parecido com o real.

| Opção | Padrão | O que faz |
|---|---|---|
| `--users` | 200 | número de usuários |
| `--fandoms` | 25 | número de fandoms |
| `--freeforms` | 300 | tags livres geradas, além dos ~35 tropos fixos |
| `--works` | 3000 | número de obras |
| `--seed` | 42 | semente aleatória (o mesmo número gera os mesmos dados) |
| `--clear` | — | apaga antes os usuários do seed anterior (com as obras deles) e as tags sem uso |
| `--force` | — | permite rodar com `DEBUG` desligado ⚠️ |

- Os usuários do seed usam e-mails `@seed.invalid` e a senha `senha-de-teste-123`.
- Exemplo pequeno e rápido: `python manage.py seed --users 20 --works 100`.

### Traduções (português → inglês)

Os textos do código e dos templates são escritos em português. A tradução para inglês fica em `locale/en/LC_MESSAGES/django.po`.

1. Depois de criar ou mudar textos, atualize o arquivo de tradução:
   ```sh
   docker compose --profile dev run --rm web-dev python manage.py makemessages -l en --ignore=staticfiles
   ```
2. Preencha os `msgstr` vazios no `.po`, que são as traduções.
3. Compile. O site só usa o arquivo `.mo` compilado:
   ```sh
   docker compose --profile dev run --rm web-dev python manage.py compilemessages
   ```

Na imagem de produção, a compilação acontece sozinha no build.

## Contas e aprovação

- **Cadastro aberto, com aprovação manual.** A pessoa se cadastra, confirma ter 18 anos ou mais e confirma o e-mail. Enquanto um admin não aprovar, ela só acessa as páginas da própria conta.
- **Para aprovar:** no admin, abra **Usuários**, filtre por "aprovada: Não", selecione as contas e use a ação **Aprovar contas selecionadas**. A pessoa recebe um e-mail no idioma que escolheu.
- **Níveis de mídia:** todo autor novo começa no **Básico** (só avatar). A ação do admin muda o nível para **Imagens** (avatar e imagens dentro do texto). As obras não têm capa.
- Toda aprovação, recusa e mudança de nível fica registrada em **Moderação → Histórico de moderação**, que é só para leitura.
- **E-mails pré-aprovados:** no admin, em **Contas → E-mails pré-aprovados**, cadastre o e-mail de uma autora **antes** de ela criar a conta e, se quiser, já escolha o nível de mídia.
  - Quando ela se cadastrar com esse e-mail e **confirmar o e-mail**, a conta é aprovada sozinha, com o nível escolhido, e a aprovação vai para o histórico de moderação em seu nome.
  - A aprovação só acontece **depois da confirmação**, para ninguém usar o e-mail de outra pessoa.
  - Cada liberação vale **uma vez**.
  - Quem se cadastrar com outro e-mail continua aguardando a sua aprovação.
- **Configurações do site** (admin → **Core → Configurações do site**), que mudam sem reiniciar nada:
  - **"Aprovar todas as novas contas automaticamente":** a caixa de marcar mais forte.
    - Marcada: toda conta nova já nasce aprovada (nível Básico) e **entra sem confirmar o e-mail**. Serve enquanto o site não tem provedor de e-mail.
    - No histórico de moderação, essas aprovações aparecem com a nota "aprovação automática".
    - Um e-mail pré-aprovado ainda recebe o nível de mídia escolhido quando a pessoa confirmar o e-mail.
    - **Risco:** qualquer pessoa (ou robô) que achar o link cria conta e publica na hora, inclusive com o e-mail de outra pessoa. Acompanhe os avisos e as denúncias.
    - **Para desligar:** desmarque a caixa e clique em **Salvar**. Quem se cadastrar depois volta a aguardar a sua aprovação e a precisar confirmar o e-mail. As contas já aprovadas continuam aprovadas; para tirar alguém, use **Recusar contas selecionadas** em **Usuários**.
  - **"Aprovar novas contas automaticamente até":** é a **janela de cadastro aberto**.
    - Enquanto a data não passar, quem criar conta e **confirmar o e-mail** entra aprovado, no nível de mídia Básico, e pode publicar.
    - Ela fecha sozinha na data escolhida; para fechar antes, apague a data.
    - Durante a janela, a página de cadastro mostra "Cadastros abertos até…".
    - No histórico de moderação, essas aprovações aparecem com a nota "janela de cadastro aberto".
    - Um e-mail pré-aprovado tem prioridade sobre a janela, então vale o nível de mídia escolhido para ele.
  - **"Avisar destes e-mails a cada conta criada":** um e-mail por linha. A cada cadastro, quem estiver na lista recebe usuário, e-mail, data, situação e o link para a conta no admin. Os e-mails ficam só no banco, nunca no código.
  - **"Endereço direto do site":** quando preenchido (hoje, o `.ts.net`), a tela de **importar PDF** mostra um aviso: PDFs grandes podem passar do tempo limite do endereço provisório (Netlify), e o aviso dá o link direto para importar por lá. Apague o campo quando o site tiver domínio próprio, e o aviso some.
  - A janela e os avisos dependem de o site **enviar e-mails de verdade**. Sem provedor de e-mail configurado (`EMAIL_*` no `.env.prod`), os e-mails só aparecem no log, e a confirmação precisa ser feita pelo comando `verify_email`, que também respeita a janela e a pré-aprovação.
- `SIGNUP_OPEN=0` no `.env` fecha o cadastro.
- Segurança: senhas com Argon2, verificação em duas etapas opcional (TOTP) e bloqueio temporário após logins falhos (5 tentativas a cada 5 minutos por conta). O login com Google se ativa ao preencher `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.

## Obras

- **Publicar:** menu **Nova obra**. O formulário já inclui o primeiro capítulo. Cada obra ou capítulo pode ser salvo como **rascunho**, **publicado** ou **agendado**. O worker confere os agendamentos a cada minuto.
- **Editor:** duas abas no topo de cada caixa, como no AO3: **Texto formatado** (botões de formatação) e **HTML**. Vale para o texto do capítulo e também para resumo, notas e notas finais (nesses, a barra é mais enxuta). O navegador lembra a última aba escolhida. Em qualquer modo, o servidor passa o texto por uma lista branca de tags (`works/sanitize.py`): scripts, `onclick`, `javascript:` e estilos somem. Texto puro colado vira parágrafos.
- **Imagens no texto:** só autores no nível **Imagens**. Cada imagem é convertida para WebP, reduzida a até 1.600 px de largura e perde os metadados (GPS etc.).
  - Limites: 5 MB por arquivo e 100 MB por autor, ajustáveis no `.env`.
  - Imagens de outros sites são bloqueadas, porque permitiriam rastrear os leitores.
  - Se o autor voltar ao nível Básico, as imagens ficam ocultas, mas não são apagadas.
  - Imagens enviadas e não usadas em nenhum capítulo por 7 dias são apagadas às 4h.
- **Coautoria:** na edição da obra, convide pelo nome de usuário. A pessoa recebe um e-mail e aceita em **Convites**.
- **Leitura:**
  - Obras "só para logados" pedem login.
  - Obras Maduro/Explícito mostram um aviso para visitantes (uma vez por obra).
  - Quem marcou "esconder avisos" vê os avisos recolhidos.

## Importar obra do AO3 (PDF)

Em **Minhas obras → Importar obra (PDF do AO3)**, o autor envia o PDF que baixou da própria obra no AO3 (Download → PDF).

- **Reconhecido sozinho:**
  - Título, classificação, avisos, categorias, fandom, relacionamentos, personagens, tags livres, idioma e capítulos previstos/completa.
  - Resumo e notas da obra e as notas finais.
  - Cada capítulo ("Chapter N: Título") com resumo, notas e notas finais próprias.
  - Os **parágrafos**, pelo espaço vertical entre eles na página.
- **A obra entra como rascunho**, no pseudônimo padrão de quem importou. Nada fica público antes da revisão. A página de resultado mostra o que foi reconhecido e os avisos, com os botões **Revisar dados da obra**, **Ver como leitores verão** e **Descartar importação**.
- **Limites:**
  - PDF escaneado (foto das páginas) não tem texto.
  - Itálico e negrito podem se perder.
  - Séries e coleções do AO3 não são importadas.
  - Uma tag que já exista aqui com outro tipo é pulada, com aviso.
  - O tamanho máximo é 20 MB (`MAX_IMPORT_MB`) e há no máximo 10 importações por hora (`IMPORTS_PER_HOUR`).
  - Se o PDF não for do AO3, o texto inteiro vira um capítulo, com aviso.
- O código fica em `works/importer.py` (leitura do PDF) e em `works/services.py` (`create_imported_work`).

## Tags e wrangling

- **Tipos de tag:** Fandom, Relacionamento, Personagem e Tag livre. A tag nova que um autor digita nasce "sem decisão".
- **Wrangling** (menu, só para o grupo **Wranglers** e admins): no admin, selecione o usuário e use a ação **Dar papel de wrangler**. Na tela de wrangling dá para:
  - **Tornar canônica:** a tag passa a ser o nome oficial.
  - **Tornar sinônimo:** "Coffee Shop AU" → "Universo Alternativo - Cafeteria". Se a tag já era canônica, os sinônimos, as metatags e os fandoms dela passam para a nova.
  - **Metatag / subtag:** "Universo Alternativo" fica acima de "AU Cafeteria". O site bloqueia ciclos.
  - **Ligar a fandom:** personagens e relacionamentos aparecem na página do fandom.
- **Filtro hierárquico:** filtrar por uma canônica traz as obras com ela, com os sinônimos dela e com as subtags (em qualquer profundidade, com os sinônimos das subtags).
- Cada ação fica no **histórico de moderação**.
- O formulário de obra **sugere as canônicas** enquanto o autor digita. Digitar um sinônimo sugere a canônica dele.

## Busca e listagens

- **Obras** (menu): busca por texto (título, autor, tags e resumo) e os filtros incluir/excluir tags, classificação, avisos, categorias, idioma, completa, faixa de palavras e data de atualização. Ordena por atualização, publicação, kudos, acessos, bookmarks, comentários, palavras, título ou relevância. Mostra 20 por página.
- A busca **ignora acentos** ("cafe" acha "Café") e aceita **prefixos** ("padar" acha "padaria"). `-palavra` exclui.
- **Como é rápido:** as listagens leem a tabela `WorkListing`, com uma linha pronta por obra. Os filtros de tag usam um índice GIN sobre os ids canônicos e as metatags de cada obra, e cada busca leva 1–2 ms no banco.
- A tabela é atualizada pelo worker sempre que uma obra, um capítulo, um autor ou uma tag muda, e é reconstruída inteira às 3h30 como rede de segurança. Para reconstruir na mão:
  ```sh
  docker compose --profile dev exec web-dev python manage.py rebuild_listings
  ```
- **Limite por IP:** 60 buscas e 300 páginas por minuto. Passando disso, o site responde "Calma aí!" (429) por um minuto. Os valores ficam no `.env`: `RATE_LIMIT_SEARCH`, `RATE_LIMIT_GLOBAL`, `RATE_LIMIT_AUTOCOMPLETE`.

## Seus dados (LGPD)

Em **Preferências**:

- **Baixar uma cópia dos meus dados:** um arquivo JSON com a conta, os e-mails, os pseudônimos, as obras com todos os capítulos, os bookmarks, os comentários e os kudos.
- **Excluir minha conta:** pede o nome de usuário e a senha. Você escolhe o que acontece com as obras:
  - **Conta órfã:** as obras continuam no ar sob o nome `orphan_account`.
  - **Apagar:** as obras somem.
  - Em qualquer caso, obras com coautores continuam com eles.

## Produção

A produção roda num projeto Docker **separado do desenvolvimento** (`arq_prod`), com banco, Redis e volumes próprios. Assim os dados de teste do dev nunca se misturam com os reais. Todos os comandos usam o atalho `./scripts/prod.sh`, que é o `docker compose` já configurado. No Windows, rode os scripts pelo **Git Bash**.

```
visitante → (Cloudflare Tunnel) → Caddy → Gunicorn/Django → Postgres, Redis
                                         Celery worker (+ agendador)
                                         backup diário
```

### Primeira instalação

1. **Crie o `.env.prod`** com senhas aleatórias. O script não sobrescreve um que já exista.
   ```sh
   ./scripts/init-env-prod.sh
   ```
2. **Suba tudo.** Esse comando monta as imagens, roda as migrations e inicia os serviços:
   ```sh
   ./scripts/deploy.sh
   ```
3. **Crie o admin:**
   ```sh
   ./scripts/prod.sh exec web python manage.py createsuperuser
   ```
4. Acesse <http://localhost:8080>.
5. Para publicar na internet, siga o [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

### Dia a dia

| O que fazer | Comando |
|---|---|
| Atualizar o site (backup, código novo, build, migrations e reinício) | `./scripts/deploy.sh` |
| Ver a saúde: serviços, RAM, CPU, banco, disco e backups | `./scripts/status.sh` |
| Fazer um backup agora | `./scripts/backup-now.sh` |
| Restaurar um backup | `./scripts/restore.sh daily/2026-10-30_030000` |
| Ver os logs | `./scripts/prod.sh logs -f web` |
| Parar tudo (os dados ficam) | `./scripts/prod.sh down` |

O detalhe técnico fica na página <http://localhost:8080/status/>, visível só para a equipe.

### Backups

- **Automático, todo dia às 3h** (`BACKUP_TIME`). Inclui o banco (`pg_dump`) e a mídia (avatares e imagens).
- Ficam em `backups/daily/` (os **7** últimos) e `backups/weekly/` (os **4** últimos, um por semana).
- Cada backup é uma pasta com `db.dump`, `media.tar.gz` e o arquivo `COMPLETO`, que só é criado quando tudo terminou.
- **Cópia para fora da máquina** (recomendado): um backup no mesmo disco não protege se o disco morrer.
  - **HD externo:** `BACKUP_COPY_ENABLED=1` e `BACKUP_COPY_DIR=E:/backups-arq`. Depois de mudar, rode `./scripts/deploy.sh`.
  - **Nuvem:** configure o rclone em `deploy/rclone/rclone.conf` e defina `RCLONE_REMOTE=meudrive:arq-backups`.
- **Restaurar:** o `./scripts/restore.sh` para o site, restaura o banco e a mídia, sobe tudo de novo e reconstrói as listagens.
- O container de backup tem um healthcheck: ele fica **unhealthy** se passar de 26 h sem um backup completo.

### O que o Caddy faz

- Serve `/static/` (com cache de 1 ano, porque os arquivos têm hash no nome) e `/media/` direto do disco, sem passar pelo Django.
- Adiciona os cabeçalhos de segurança: CSP, `nosniff`, `X-Frame-Options` e `Referrer-Policy`.
- Escuta só em `127.0.0.1:8080`. Ninguém da rede alcança o site a não ser pelo túnel.

### Volta sozinho depois de reiniciar o PC

- Todos os serviços têm `restart: unless-stopped` e healthcheck.
- O Docker Desktop precisa abrir com o Windows: em **Settings → General**, marque "Start Docker Desktop when you sign in".
- O ajuste de reinícios do Windows Update e de energia fica no `docs/SERVIDOR.md`, que será escrito na migração para a máquina dedicada.

## Publicar na internet — protótipo neste PC (Tailscale Funnel)

É assim que o site está no ar agora, de graça, enquanto não existe o servidor próprio. O **Tailscale Funnel** cria um endereço HTTPS público (`https://<nome-do-pc>.<sua-rede>.ts.net`) que leva até o Caddy deste PC. Ele **não abre portas no roteador** e **não mostra o IP da sua casa**. O PC precisa ficar ligado e acordado, ou o site sai do ar.

Rode os comandos no **Git Bash**, na pasta do projeto. Os que pedem digitação (senha) vão no **PowerShell**.

### 1. Instalar a produção

```sh
./scripts/init-env-prod.sh      # cria o .env.prod com senhas aleatórias (só na primeira vez)
./scripts/deploy.sh             # monta as imagens, migrations e sobe tudo em http://localhost:8080
```

### 2. Criar a sua conta de admin

No **PowerShell**:
```powershell
cd C:\Users\cbreder\arq_louquinha
docker compose -p arq_prod --env-file .env.prod --profile prod exec web python manage.py createsuperuser
```
Use uma senha **forte** e **não** aceite o "Bypass password validation". Depois, confirme o e-mail da conta. Enquanto o site não envia e-mails de verdade, isso é feito pelo terminal:
```sh
./scripts/prod.sh exec web python manage.py verify_email SEU_USUARIO
```

### 3. Descobrir o endereço do PC no Tailscale

```powershell
tailscale status --json | Select-String DNSName
```
O endereço é algo como `desktop-saqgca0.tail463929.ts.net`. Ignore o ponto final.

### 4. Ajustar o `.env.prod`

Abra o `.env.prod` num editor e deixe estas linhas assim, trocando pelo seu endereço:
```ini
SITE_NAME=Arquivo Louquinha
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,desktop-saqgca0.tail463929.ts.net
DJANGO_CSRF_TRUSTED_ORIGINS=https://desktop-saqgca0.tail463929.ts.net
SESSION_COOKIE_SECURE=1
```
Depois, aplique:
```sh
./scripts/prod.sh up -d --force-recreate web worker
```

### 5. Ligar o HTTPS no painel do Tailscale (uma vez só)

1. Abra <https://login.tailscale.com/admin/dns>.
2. Em **HTTPS Certificates**, clique em **Enable HTTPS**.

### 6. Ligar o Funnel

No **PowerShell**:
```powershell
tailscale funnel --bg http://127.0.0.1:8080
```
- **Na primeira vez**, ele responde "Funnel is not enabled on your tailnet" com um link. Abra o link, autorize o Funnel e rode o comando de novo.
- **Se der certo**, aparece "Available on the internet: https://...ts.net/". O `--bg` mantém o Funnel ligado mesmo depois de reiniciar o PC.
- **Para desligar:** `tailscale funnel --https=443 off`.
- **Para ver o estado:** `tailscale funnel status`.

### 7. Deixar uma amiga testar como autora

**Atalho:** cadastre antes o e-mail dela no admin, em **Contas → E-mails pré-aprovados** (veja "Contas e aprovação"). Assim, quando o e-mail dela for confirmado, a conta já entra aprovada. Enquanto o site não envia e-mails, o comando do passo 2 abaixo faz essa confirmação e aplica a pré-aprovação.

1. Ela cria a conta pelo endereço `.ts.net`, em "Criar conta".
2. Você confirma o e-mail e aprova a conta de uma vez:
   ```sh
   ./scripts/prod.sh exec web python manage.py verify_email NOME_DELA --approve
   ```
3. Para ela poder pôr imagens no texto: no admin, abra **Usuários**, selecione a conta e use a ação **Nível de mídia: Imagens**.

### 8. Obras de teste

O site começa vazio. Para ter algo na página inicial, crie obras simples ("Teste 1" a "Teste 6") na sua conta. O comando não duplica se for rodado de novo:
```sh
./scripts/prod.sh exec web python manage.py create_test_works --user SEU_USUARIO
```
Para apagar, use **Minhas obras → Editar → Excluir obra**.

No **desenvolvimento**, para trocar as milhares de obras falsas do `seed` por essas obras de teste:
```sh
docker compose --profile dev exec web-dev python manage.py seed --clear-only
docker compose --profile dev exec web-dev python manage.py create_test_works --user NOME_DA_CONTA
```
O `seed --clear-only` apaga **só** o que o seed criou: contas `@seed.invalid`, as obras e séries delas e as tags sem uso.

### 9. Atualizar o site público depois de mudanças no código

```sh
./scripts/deploy.sh             # com backup antes (recomendado)
# ou, sem backup:
./scripts/prod.sh build && ./scripts/prod.sh up -d
```

### 10. Endereço mais bonito, provisório (Netlify)

Enquanto o domínio não sai, a Netlify pode servir de "porta de entrada" grátis, com um nome como `arquivolouquinha.netlify.app`:
```
visitante → arquivolouquinha.netlify.app (Netlify) → ...ts.net (Funnel) → este PC
```
A pasta `deploy/netlify/` tem o arquivo `_redirects`, que repassa todas as visitas para o endereço `.ts.net`. O Funnel precisa continuar ligado.

1. Crie uma conta grátis em <https://app.netlify.com/signup>.
2. Em **Sites** (ou **Projects**), escolha **Add new site → Deploy manually** e arraste a pasta `deploy/netlify` inteira.
3. Em **Site configuration → Change site name**, troque o nome aleatório por `arquivolouquinha` (ou outro livre).
4. No `.env.prod`, acrescente o endereço novo nas duas linhas, separado por vírgula:
   ```ini
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,desktop-saqgca0.tail463929.ts.net,arquivolouquinha.netlify.app
   DJANGO_CSRF_TRUSTED_ORIGINS=https://desktop-saqgca0.tail463929.ts.net,https://arquivolouquinha.netlify.app
   ```
5. Aplique: `./scripts/prod.sh up -d --force-recreate web worker`.

Limites: a Netlify também vê o tráfego (como a Cloudflare veria depois); o plano grátis tem cota mensal de tráfego, de sobra para testes; pedidos que demoram mais de ~25 segundos são cortados, então importar um PDF muito grande pode falhar (use o `.ts.net` nesse caso; a tela de importar avisa isso quando o "Endereço direto do site" está preenchido nas Configurações do site); links em e-mails continuam com o `.ts.net`. Para desligar, apague o site na Netlify.

## Domínio próprio (próximo passo)

Com um domínio, o site troca o `.ts.net` pelo seu endereço e passa a usar o **Cloudflare Tunnel** (veja [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md)). Essa é a mesma configuração do servidor próprio, então o link não muda na migração. O túnel exige que o DNS do domínio fique na Cloudflare.

| Opção | Custo | Observação |
|---|---|---|
| **`.eu.org`** (ex.: `arquivolouquinha.eu.org`) | Grátis | Associação sem fins lucrativos, estável desde 1996. Aceita DNS da Cloudflare. A aprovação é manual e leva **dias ou semanas** |
| DigitalPlat (`.dpdns.org`, `.qzz.io`) | Grátis | Aprovação rápida, mas reputação incerta |
| `.com.br` no Registro.br | ~R$ 40/ano | Oficial do Brasil; depois, troque o DNS para a Cloudflare |
| `.com` na Cloudflare | ~US$ 10/ano | O mais simples: já nasce com o DNS na Cloudflare |

Os preços são aproximados; confira na hora. Evite os antigos domínios "grátis" (`.tk`, `.ml`), que foram descontinuados. Evite também o DuckDNS: ele exigiria abrir portas e expor o IP da sua casa.

**Passo a passo do `.eu.org`:**
1. Crie uma conta grátis na Cloudflare e, no painel, clique em **Add a domain**, informando `arquivolouquinha.eu.org`. Anote os **dois nameservers** que a Cloudflare mostrar (algo como `xxx.ns.cloudflare.com`).
2. Crie uma conta em <https://nic.eu.org> (em inglês) e peça o domínio em **New domain**. No campo de servidores de nome, informe os dois da Cloudflare.
3. Espere o e-mail de aprovação. Pode levar semanas; enquanto isso, o site continua no `.ts.net`.
4. Com o domínio aprovado e ativo na Cloudflare, siga o [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md) para criar o túnel. Depois, desligue o Funnel com `tailscale funnel --https=443 off`.

## Desempenho (Fase 7, medido neste PC em 2026-10-30)

**Como foi medido:** produção completa (Caddy, Gunicorn, Postgres, Redis e worker) com as 3.000 obras do seed. Os visitantes simultâneos tinham IPs diferentes, como se viessem pela Cloudflare, e misturavam página inicial, buscas com filtros, páginas de tag, leitura de capítulos e kudos, com ~1 s de pausa entre cliques.

| Cenário | Páginas/s | Mediana | Pior 5% | Erros |
|---|---|---|---|---|
| 10 visitantes | 9,8 | 49 ms | 139 ms | 0 |
| 30 visitantes | 28,3 | 54 ms | 277 ms | 0 |
| 50 visitantes (limite de 1 CPU) | 37,9 | 306 ms | 729 ms | 0 |
| "Máquina fraca" (0,5 CPU por serviço), 15 visitantes | 13,5 | 58 ms | 400 ms | 0 |

- **Memória:** a produção inteira usou ~520 MB no pico (web ~165, worker ~200, banco ~130, o resto <30).
- **Gargalo:** a CPU do Django montando HTML. O banco ficou abaixo de 45% em todos os testes, e cada busca leva 1–2 ms nele.

**Ajustes feitos:**
1. **Cache dos cards de obra no Redis:** a chave é obra + carimbo de atualização + idioma, então o card nunca fica desatualizado. Com 30 visitantes, a mediana caiu de 122 ms para 54 ms e o p95 de 468 ms para 277 ms. O `deploy.sh` limpa esse cache a cada atualização.
2. **Gunicorn com 2 threads por worker** (`GUNICORN_THREADS`): evita travamentos longos quando uma página demora. Na máquina fraca, o pior caso caiu de ~5 s para menos de 1–2 s.

**Na máquina dedicada:** refazer o teste e, se sobrar CPU, subir `GUNICORN_WORKERS`. Cada worker a mais custa ~60 MB.

## Leveza

Todos os containers têm limite de memória e CPU, ajustável no `.env`:

- **Postgres:** 384 MB, ajustado para pouca RAM.
- **Redis:** 128 MB.
- **Web:** 384 MB.
- **Worker:** 256 MB. Ele roda o Celery com 1 processo e o agendador (`beat`) embutido, para não precisar de mais um container.

## Estrutura

```
config/        configurações, URLs, Celery
core/          página inicial, idioma, middlewares, healthcheck, comando seed
accounts/      usuário, pseudônimos, aprovação, preferências
tags/          tags, sinônimos, metatags
works/         obras, capítulos, coautoria, séries
interactions/  kudos, comentários, bookmarks
moderation/    denúncias e histórico de moderação
templates/     HTML
static/        CSS
locale/        traduções
```
