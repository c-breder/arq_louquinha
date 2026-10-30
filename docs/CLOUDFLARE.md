# Publicar o site na internet com o Cloudflare Tunnel

Com o túnel, o site fica acessível pelo seu domínio **sem abrir portas no roteador** e **sem expor o IP da sua casa**. O container `cloudflared` abre uma conexão de saída até a Cloudflare, e as visitas chegam por ela.

```
visitante → Cloudflare (HTTPS) → túnel → cloudflared → Caddy (:80 interno) → Django
```

## O que você precisa

- Uma conta gratuita na Cloudflare.
- Um domínio com o DNS gerenciado pela Cloudflare. Se o domínio foi comprado em outro lugar, a Cloudflare mostra como trocar os "nameservers" no registro do domínio.
- A produção já rodando localmente: `./scripts/deploy.sh` funcionando e <http://localhost:8080> abrindo.

## Passo a passo

1. **Criar o túnel.** No painel da Cloudflare, abra **Zero Trust → Networks → Tunnels** e clique em **Create a tunnel**. Escolha o tipo **Cloudflared** e dê um nome, por exemplo `arq-louquinha`.
2. **Copiar o token.** Na tela "Install connector", escolha **Docker**. Aparece um comando com `--token eyJ...`. Copie **só o token**, o texto longo depois de `--token`. Não precisa rodar o comando: o nosso Compose já tem o serviço.
3. **Apontar o domínio.** Ainda no túnel, abra a aba **Public Hostname → Add a public hostname**:
   - **Subdomain:** vazio, ou `www`.
   - **Domain:** o seu domínio.
   - **Service:** tipo `HTTP`, URL `caddy:80`.

   Use `caddy:80`, e não `localhost`. O túnel roda dentro da rede do Docker e acha o Caddy pelo nome. A porta 80 interna é a que confia no IP real enviado pela Cloudflare.
4. **Ajustar o `.env.prod`:**
   ```ini
   CLOUDFLARE_TUNNEL_TOKEN=<o token copiado>
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,meudominio.com.br
   DJANGO_CSRF_TRUSTED_ORIGINS=https://meudominio.com.br
   SESSION_COOKIE_SECURE=1
   TRUST_CF_CONNECTING_IP=1
   ```
5. **Subir de novo:**
   ```sh
   ./scripts/deploy.sh
   ```
   O `scripts/prod.sh` vê o token e liga o serviço `cloudflared` sozinho. Para conferir: `./scripts/prod.sh logs cloudflared` deve mostrar "Registered tunnel connection".
6. **Testar** `https://meudominio.com.br` de outro aparelho, por exemplo do celular fora do Wi-Fi.

## Recomendações no painel da Cloudflare

- **SSL/TLS → Overview:** modo **Full**.
- **SSL/TLS → Edge Certificates:** ligue **Always Use HTTPS**.
- **Security → Bots:** **Bot Fight Mode** ajuda contra robôs.
- **HSTS:** depois que tudo estiver funcionando, ligue em **SSL/TLS → Edge Certificates → HSTS**, ou defina `SECURE_HSTS_SECONDS=31536000` no `.env.prod`.
- **Caching → Configuration:** o site já envia cabeçalhos de cache certos. Os estáticos ficam guardados por 1 ano, e as páginas não ficam em cache.

## Como o IP real dos visitantes é tratado

- A Cloudflare manda o IP do visitante no cabeçalho `CF-Connecting-IP`.
- Com `TRUST_CF_CONNECTING_IP=1`, o Django usa esse IP para o limite de pedidos e para o bloqueio de logins.
- O Caddy **apaga esse cabeçalho** em quem entra pela porta local `127.0.0.1:8080`. Assim, ninguém consegue forjar um IP falso por esse caminho. Só o tráfego que veio do túnel (porta 80 interna) mantém o cabeçalho.

## Desligar o túnel

Apague o valor de `CLOUDFLARE_TUNNEL_TOKEN` no `.env.prod` e rode:
```sh
./scripts/prod.sh --profile tunnel stop cloudflared
./scripts/deploy.sh
```
