# AntiGravity - Auto-Battler 2D para TikTok Lives Interativas ⚔️

Bem-vindo ao repositório do **AntiGravity**, um simulador Auto-Battler 2D projetado especificamente para transmissões ao vivo (Lives) interativas no TikTok! 

Neste jogo, os espectadores da sua live podem participar da batalha interagindo no chat, enviando curtidas (likes) e presentes (gifts). Cada interação afeta a arena em tempo real, permitindo que a audiência "jogue" enquanto assiste.

## 🌟 Funcionalidades

- **Interatividade via TikTok Live:**
  - **Comentários:** Espectadores digitam comandos no chat para entrar na arena (spawn).
  - **Curtidas (Likes):** Curar ou aumentar a vida (HP) de um gladiador.
  - **Presentes (Gifts):** Dão buffs massivos de HP e destacam o gladiador com efeitos visuais e posições no pódio de maiores apoiadores.
- **Física e Combate:** Sistema de colisão elástica e dano baseado no impacto entre os avatares.
- **Avatares Dinâmicos:** Captura automaticamente a foto de perfil do usuário do TikTok e renderiza na arena.
- **Painel de Controle Embutido:** Um dashboard para gerenciar a arena manualmente via rede local (UDP).
- **Projetado para 24/7:** Tratamento de erros isolados, reconexão automática com a API do TikTok e filas de mensagens não bloqueantes.

## 📋 Pré-requisitos

Certifique-se de ter o Python 3.8 ou superior instalado. O projeto utiliza as seguintes bibliotecas:

- `pygame` (para renderização gráfica 2D)
- `requests` (para download dos avatares)
- `TikTokLive` (para capturar os eventos da live do TikTok)

Instale todas as dependências com o comando:

```bash
pip install -r requirements.txt
```

## 🚀 Como Executar

### 1. Auto-Battler Arena (Jogo Principal)
Execute o script principal para iniciar a arena. Certifique-se de configurar o seu `@usuario` do TikTok no arquivo `auto_battler_live.py` na variável `TIKTOK_CHANNEL`.

```bash
python auto_battler_live.py
```

### 2. Painel de Controle (Opcional)
Se desejar testar a interação ou controlar a live manualmente, abra o dashboard em uma segunda janela do terminal:

```bash
python painel_controle.py
```
A partir do painel, você pode:
- Spawnar "Bots" (personagens aleatórios para encher a arena).
- Dar HP para personagens específicos simulando presentes ou curtidas.

## 📁 Estrutura de Arquivos

- `auto_battler_live.py`: O núcleo do jogo, responsável pelos gráficos (Pygame), física e a conexão com a live.
- `painel_controle.py`: Uma interface gráfica construída em Tkinter que envia comandos UDP locais (porta 5005) para controlar a arena.
- `requirements.txt`: Lista de pacotes e dependências Python necessários.
- `avatares/`: Diretório para armazenar e manter o cache dos avatares carregados durante a live.
- Imagens e Áudios: Arquivos como `fundo_arena.jpg` e `hit.wav` fornecem as características visuais e de efeitos sonoros da arena.

## 🤝 Como Contribuir

Sinta-se à vontade para fazer um **Fork** deste repositório, sugerir melhorias na física, criar novos eventos interativos e abrir **Pull Requests**!

## 📜 Licença

Distribuído sob a licença MIT. Sinta-se livre para usar, modificar e adaptar para as suas próprias transmissões ao vivo.
