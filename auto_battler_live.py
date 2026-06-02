"""
Auto-Battler 2D — Lives Interativas
Física elástica, pódio 3D, TikTok Live, avatares em background e barra de HP.
Projetado para rodar 24h: erros isolados, reconexão TikTok e fila não-bloqueante.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import re
import sys
import threading
import traceback
from queue import Empty, Queue
from typing import Any
from urllib.parse import quote

import pygame
import requests
from pygame.math import Vector2

# TikTokLive (opcional em dev sem a lib instalada)
try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import CommentEvent, ConnectEvent, GiftEvent, LikeEvent
    from TikTokLive.client.web.web_settings import WebDefaults

    # Chave da API configurada globalmente para evitar o bloqueio (Rate Limit)
    WebDefaults.tiktok_sign_api_key = "euler_MDhjN2JhOTdkNDE1MTZmODQ2YWZiMDlhNzUzODM0YmE3ZWM3OTNlMDVmZTc3MTk2ZTE4ZjI0"

    TIKTOK_DISPONIVEL = True
except ImportError:
    TIKTOK_DISPONIVEL = False
    TikTokLiveClient = None  # type: ignore
    CommentEvent = ConnectEvent = GiftEvent = LikeEvent = None  # type: ignore

# ---------------------------------------------------------------------------
# Configuração global
# ---------------------------------------------------------------------------
LARGURA, ALTURA = 800, 800
FPS = 60
FUNDO = (18, 18, 24)
FUNDO_IMAGEM = "fundo_arena.jpg"

TIKTOK_CHANNEL = "faustolima1503"
TIKTOK_RECONNECT_SEG = 15

HP_INICIAL = 400
RAIO_MAX = 150  
# Dano fixo a cada colisão
DANO_COLISAO = 15.0

PODIO_CORES = [
    (255, 215, 0),
    (192, 192, 192),
    (205, 127, 50),
]
PODIO_ESPESSURA = 20

VELOCIDADE_MIN, VELOCIDADE_MAX = 160, 320
AVATAR_DOWNLOAD_TIMEOUT = 12
MAX_GLADIADORES = 120

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("auto_battler")

# Cache de avatares (nickname minúsculo -> Surface); acesso com lock
_avatar_lock = threading.Lock()
_avatar_cache: dict[str, pygame.Surface] = {}
_avatar_baixando: set[str] = set()


def raio_por_hp(hp: float) -> float:
    """Raio visual com teto nos 2000 HP; acima de 2000 ele não cresce mais."""
    hp_eff = min(hp, 2000.0)
    # 400 HP -> ~40 raio; 2000 HP -> 150 raio
    return max(15.0, 15.0 + (hp_eff / 2000.0) * 135.0)


# ---------------------------------------------------------------------------
# Utilitários visuais 3D
# ---------------------------------------------------------------------------
def _superficie_alpha(w: int, h: int) -> pygame.Surface:
    return pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)


def gerar_surface_esfera_3d(r: int, cor_base: tuple[int, int, int]) -> pygame.Surface:
    """Gera a imagem 3D da esfera e retorna para ser salva no Cache do Gladiador."""
    diam = r * 2 + 4
    tmp = _superficie_alpha(diam, diam)
    ox, oy = r + 2, r + 2

    pygame.draw.circle(tmp, cor_base, (ox, oy), r)

    # Reflexo superior-esquerdo
    reflexo = _superficie_alpha(diam, diam)
    pygame.draw.ellipse(reflexo, (255, 255, 255, 90), (ox - r // 2, oy - r // 2, r, r // 2))
    tmp.blit(reflexo, (0, 0))

    # Sombra inferior-direita
    sombra = _superficie_alpha(diam, diam)
    pygame.draw.arc(
        sombra,
        (0, 0, 0, 110),
        (ox - r + 4, oy - r // 4, r + 6, r + 6),
        3.14 * 0.15,
        3.14 * 0.85,
        max(3, r // 6),
    )
    pygame.draw.ellipse(sombra, (0, 0, 0, 70), (ox + r // 6, oy + r // 3, r // 2, r // 4))
    tmp.blit(sombra, (0, 0))

    return tmp


def desenhar_anel_podio_3d(
    superficie: pygame.Surface,
    cx: int,
    cy: int,
    raio: int,
    cor_base: tuple[int, int, int],
) -> None:
    """Anel com relevo: escuro por fora, claro por dentro."""
    distancia_borda = raio + (PODIO_ESPESSURA // 2)
    
    escuro = tuple(max(0, c - 70) for c in cor_base)
    claro = tuple(min(255, c + 55) for c in cor_base)

    pygame.draw.circle(superficie, escuro, (cx, cy), distancia_borda + 2, PODIO_ESPESSURA + 2)
    pygame.draw.circle(superficie, cor_base, (cx, cy), distancia_borda, PODIO_ESPESSURA)
    pygame.draw.circle(superficie, claro, (cx, cy), distancia_borda - 2, max(2, PODIO_ESPESSURA - 4))


def carregar_fundo() -> pygame.Surface | None:
    caminhos = [
        FUNDO_IMAGEM,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), FUNDO_IMAGEM),
    ]
    for path in caminhos:
        try:
            if os.path.isfile(path):
                img = pygame.image.load(path).convert()
                return pygame.transform.smoothscale(img, (LARGURA, ALTURA))
        except (pygame.error, OSError, ValueError) as exc:
            log.warning("Fundo '%s' ignorado: %s", path, exc)
    log.info("Usando fundo sólido (fundo_arena.jpg não encontrado).")
    return None


# ---------------------------------------------------------------------------
# Avatares (download em thread separada)
# ---------------------------------------------------------------------------
_URL_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
_CDN_HINT_RE = re.compile(r"tiktok|tiktokcdn|muscdn|byteimg", re.IGNORECASE)

_CAMPOS_AVATAR_USER = (
    "avatar_large",
    "avatar_medium",
    "avatar_thumb",
    "avatar_border",
    "avatar_jpg",
    "profile_picture",
    "avatar",
)


def _nickname_de_user(user: Any) -> str:
    if user is None:
        return "X"
    for attr in ("nickname", "nick_name", "nickName", "display_id", "username", "unique_id"):
        try:
            val = getattr(user, attr, None)
            if val and str(val).strip():
                return str(val).strip()
        except Exception:
            continue
    return "X"


def _url_ui_avatars(nickname: str) -> str:
    nome = quote(str(nickname).strip() or "X", safe="")
    return f"https://ui-avatars.com/api/?name={nome}&background=random&color=fff&size=128"


def _normalizar_url(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            val = val.decode("utf-8", errors="ignore")
        except Exception:
            return None
    s = str(val).strip()
    if not s or not _URL_HTTP_RE.match(s):
        return None
    return s


def _url_de_image_model(img: Any) -> str | None:
    if img is None:
        return None
    try:
        for lista_attr in ("m_urls", "urls", "url_list", "urlList"):
            lista = getattr(img, lista_attr, None)
            if lista:
                for item in lista:
                    url = _normalizar_url(item)
                    if url:
                        return url
        uri = getattr(img, "m_uri", None) or getattr(img, "uri", None)
        url = _normalizar_url(uri)
        if url:
            return url
    except Exception:
        pass
    return None


def _url_de_dict(obj: dict, profundidade: int, visitados: set[int]) -> str | None:
    if profundidade <= 0:
        return None
    oid = id(obj)
    if oid in visitados:
        return None
    visitados.add(oid)

    chaves_url = ("m_urls", "urls", "url_list", "urlList", "m_uri", "uri")
    chaves_avatar = ("avatar_large", "avatar_medium", "avatar_thumb", "avatar", "profile_picture")

    for chave in chaves_avatar:
        if chave not in obj:
            continue
        url = _extrair_url_recursivo(obj[chave], profundidade - 1, visitados)
        if url:
            return url

    for chave in chaves_url:
        val = obj.get(chave)
        if isinstance(val, list):
            for item in val:
                url = _normalizar_url(item)
                if url:
                    return url
        else:
            url = _normalizar_url(val)
            if url:
                return url

    for val in obj.values():
        if isinstance(val, (dict, list)) or val is not None:
            url = _extrair_url_recursivo(val, profundidade - 1, visitados)
            if url:
                return url
    return None


def _extrair_url_recursivo(obj: Any, profundidade: int = 5, visitados: set[int] | None = None) -> str | None:
    if obj is None or profundidade <= 0:
        return None
    if visitados is None:
        visitados = set()

    url = _normalizar_url(obj)
    if url:
        return url

    url = _url_de_image_model(obj)
    if url:
        return url

    if isinstance(obj, dict):
        return _url_de_dict(obj, profundidade, visitados)

    if isinstance(obj, (list, tuple)):
        for item in obj:
            url = _extrair_url_recursivo(item, profundidade - 1, visitados)
            if url:
                return url
        return None

    oid = id(obj)
    if oid in visitados:
        return None
    visitados.add(oid)

    for attr in _CAMPOS_AVATAR_USER:
        try:
            sub = getattr(obj, attr, None)
        except Exception:
            continue
        if sub is None:
            continue
        url = _extrair_url_recursivo(sub, profundidade - 1, visitados)
        if url:
            return url

    for metodo in ("to_pydict", "to_dict", "dict"):
        try:
            fn = getattr(obj, metodo, None)
            if callable(fn):
                d = fn()
                if isinstance(d, dict):
                    url = _url_de_dict(d, profundidade, visitados)
                    if url:
                        return url
        except Exception:
            pass

    return None


def extrair_avatar_url(user: Any) -> str:
    nickname = _nickname_de_user(user)

    if user is None:
        return _url_ui_avatars(nickname)

    try:
        for campo in _CAMPOS_AVATAR_USER:
            try:
                sub = getattr(user, campo, None)
            except Exception:
                continue
            if sub is None:
                continue
            if isinstance(sub, str):
                url = _normalizar_url(sub)
                if url:
                    return url
            url = _url_de_image_model(sub)
            if url:
                return url

        url = _extrair_url_recursivo(user, profundidade=6)
        if url:
            return url

    except Exception as exc:
        log.debug("extrair_avatar_url(%s): %s", nickname, exc)

    return _url_ui_avatars(nickname)

def _surface_quadrada(imagem: pygame.Surface, lado: int) -> pygame.Surface:
    lado = max(4, lado)
    esc = pygame.transform.smoothscale(imagem, (lado, lado))
    if esc.get_flags() & pygame.SRCALPHA:
        return esc
    out = pygame.Surface((lado, lado), pygame.SRCALPHA)
    out.blit(esc, (0, 0))
    return out


def _baixar_avatar_sync(nickname: str, url: str, lado: int) -> pygame.Surface | None:
    if not url: return None
    # Suporte para avatares locais
    if os.path.isfile(url):
        try:
            img = pygame.image.load(url)
            return _surface_quadrada(img.convert_alpha(), lado)
        except Exception:
            return None

    if not _URL_HTTP_RE.match(url.strip()):
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if _CDN_HINT_RE.search(url):
            headers["Referer"] = "https://www.tiktok.com/"
        resp = requests.get(url, headers=headers, timeout=AVATAR_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        data = resp.content
        if not data:
            return None
        img = pygame.image.load(io.BytesIO(data))
        return _surface_quadrada(img.convert_alpha(), lado)
    except Exception as exc:
        log.warning("Avatar '%s' falhou: %s", nickname, exc)
        return None


def worker_baixar_avatar(
    nickname: str,
    url: str,
    lado: int,
    gladiadores: list["Gladiator"],
    lock_glads: threading.Lock,
) -> None:
    chave = nickname.lower()
    try:
        sup = _baixar_avatar_sync(nickname, url, lado)
        if sup is not None:
            with _avatar_lock:
                _avatar_cache[chave] = sup
            with lock_glads:
                for g in gladiadores:
                    if g.vivo and g.nome.lower() == chave:
                        g.avatar_surface = sup
                        # Reseta o cache interno dele para forçar a atualizar a imagem na tela
                        g._cache_avatar_img = None
                        break
    finally:
        with _avatar_lock:
            _avatar_baixando.discard(chave)


def agendar_avatar(
    gladiador: "Gladiator",
    avatar_url: str | None,
    gladiadores: list["Gladiator"],
    lock_glads: threading.Lock,
) -> None:
    if not avatar_url:
        return
    chave = gladiador.nome.lower()
    
    # Baixa sempre a foto em alta qualidade (150x150)
    lado = 150 

    with _avatar_lock:
        if chave in _avatar_cache:
            gladiador.avatar_surface = _avatar_cache[chave]
            return
        if chave in _avatar_baixando:
            return
        _avatar_baixando.add(chave)

    threading.Thread(
        target=worker_baixar_avatar,
        args=(gladiador.nome, avatar_url, lado, gladiadores, lock_glads),
        daemon=True,
        name=f"avatar-{chave[:12]}",
    ).start()


# ---------------------------------------------------------------------------
# Classe Gladiator
# ---------------------------------------------------------------------------
class Gladiator:
    def __init__(self, nome: str, hp: float = HP_INICIAL, avatar_url: str | None = None):
        self.nome = nome.strip() or "Anônimo"
        self.hp = float(hp)
        self.hp_max = float(hp)
        self.avatar_url = avatar_url
        self.avatar_surface: pygame.Surface | None = None
        self.cor_base = (
            random.randint(60, 255),
            random.randint(60, 255),
            random.randint(60, 255),
        )
        margem = 80
        self.pos = Vector2(
            random.uniform(margem, LARGURA - margem),
            random.uniform(margem, ALTURA - margem),
        )
        vel_mag = random.uniform(VELOCIDADE_MIN, VELOCIDADE_MAX)
        self.vel = Vector2(1, 0).rotate(random.uniform(0, 360)) * vel_mag
        self.total_gifts = 0.0

        # CACHE DE RENDERIZAÇÃO: Impede o jogo de travar gerando imagens toda hora
        self._cache_avatar_lado = 0
        self._cache_avatar_img = None
        self._cache_esfera_raio = 0
        self._cache_esfera_img = None

    @property
    def vivo(self) -> bool:
        return self.hp > 0

    @property
    def raio(self) -> float:
        return raio_por_hp(self.hp)

    def atualizar_fisica(self, dt: float) -> None:
        self.pos += self.vel * dt
        r = self.raio

        if self.pos.x - r < 0:
            self.pos.x = r
            self.vel.x = abs(self.vel.x)
        elif self.pos.x + r > LARGURA:
            self.pos.x = LARGURA - r
            self.vel.x = -abs(self.vel.x)

        if self.pos.y - r < 0:
            self.pos.y = r
            self.vel.y = abs(self.vel.y)
        elif self.pos.y + r > ALTURA:
            self.pos.y = ALTURA - r
            self.vel.y = -abs(self.vel.y)

    def separar_de(self, outro: "Gladiator") -> None:
        delta = self.pos - outro.pos
        dist = delta.length()
        soma_r = self.raio + outro.raio
        if dist < 1e-6:
            delta = Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
            if delta.length_squared() < 1e-6:
                delta = Vector2(1, 0)
            dist = delta.length()
        if dist < soma_r:
            overlap = (soma_r - dist) / 2.0
            normal = delta.normalize()
            self.pos += normal * overlap
            outro.pos -= normal * overlap
            rel = self.vel - outro.vel
            sep_v = rel.dot(normal)
            if sep_v < 0:
                impulso = normal * sep_v
                self.vel -= impulso
                outro.vel += impulso

    def aplicar_dano_colisao(self, outro: "Gladiator") -> None:
        if self.hp <= 0 or outro.hp <= 0:
            return
        
        dano_self = DANO_COLISAO
        dano_outro = DANO_COLISAO
        
        # Se bater 2000 de HP, recebe 75 de dano (e continua dando 15)
        if self.hp >= 2000:
            dano_self = 75.0
        if outro.hp >= 2000:
            dano_outro = 75.0
            
        self.hp -= dano_self
        outro.hp -= dano_outro

    def desenhar(self, superficie: pygame.Surface, rank_presente: int | None, fonte_hp, fonte_nome=None) -> None:
        import math
        cx, cy = int(self.pos.x), int(self.pos.y)
        r = int(self.raio)

        # Determinar cor da serra com base no top presentes
        cor_borda = self.cor_base
        if rank_presente is not None:
            if rank_presente == 0:
                cor_borda = (255, 215, 0) # Dourado
            elif rank_presente == 1:
                cor_borda = (192, 192, 192) # Prata
            elif rank_presente == 2:
                cor_borda = (205, 127, 50) # Bronze

        # Desenhar serra em volta
        dentes = max(12, int(r / 2.5))
        profundidade = max(4, int(r * 0.2))
        pontos = []
        tempo = pygame.time.get_ticks() / 1000.0
        offset_angulo = tempo * 2.0  # Rotação da serra
        
        for i in range(dentes * 2):
            angulo = i * math.pi / dentes + offset_angulo
            r_ponto = r + profundidade if i % 2 == 0 else r
            # Adiciona inclinação para parecer uma serra
            angulo_ponto = angulo + (0.1 if i % 2 == 0 else 0)
            x = cx + r_ponto * math.cos(angulo_ponto)
            y = cy + r_ponto * math.sin(angulo_ponto)
            pontos.append((x, y))
            
        pygame.draw.polygon(superficie, cor_borda, pontos)

        # Desenhar avatar circular interno
        lado = max(4, r * 2)
        rect_avatar = pygame.Rect(0, 0, lado, lado)
        rect_avatar.center = (cx, cy)

        if self.avatar_surface is not None:
            if self._cache_avatar_lado != lado or self._cache_avatar_img is None:
                try:
                    img_esc = pygame.transform.smoothscale(self.avatar_surface, (lado, lado))
                    mask = pygame.Surface((lado, lado), pygame.SRCALPHA)
                    pygame.draw.circle(mask, (255, 255, 255, 255), (lado // 2, lado // 2), lado // 2)
                    
                    self._cache_avatar_img = pygame.Surface((lado, lado), pygame.SRCALPHA)
                    self._cache_avatar_img.blit(img_esc, (0, 0))
                    self._cache_avatar_img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                    self._cache_avatar_lado = lado
                except pygame.error:
                    pass
            
            if self._cache_avatar_img:
                superficie.blit(self._cache_avatar_img, rect_avatar.topleft)
            else:
                pygame.draw.circle(superficie, (45, 45, 55), (cx, cy), r)
        else:
            pygame.draw.circle(superficie, (45, 45, 55), (cx, cy), r)
            
        # Linha interna da serra para melhorar o visual
        pygame.draw.circle(superficie, cor_borda, (cx, cy), r, max(2, int(r * 0.05)))

        # === HP CENTRALIZADO ===
        cor_hp = (0, 255, 0) # Verde vibrante
        texto = fonte_hp.render(str(int(self.hp)), True, cor_hp)
        outline = fonte_hp.render(str(int(self.hp)), True, (0, 0, 0))
        tx = cx - texto.get_width() // 2
        ty = cy - texto.get_height() // 2
        
        # Outline bem espesso (loop para várias direções)
        for dx in [-3, -2, -1, 0, 1, 2, 3]:
            for dy in [-3, -2, -1, 0, 1, 2, 3]:
                if dx != 0 or dy != 0:
                    superficie.blit(outline, (tx + dx, ty + dy))
                    
        superficie.blit(texto, (tx, ty))

        # === NOME DO GLADIADOR ===
        if fonte_nome:
            texto_nome = fonte_nome.render(self.nome, True, (255, 255, 255))
            sombra_nome = fonte_nome.render(self.nome, True, (0, 0, 0))
            tx_nome = cx - texto_nome.get_width() // 2
            ty_nome = cy + r + 5
            superficie.blit(sombra_nome, (tx_nome + 2, ty_nome + 2))
            superficie.blit(texto_nome, (tx_nome, ty_nome))


# ---------------------------------------------------------------------------
# Combate e pódio
# ---------------------------------------------------------------------------
def processar_colisoes(gladiadores: list[Gladiator]) -> bool:
    bateu = False
    n = len(gladiadores)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = gladiadores[i], gladiadores[j]
            if not a.vivo or not b.vivo:
                continue
            if a.pos.distance_to(b.pos) < a.raio + b.raio:
                a.separar_de(b)
                a.aplicar_dano_colisao(b)
                bateu = True
    return bateu


def remover_mortos(gladiadores: list[Gladiator]) -> list[Gladiator]:
    return [g for g in gladiadores if g.vivo]


def ranks_presentes(gladiadores: list[Gladiator]) -> dict[Gladiator, int]:
    vivos = [g for g in gladiadores if g.vivo and g.total_gifts > 0]
    vivos.sort(key=lambda g: g.total_gifts, reverse=True)
    return {g: i for i, g in enumerate(vivos[:3])}


def desenhar_cena(
    superficie: pygame.Surface,
    gladiadores: list[Gladiator],
    fonte_hp,
    fonte_nome=None
) -> None:
    vivos = [g for g in gladiadores if g.vivo]
    vivos.sort(key=lambda g: g.hp)
    podio_presentes = ranks_presentes(gladiadores)
    for g in vivos:
        g.desenhar(superficie, podio_presentes.get(g), fonte_hp, fonte_nome)


# ---------------------------------------------------------------------------
# Fila de comandos (dict TikTok + texto terminal)
# ---------------------------------------------------------------------------
def enfileirar(fila: Queue, cmd: str, nome: str, valor: float = 0, avatar_url: str | None = None) -> None:
    fila.put({
        "cmd": cmd,
        "nome": nome,
        "valor": valor,
        "avatar_url": avatar_url,
    })


def _buscar_por_nome(gladiadores: list[Gladiator], nome: str) -> Gladiator | None:
    nome_l = nome.lower()
    for g in gladiadores:
        if g.vivo and g.nome.lower() == nome_l:
            return g
    return None


def aplicar_dict_comando(
    msg: dict[str, Any],
    gladiadores: list[Gladiator],
    lock_glads: threading.Lock,
) -> None:
    try:
        cmd = str(msg.get("cmd", "")).lower()
        nome = str(msg.get("nome", "")).strip()
        valor = float(msg.get("valor", 0) or 0)
        avatar_url = msg.get("avatar_url")

        if not nome and cmd != "connect":
            return

        with lock_glads:
            if cmd == "spawn":
                if len([g for g in gladiadores if g.vivo]) >= MAX_GLADIADORES:
                    log.warning("Arena cheia (%s), spawn ignorado: %s", MAX_GLADIADORES, nome)
                    return
                if _buscar_por_nome(gladiadores, nome):
                    return
                g = Gladiator(nome, HP_INICIAL, avatar_url=avatar_url)
                gladiadores.append(g)
                if avatar_url:
                    agendar_avatar(g, avatar_url, gladiadores, lock_glads)
                elif nome.lower() in _avatar_cache:
                    g.avatar_surface = _avatar_cache[nome.lower()]

            elif cmd == "like":
                alvo = _buscar_por_nome(gladiadores, nome)
                if alvo:
                    # CORREÇÃO: Removemos o fallback desproporcional. Agora soma exatamente o valor da curtida.
                    inc = valor if valor > 0 else 1.0
                    alvo.hp += inc
                else:
                    g = Gladiator(nome, HP_INICIAL + (valor if valor > 0 else 1.0), avatar_url=avatar_url)
                    gladiadores.append(g)
                    if avatar_url:
                        agendar_avatar(g, avatar_url, gladiadores, lock_glads)

            elif cmd == "gift":
                alvo = _buscar_por_nome(gladiadores, nome)
                inc = float(valor) if valor > 0 else 1.0
                if alvo:
                    alvo.hp += inc
                    alvo.total_gifts += inc
                else:
                    g = Gladiator(nome, HP_INICIAL + inc, avatar_url=avatar_url)
                    g.total_gifts += inc
                    gladiadores.append(g)
                    if avatar_url:
                        agendar_avatar(g, avatar_url, gladiadores, lock_glads)

    except Exception as exc:
        log.error("Comando inválido %s: %s", msg, exc)


def processar_linha_terminal(linha: str, fila: Queue) -> None:
    if not linha:
        return
    partes = linha.split(maxsplit=1)
    cmd = partes[0].lower()
    nome = partes[1].strip() if len(partes) > 1 else ""
    if cmd == "spawn" and nome:
        enfileirar(fila, "spawn", nome)
    elif cmd == "like" and nome:
        # CORREÇÃO: O teste via terminal agora também injeta apenas 1 HP, em vez de 10
        enfileirar(fila, "like", nome, valor=1)
    elif cmd == "gift" and nome:
        enfileirar(fila, "gift", nome, valor=50)
    else:
        print("[CMD] spawn [nome] | like [nome] | gift [nome]")


def drenar_fila(
    fila: Queue,
    gladiadores: list[Gladiator],
    lock_glads: threading.Lock,
) -> None:
    while True:
        try:
            item = fila.get_nowait()
        except Empty:
            break
        try:
            if isinstance(item, dict):
                aplicar_dict_comando(item, gladiadores, lock_glads)
            elif isinstance(item, str):
                processar_linha_terminal(item, fila)
        except Exception:
            log.exception("Erro ao processar item da fila")


def thread_terminal(fila: Queue) -> None:
    while True:
        try:
            linha = sys.stdin.readline()
        except (EOFError, OSError):
            break
        if not linha:
            break
        try:
            fila.put(linha.strip())
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TikTok Live (async em thread dedicada)
# ---------------------------------------------------------------------------
def moedas_presente(event: Any) -> int:
    try:
        if hasattr(event, "diamonds") and event.diamonds:
            return max(1, int(event.diamonds))
        gift = getattr(event, "gift", None)
        if gift is not None:
            for attr in ("diamond_count", "diamondCount", "fan_ticket_count", "fanTicketCount"):
                v = getattr(gift, attr, None)
                if v and int(v) > 0:
                    repeat = max(1, int(getattr(event, "repeat_count", 1) or 1))
                    return max(1, int(v)) * repeat
        return max(1, int(getattr(event, "repeat_count", 1) or 1))
    except (TypeError, ValueError):
        return 1


def gift_deve_processar(event: Any) -> bool:
    try:
        gift = getattr(event, "gift", None)
        if gift is None:
            return True
        gift_type = int(getattr(gift, "gift_type", 0) or getattr(gift, "giftType", 0) or 0)
        if gift_type == 1:
            return int(getattr(event, "repeat_end", 0) or 0) == 1
        streakable = getattr(gift, "streakable", None)
        if streakable:
            return not getattr(event, "streaking", False)
        return True
    except Exception:
        return True


def criar_loop_tiktok(fila: Queue) -> None:
    if not TIKTOK_DISPONIVEL:
        log.warning("TikTokLive não instalado. pip install TikTokLive")
        return

    async def runner() -> None:
        while True:
            client = TikTokLiveClient(unique_id=TIKTOK_CHANNEL)
            try:

                @client.on(ConnectEvent)
                async def on_connect(event: ConnectEvent) -> None:
                    log.info("TikTok conectado: @%s", getattr(event, "unique_id", TIKTOK_CHANNEL))

                @client.on(CommentEvent)
                async def on_comment(event: CommentEvent) -> None:
                    try:
                        nome = "Viewer"
                        avatar_url = None
                        try:
                            user = event.user
                            nome = getattr(user, "nickname", None) or "Viewer"
                            avatar_url = extrair_avatar_url(user)
                        except Exception:
                            # Fallback caso a biblioteca TikTokLive bugue no user (ex: TypeError nickName)
                            if hasattr(event, "user_info"):
                                ui = event.user_info
                                nome = getattr(ui, "nickname", None) or getattr(ui, "nick_name", "Viewer")
                        
                        enfileirar(
                            fila,
                            "spawn",
                            nome,
                            avatar_url=avatar_url,
                        )
                    except Exception:
                        log.exception("CommentEvent")

                @client.on(LikeEvent)
                async def on_like(event: LikeEvent) -> None:
                    try:
                        user = getattr(event, "user", None)
                        if user is None:
                            return
                        count = max(1, int(getattr(event, "count", 1) or 1))
                        enfileirar(
                            fila,
                            "like",
                            getattr(user, "nickname", "Viewer"),
                            valor=float(count),
                            avatar_url=extrair_avatar_url(user),
                        )
                    except Exception:
                        log.exception("LikeEvent")

                @client.on(GiftEvent)
                async def on_gift(event: GiftEvent) -> None:
                    try:
                        if not gift_deve_processar(event):
                            return
                        user = getattr(event, "user", None)
                        if user is None:
                            return
                        moedas = moedas_presente(event)
                        enfileirar(
                            fila,
                            "gift",
                            getattr(user, "nickname", "Viewer"),
                            valor=float(moedas),
                            avatar_url=extrair_avatar_url(user),
                        )
                    except Exception:
                        log.exception("GiftEvent")

                await client.start(fetch_gift_info=True)
                await client.wait_for_complete()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("TikTok desconectado: %s — reconectando em %ss", exc, TIKTOK_RECONNECT_SEG)
                await asyncio.sleep(TIKTOK_RECONNECT_SEG)

    def _thread_target() -> None:
        try:
            asyncio.run(runner())
        except Exception:
            log.exception("Thread TikTok encerrada")

    threading.Thread(target=_thread_target, daemon=True, name="tiktok-live").start()


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------
def main() -> None:
    fila: Queue = Queue()

    import socket
    sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock_udp.bind(("127.0.0.1", 5005))
        sock_udp.setblocking(False)
        log.info("Servidor UDP de controle iniciado na porta 5005.")
    except Exception as e:
        log.error("Falha ao iniciar servidor UDP: %s", e)
        sock_udp = None

    if TIKTOK_DISPONIVEL and TIKTOK_CHANNEL:
        criar_loop_tiktok(fila)

    pygame.init()
    try:
        pygame.mixer.quit()
    except pygame.error:
        pass

    tela = pygame.display.set_mode((LARGURA, ALTURA))
    pygame.display.set_caption("Auto-Battler Live — Espaço Sideral")
    relogio = pygame.time.Clock()
    # Usa Impact ou Arial Black para texto mais "pesado" igual ao da imagem
    fonte_hp = pygame.font.SysFont("impact", 32, bold=False)
    fonte_nome = pygame.font.SysFont("arial", 20, bold=True)

    try:
        som_colisao = pygame.mixer.Sound("hit.wav")
        som_colisao.set_volume(0.3)
    except Exception:
        som_colisao = None

    fundo_img = None  # Ignora a imagem local para forçar o desenho do espaço estrelado
    estrelas = []
    import random
    for _ in range(150):
        estrelas.append((random.randint(0, LARGURA), random.randint(0, ALTURA), random.uniform(1, 3)))
    fila_cmd: Queue = Queue()
    lock_glads = threading.Lock()
    gladiadores: list[Gladiator] = []

    threading.Thread(target=thread_terminal, args=(fila_cmd,), daemon=True).start()
    criar_loop_tiktok(fila_cmd)

    rodando = True
    print("=== Auto-Battler Live ===")
    print(f"TikTok: {TIKTOK_CHANNEL} ({'ativo' if TIKTOK_DISPONIVEL else 'pip install TikTokLive'})")
    print("Terminal: spawn [nome] | like [nome] | gift [nome]\n")

    while rodando:
        try:
            dt = relogio.tick(FPS) / 1000.0

            if sock_udp:
                try:
                    while True:
                        dados, addr = sock_udp.recvfrom(1024)
                        msg = dados.decode('utf-8').strip()
                        partes = msg.split('|')
                        if partes:
                            cmd = partes[0]
                            nome = partes[1] if len(partes) > 1 else "Unknown"
                            if cmd == "spawn":
                                avatar_path = partes[2] if len(partes) > 2 and partes[2] else None
                                enfileirar(fila_cmd, "spawn", nome, avatar_url=avatar_path)
                            elif cmd == "gift":
                                val = float(partes[2]) if len(partes) > 2 else 1000.0
                                enfileirar(fila_cmd, "gift", nome, valor=val)
                            elif cmd == "like":
                                enfileirar(fila_cmd, "like", nome)
                except BlockingIOError:
                    pass
                except Exception as e:
                    log.error("Erro no UDP: %s", e)

            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    rodando = False

            drenar_fila(fila_cmd, gladiadores, lock_glads)

            with lock_glads:
                for g in gladiadores:
                    if g.vivo:
                        g.atualizar_fisica(dt)
                
                teve_colisao = processar_colisoes(gladiadores)
                if teve_colisao and som_colisao is not None:
                    if not hasattr(processar_colisoes, 'ultimo_som'):
                        processar_colisoes.ultimo_som = 0
                    agora = pygame.time.get_ticks()
                    if agora - processar_colisoes.ultimo_som > 150:  # 150ms cooldown
                        som_colisao.play()
                        processar_colisoes.ultimo_som = agora
                        
                gladiadores = remover_mortos(gladiadores)

            if fundo_img is not None:
                tela.blit(fundo_img, (0, 0))
            else:
                tela.fill((10, 10, 20)) # Fundo de espaço vazio
                for ex, ey, er in estrelas:
                    pygame.draw.circle(tela, (255, 255, 255), (int(ex), int(ey)), int(er))
            
            # --- Marca d'Água ---
            if not hasattr(main, "watermark_surf"):
                fonte_wm = pygame.font.SysFont("arial", 40, bold=True)
                main.watermark_surf = fonte_wm.render("AntiGravity / igorlima1992", True, (255, 255, 255))
                main.watermark_surf.set_alpha(50) # Transparência
            tela.blit(main.watermark_surf, (LARGURA // 2 - main.watermark_surf.get_width() // 2, ALTURA - 60))
            # --------------------

            with lock_glads:
                desenhar_cena(tela, gladiadores, fonte_hp, fonte_nome)

            pygame.display.flip()

        except pygame.error as exc:
            log.critical("Pygame: %s", exc)
            rodando = False
        except Exception:
            log.exception("Frame com erro (continuando)")
            traceback.print_exc()

    pygame.quit()


if __name__ == "__main__":
    main()