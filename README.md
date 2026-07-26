# Sistema de Rastreador em Tempo Real - Termux Python & Painel Web PHP

Este projeto é um sistema avançado de monitoramento e rastreamento de localização em tempo real composto por duas partes integradas através do **Firebase Realtime Database**:

1. **Cliente Termux (Python CLI)**: Executa no Android (Termux) ou computador para enviar as coordenadas exatas do dispositivo a cada 5 segundos.
2. **Painel Web de Monitoramento (PHP + Leaflet.js)**: Painel administrativo responsivo projetado para hospedagem no **InfinityFree** (ou qualquer servidor PHP), com mapa interativo ao vivo e controle de usuários.

---

## 🛠️ Requisitos e Recursos

- **Geocodificação Reversa Automática**: Identifica **Rua**, **Bairro**, **Cidade**, **Estado** e gera um link direto para o **Google Maps**.
- **Intervalo de Atualização**: 5 segundos em tempo real.
- **Painel de Usuário**:
  - Opção para **ATIVAR / DESATIVAR** o monitoramento com 1 clique.
  - Exibição limpa da localização exata do próprio usuário.
- **Painel do Administrador (CLI e Web)**:
  - Criação de novos logins (usuários comum ou admin).
  - Bloqueio/Desativação de contas.
  - Visualização de todos os dispositivos rastreados em um **mapa interativo ao vivo**.

---

## 🚀 Como Instalar e Rodar no Termux (Android)

1. No seu celular Android, abra o **Termux** e instale o aplicativo auxiliar **Termux:API** (disponível na F-Droid).
2. Dê permissão de localização ao app **Termux:API** nas configurações do Android.
3. Copie esta pasta do projeto para o Termux e acesse a pasta:
   ```bash
   cd /caminho/para/rastreador
   ```
4. Execute o script de instalação automatizado:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
5. Configure a URL do seu Firebase no arquivo `config.json` (ou digite-a na primeira inicialização do app).
6. Inicie o aplicativo:
   ```bash
   python termux_app.py
   ```

> **Nota**: Ao abrir o app pela primeira vez com um banco novo, será criada a conta de administrador padrão:
> - **Usuário**: `admin`
> - **Senha**: `admin123`

---

## 🌐 Hospedagem do Painel Web no InfinityFree (PHP)

Consulte as instruções passo a passo detalhadas no arquivo [`web_panel/README_DEPLOY.md`](file:///c:/Users/ainsterr/Desktop/Termux/rastreador/web_panel/README_DEPLOY.md).

### Resumo do Deploy no InfinityFree:
1. Crie uma conta no [InfinityFree](https://www.infinityfree.com/).
2. Faça o upload do conteúdo da pasta `web_panel/` para o diretório `htdocs` via Gerenciador de Arquivos ou FTP.
3. Acesse a URL do seu site, digite o usuário `admin` e senha `admin123` (e a URL do seu Firebase) para acessar o mapa ao vivo.
